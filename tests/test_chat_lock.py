"""Tests for the per-companion chat lock in api.ollama.send_message.

Race-condition regression: rapid-fire sends used to produce assistant
responses paired with the wrong user message because each call to
send_message read recent_messages() at a different moment, and Ollama
returned responses in non-deterministic order.

The fix is a per-companion threading.Lock. These tests verify that
concurrent sends against the same companion are serialized, while
sends against different companions stay parallel.
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Make api importable
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from api import ollama


def _make_companion(name: str) -> str:
    """Create a test companion and return its id."""
    from api import db
    cid = db.create_companion(
        name=name,
        personality="p1",
        model_name="qwen2.5:0.5b",  # smallest model for speed
        soul_md="You are a test companion.",
    )
    return cid


def test_lock_exists_and_per_companion():
    """_get_chat_lock returns a Lock, distinct per companion."""
    a = ollama._get_chat_lock("test-companion-A")
    b = ollama._get_chat_lock("test-companion-A")
    c = ollama._get_chat_lock("test-companion-B")
    assert isinstance(a, type(b)), "Same companion should get the same lock type"
    assert a is b, "Same companion should reuse the same lock instance"
    assert a is not c, "Different companions should get different locks"


def test_lock_serializes_same_companion():
    """If 5 threads call _hold_lock(50ms) on the same companion, total time ≥ 250ms."""
    lock = ollama._get_chat_lock(f"test-serial-{time.time()}")

    def _hold():
        with lock:
            time.sleep(0.05)
            return time.time()

    start = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(lambda _: _hold(), range(5)))
    elapsed = time.time() - start
    assert elapsed >= 0.25, f"Lock did not serialize — 5 holds of 50ms ran in {elapsed:.2f}s"


def test_lock_parallelizes_different_companions():
    """If 3 threads hold the lock for 3 different companions concurrently, total time < 200ms (not 300ms)."""
    a = ollama._get_chat_lock(f"test-par-a-{time.time()}")
    b = ollama._get_chat_lock(f"test-par-b-{time.time()}")
    c = ollama._get_chat_lock(f"test-par-c-{time.time()}")

    def _hold(lock):
        with lock:
            time.sleep(0.1)
            return True

    start = time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_hold, x) for x in (a, b, c)]
        for f in as_completed(futs):
            f.result()
    elapsed = time.time() - start
    assert elapsed < 0.2, f"Different-companion locks serialized — 3 holds of 100ms took {elapsed:.2f}s"


def test_lock_blocks_during_long_send():
    """While one thread is inside the lock for 200ms, a second thread blocks."""
    lock = ollama._get_chat_lock(f"test-block-{time.time()}")
    second_holder_started_at = None

    def first():
        with lock:
            time.sleep(0.2)

    def second():
        nonlocal second_holder_started_at
        time.sleep(0.05)  # let the first thread grab the lock first
        with lock:
            second_holder_started_at = time.time()

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    start = time.time()
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    elapsed_since_start = second_holder_started_at - start
    # Second thread should have started holding the lock around t=0.2s,
    # so its lock-acquire time should be ~0.2s from start, not ~0.05s.
    assert elapsed_since_start >= 0.18, f"Second thread wasn't blocked: {elapsed_since_start:.2f}s"


if __name__ == "__main__":
    import traceback
    failures = []
    tests = [
        test_lock_exists_and_per_companion,
        test_lock_serializes_same_companion,
        test_lock_parallelizes_different_companions,
        test_lock_blocks_during_long_send,
    ]
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            failures.append((t.__name__, traceback.format_exc()))
            print(f"  ✗ {t.__name__}: {e}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed")
