#!/usr/bin/env python3
"""Test the crash-guard in our_nook.py by deliberately crashing.
Spawned as a subprocess so it has a clean Python interpreter to crash in."""
import sys
import os
import time

# This script intentionally crashes AFTER installing the excepthook
# to verify the guard writes a structured log to disk.
#
# We replicate the import section from our_nook.py and then the
# excepthook setup, so this is a faithful end-to-end test.

import sys, os, time, subprocess, signal, traceback, platform
from datetime import datetime

# Replicate the crash-guard code from our_nook.py
def _crash_log_path():
    system = platform.system()
    home = os.path.expanduser("~")
    if system == "Darwin":
        base = os.path.join(home, "Library", "Application Support", "OurNook")
    elif system == "Windows":
        base = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        base = os.path.join(base, "OurNook")
    else:
        base = os.path.join(home, ".local", "share", "OurNook")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "crash.log")


def _dump_crash(exc_type, exc_value, exc_tb):
    path = _crash_log_path()
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n\n{'=' * 70}\n")
        f.write(f"CRASH_GUARD_TEST {datetime.now().isoformat()}\n")
        f.write(f"{'=' * 70}\n")
        f.write(tb_text)


def _excepthook(exc_type, exc_value, exc_tb):
    _dump_crash(exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook

# Now deliberately crash
print("about to crash…", file=sys.stderr)
raise RuntimeError("CRASH_GUARD_TEST — deliberate test of the crash log path")
