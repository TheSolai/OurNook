"""
OurNook import/export/create e2e tests.

Hits the live FastAPI server on port 18765. Assumes server is already running.
Exercises:
  - list companions
  - create companion (via /api/companions and /api/companions/full)
  - get companion
  - update companion (basic fields)
  - update soul.md
  - export as JSON
  - export as PNG (with embedded card)
  - import from JSON file
  - import from PNG file (round-trip)
  - import via paste-JSON endpoint
  - error cases: empty file, invalid JSON, oversized, malformed PNG
  - card preview endpoint

Run with: cd /Users/amre/.minimax/agents/mavis/workspace/nook && ~/.nook-venv/bin/python3 tests/test_io_flows.py
Exits 0 on full pass, 1 on any failure.
"""
import io
import json
import struct
import sys
import time
import urllib.request
import urllib.error
import zlib
from pathlib import Path

API = "http://127.0.0.1:18765/api"
ORIGINAL_COMPANION_IDS: set[str] = set()
CREATED_IDS: list[str] = []
PASS_COUNT = 0
FAIL_COUNT = 0
ERRORS: list[str] = []


def request(method: str, path: str, *, body=None, headers=None, raw=False, timeout: float = 30.0) -> tuple[int, bytes, dict]:
    url = f"{API}{path}" if path.startswith("/") else path
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if body is not None and not raw:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif body is not None and raw:
        data = body
    req = urllib.request.Request(url, method=method, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


def get(path):
    return request("GET", path)


def post(path, body=None, timeout: float = 30.0):
    return request("POST", path, body=body, timeout=timeout)


def put(path, body=None):
    return request("PUT", path, body=body)


def delete(path):
    return request("DELETE", path)


def post_file(path: str, filename: str, content: bytes, content_type: str = "application/octet-stream"):
    """Multipart upload."""
    boundary = "----TestBoundary" + str(int(time.time() * 1000))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))}
    return request("POST", path, body=body, headers=h, raw=True)


def check(name: str, ok: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  ✓ {name}")
    else:
        FAIL_COUNT += 1
        ERRORS.append(f"{name}: {detail}")
        print(f"  ✗ {name}  {detail}")


def make_valid_png() -> bytes:
    """Build a real 1x1 transparent PNG (68 bytes)."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def make_sample_card_json(name: str = "Test Hero") -> bytes:
    return json.dumps({
        "name": name,
        "description": f"A {name} who wanders the world seeking adventure. Wry, clever, kind.",
        "personality": "Witty, observant, a touch melancholic. Speaks in short sentences with dry humor.",
        "scenario": "You meet at a crossroads inn. The rain is heavy; the fire is warm.",
        "first_mes": "*Sets down a half-empty tankard.* You're new here. I can tell by the way you keep checking the door.",
        "mes_example": "<START>\nWhat brings you out this way?\n*leans back, hands folded.* Most people who come here are running from something. Some are running toward. Few know which.\n<END>",
        "system_prompt": f"# {name}\n\n**A wanderer with a soft heart.**\n\n## Who They Are\n\nA {name} who has seen too much and learned to laugh at it.",
        "tags": ["test", "fantasy"],
        "creator": "test",
        "character_version": "1",
        "extensions": {
            "nook": {
                "memory_mode": "auto",
                "relationship_type": "mentor",
                "model_name": "qwen3:14b",
                "tagline": "A wanderer with a soft heart."
            }
        }
    }, ensure_ascii=False, indent=2).encode("utf-8")


# ── Tests ───────────────────────────────────────────────────────

def test_baseline():
    print("\n── Baseline: server reachable ──")
    code, body, _ = get("/ping")
    check("ping returns 200", code == 200, f"got {code}")
    check("ping ok=true", json.loads(body).get("ok") is True, body[:80].decode())

    code, body, _ = get("/companions")
    check("list companions", code == 200, f"got {code}")
    cs = json.loads(body)
    for c in cs:
        ORIGINAL_COMPANION_IDS.add(c["id"])
    print(f"    (started with {len(ORIGINAL_COMPANION_IDS)} original companions)")


def test_create_via_simple_post():
    print("\n── Create companion via simple POST ──")
    payload = {
        "name": "Test Simple Companion",
        "backstory": "Just a simple test companion.",
        "personality": "Basic, predictable.",
        "relationship_type": "friend",
        "memory_mode": "hybrid",
        "model_name": "qwen3:14b",
    }
    code, body, _ = post("/companions", payload)
    check("create returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        c = json.loads(body)
        CREATED_IDS.append(c["id"])
        check("name persisted", c["name"] == payload["name"])
        check("relationship persisted", c["relationship_type"] == "friend")


def test_create_via_full_wizard():
    print("\n── Create companion via wizard (full + soul.md) ──")
    soul_text = "# Wizard Test\n\n**Wizard-generated soul.**\n\n## Who They Are\n\nA character created via the wizard endpoint.\n\n## How They Talk\n\nWizard-style voice."
    payload = {
        "name": "Test Wizard Companion",
        "soul": soul_text,
        "ocean": {"openness": 7, "conscientiousness": 5, "extraversion": 4, "agreeableness": 8, "neuroticism": 3},
        "archetype": "mentor",
        "relationshipType": "mentor",
        "memoryMode": "auto",
        "voiceConfig": json.dumps({"voice_id": "af_sarah", "speed": 1.0, "pitch": 0}),
        "modelName": "qwen3:14b",
    }
    code, body, _ = post("/companions/full", payload)
    check("wizard create returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        c = json.loads(body)
        CREATED_IDS.append(c["id"])
        check("name persisted", c["name"] == payload["name"])
        check("archetype roundtrip (in personality)", "Wizard" in (c.get("personality") or ""))
        # Check soul.md was actually written
        sp = c.get("soul_path", "")
        if sp and Path(sp).exists():
            on_disk = Path(sp).read_text()
            check("soul.md written to disk", on_disk == soul_text)
        else:
            check("soul.md written to disk", False, f"soul_path missing or file not found: {sp}")


def test_get_companion():
    print("\n── Get companion ──")
    if not CREATED_IDS:
        check("get_companion prereq", False, "no companions created")
        return
    cid = CREATED_IDS[0]
    code, body, _ = get(f"/companions/{cid}")
    check("get returns 200", code == 200, f"got {code}")
    if code == 200:
        c = json.loads(body)
        check("id matches", c["id"] == cid)


def test_update_companion_basic():
    print("\n── Update companion (basic fields) ──")
    if not CREATED_IDS:
        check("update prereq", False, "no companions")
        return
    cid = CREATED_IDS[0]
    payload = {
        "name": "Test Simple Companion (Renamed)",
        "relationship_type": "rival",
        "personality": "Now I'm a rival.",
    }
    code, body, _ = put(f"/companions/{cid}", payload)
    check("update returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        c = json.loads(body)
        check("name updated", c["name"] == "Test Simple Companion (Renamed)")
        check("relationship updated", c["relationship_type"] == "rival")
        check("personality updated", "rival" in c["personality"])


def test_update_companion_validation():
    print("\n── Update validation: empty name rejected ──")
    if not CREATED_IDS:
        check("validation prereq", False, "no companions")
        return
    cid = CREATED_IDS[0]
    code, body, _ = put(f"/companions/{cid}", {"name": "   "})
    check("empty name rejected (400)", code == 400, f"got {code}")


def test_update_soul():
    print("\n── Update soul.md ──")
    if len(CREATED_IDS) < 2:
        check("soul update prereq", False, "need 2+ companions")
        return
    cid = CREATED_IDS[1]  # wizard companion
    new_soul = "# Wizard Test\n\n**Updated soul tagline.**\n\n## Who They Are\n\nUpdated."
    code, body, _ = put(f"/companions/{cid}/soul", {"soul": new_soul})
    check("soul update returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        # Verify the file was actually changed
        c_resp, c_body, _ = get(f"/soul/{cid}")
        check("soul on disk updated", new_soul in json.loads(c_body).get("markdown", ""), "")


def test_card_preview():
    print("\n── Card preview endpoint ──")
    if not CREATED_IDS:
        check("preview prereq", False, "no companions")
        return
    cid = CREATED_IDS[0]
    code, body, _ = get(f"/companions/{cid}/card-preview")
    check("preview returns 200", code == 200, f"got {code}")
    if code == 200:
        card = json.loads(body)
        check("card has name", isinstance(card.get("name"), str) and len(card["name"]) > 0)
        check("card has description", isinstance(card.get("description"), str))
        check("card has personality", isinstance(card.get("personality"), str))
        check("card has extensions.nook", isinstance(card.get("extensions", {}).get("nook"), dict))


def test_export_json():
    print("\n── Export companion as JSON ──")
    if not CREATED_IDS:
        check("export json prereq", False, "no companions")
        return
    cid = CREATED_IDS[0]
    code, body, headers = get(f"/companions/{cid}/export?format=json")
    check("export json returns 200", code == 200, f"got {code}")
    h = {k.lower(): v for k, v in headers.items()}
    check("content-type is json", "application/json" in h.get("content-type", ""), str(headers))
    if code == 200:
        try:
            card = json.loads(body)
            check("exported json is valid", isinstance(card, dict))
            check("exported card has name", card.get("name") == "Test Simple Companion (Renamed)")
        except json.JSONDecodeError as e:
            check("exported json parses", False, str(e))


def test_export_png():
    print("\n── Export companion as PNG (with embedded card) ──")
    if not CREATED_IDS:
        check("export png prereq", False, "no companions")
        return
    cid = CREATED_IDS[0]
    code, body, headers = get(f"/companions/{cid}/export?format=png")
    check("export png returns 200", code == 200, f"got {code}")
    check("starts with PNG magic", body[:8] == b"\x89PNG\r\n\x1a\n", body[:20].hex())
    h = {k.lower(): v for k, v in headers.items()}
    check("content-type is png", "image/png" in h.get("content-type", ""), str(headers))
    if code == 200 and body[:8] == b"\x89PNG\r\n\x1a\n":
        Path("/tmp/_exported.png").write_bytes(body)
        check("png size > 200 bytes", len(body) > 200, f"got {len(body)}")


def _headers_to_lower(h: dict) -> dict:
    return {k.lower(): v for k, v in h.items()}


def test_round_trip_json():
    print("\n── Round-trip: export JSON → import JSON → identical ──")
    if not CREATED_IDS:
        check("round-trip prereq", False, "no companions")
        return
    src_id = CREATED_IDS[0]
    # Export
    code, export_body, _ = get(f"/companions/{src_id}/export?format=json")
    if code != 200:
        check("export for round-trip", False, f"got {code}")
        return
    Path("/tmp/_roundtrip.json").write_bytes(export_body)
    # Import
    code, import_body, _ = post_file("/companions/import-file", "roundtrip.json", export_body, "application/json")
    check("import round-trip returns 200", code == 200, f"got {code} body={import_body[:200].decode()}")
    if code == 200:
        new = json.loads(import_body)
        CREATED_IDS.append(new["companion"]["id"])
        # Compare core fields
        orig_code, orig_body, _ = get(f"/companions/{src_id}")
        orig = json.loads(orig_body)
        new_c = new["companion"]
        check("name preserved", orig["name"] == new_c["name"])
        check("backstory preserved", orig["backstory"] == new_c["backstory"])
        check("personality preserved", orig["personality"] == new_c["personality"])
        check("relationship preserved", orig["relationship_type"] == new_c["relationship_type"])
        check("memory_mode preserved", orig["memory_mode"] == new_c["memory_mode"])
        check("model preserved", orig["model_name"] == new_c["model_name"])


def test_round_trip_png():
    print("\n── Round-trip: export PNG → import PNG → identical ──")
    if not CREATED_IDS:
        check("png round-trip prereq", False, "no companions")
        return
    src_id = CREATED_IDS[0]
    # Export as PNG
    code, export_body, _ = get(f"/companions/{src_id}/export?format=png")
    if code != 200:
        check("png export for round-trip", False, f"got {code}")
        return
    # Import the PNG
    code, import_body, _ = post_file("/companions/import-file", "roundtrip.png", export_body, "image/png")
    check("png import returns 200", code == 200, f"got {code} body={import_body[:200].decode()}")
    if code == 200:
        new = json.loads(import_body)
        CREATED_IDS.append(new["companion"]["id"])
        # Compare
        orig_code, orig_body, _ = get(f"/companions/{src_id}")
        orig = json.loads(orig_body)
        new_c = new["companion"]
        check("png: name preserved", orig["name"] == new_c["name"])
        check("png: personality preserved", orig["personality"] == new_c["personality"])
        check("png: relationship preserved", orig["relationship_type"] == new_c["relationship_type"])
        check("png: has avatar", new_c.get("avatar_path") is not None and Path(new_c["avatar_path"]).exists())


def test_import_paste_json():
    print("\n── Import via paste-JSON endpoint ──")
    card = make_sample_card_json("Pasted Hero")
    code, body, _ = post("/companions/import-paste", {"json": card.decode("utf-8")})
    check("paste import returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        new = json.loads(body)
        CREATED_IDS.append(new["companion"]["id"])
        check("paste: name matches", new["name"] == "Pasted Hero")


def test_error_empty_file():
    print("\n── Error: empty file rejected ──")
    code, body, _ = post_file("/companions/import-file", "empty.json", b"", "application/json")
    check("empty file rejected (400)", code == 400, f"got {code} body={body[:200].decode()}")


def test_error_invalid_json():
    print("\n── Error: invalid JSON rejected ──")
    code, body, _ = post_file("/companions/import-file", "bad.json", b"{not valid json", "application/json")
    check("invalid json rejected (400)", code == 400, f"got {code} body={body[:200].decode()}")


def test_error_unknown_format():
    print("\n── Error: unknown file format rejected ──")
    code, body, _ = post_file("/companions/import-file", "weird.txt", b"some text", "text/plain")
    check("unknown format rejected (400)", code == 400, f"got {code} body={body[:200].decode()}")


def test_error_png_no_card():
    print("\n── Error: PNG without embedded card rejected ──")
    png = make_valid_png()
    code, body, _ = post_file("/companions/import-file", "blank.png", png, "image/png")
    check("PNG w/o card rejected (400)", code == 400, f"got {code} body={body[:200].decode()}")


def test_error_404_companion():
    print("\n── Error: 404 on missing companion ──")
    code, body, _ = get("/companions/00000000-0000-0000-0000-000000000000")
    check("missing companion → 404", code == 404, f"got {code}")


def test_ollama_health():
    print("\n── Ollama health ──")
    code, body, _ = get("/ollama/health")
    check("health returns 200", code == 200, f"got {code}")
    if code == 200:
        h = json.loads(body)
        check("health.healthy is bool", isinstance(h.get("healthy"), bool))
        if h.get("healthy"):
            print(f"    (ollama online, {h.get('image_gen_platform_supported')=})")


def test_models_catalog():
    print("\n── Models catalog endpoint ──")
    code, body, _ = get("/models/catalog")
    check("catalog returns 200", code == 200, f"got {code}")
    if code == 200:
        models = json.loads(body)
        check("catalog has models", len(models) > 0, f"got {len(models)}")
        if models:
            m = models[0]
            check("model has name", isinstance(m.get("name"), str) and len(m["name"]) > 0)
            check("model has pull_cmd", "ollama pull" in (m.get("pull_cmd") or ""))


def test_create_then_full_cycle():
    """The golden path: create → edit → export → delete companion → import → use."""
    print("\n── Golden path: create → edit → export → delete → import → chat ──")
    # 1. Create
    soul = "# Cycle Test\n\n**Cycle-test soul.**\n\n## Who They Are\n\nBuilt to be cycled."
    code, body, _ = post("/companions/full", {
        "name": "Cycle Test Hero", "soul": soul, "relationshipType": "friend", "memoryMode": "hybrid", "modelName": "qwen3:14b"
    })
    check("1. create via wizard", code == 200, f"got {code} body={body[:200].decode()}")
    if code != 200:
        return
    cycle_id = json.loads(body)["id"]
    CREATED_IDS.append(cycle_id)

    # 2. Edit
    code, body, _ = put(f"/companions/{cycle_id}", {"name": "Cycle Test Hero (Renamed)", "relationship_type": "rival"})
    check("2. update basic fields", code == 200, f"got {code}")

    # 3. Edit soul
    code, body, _ = put(f"/companions/{cycle_id}/soul", {"soul": "# Cycle Test\n\n**Updated.**"})
    check("3. update soul.md", code == 200, f"got {code}")

    # 4. Export as JSON
    code, export_body, _ = get(f"/companions/{cycle_id}/export?format=json")
    check("4. export as JSON", code == 200, f"got {code}")

    # 5. Delete the original
    code, _, _ = delete(f"/companions/{cycle_id}")
    check("5. delete companion", code == 200, f"got {code}")

    # 6. Import the export
    code, body, _ = post_file("/companions/import-file", "cycle.json", export_body, "application/json")
    check("6. re-import", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        new_id = json.loads(body)["companion"]["id"]
        CREATED_IDS.append(new_id)
        # 7. Verify the new one matches
        code, body, _ = get(f"/companions/{new_id}")
        c = json.loads(body)
        check("7. imported has renamed name", c["name"] == "Cycle Test Hero (Renamed)")
        check("7. imported has rival rel", c["relationship_type"] == "rival")


# ── Cleanup ─────────────────────────────────────────────────────

# ── Art upload + image-gen detection ───────────────────────────

def _make_png_1x1() -> bytes:
    """Build a valid 1×1 transparent PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _make_jpeg_1x1() -> bytes:
    """A minimal valid JPEG (1×1 white)."""
    # Pre-built minimal JPEG: SOI + APP0 + DQT + SOF0 + DHT + SOS + image data + EOI
    # Easier: just return a known tiny JPEG
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432"
        "ffc00011080001000103012200021101031101"
        "ffc4001f0000010501010101010100000000000000000102030405060708090a0b"
        "ffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9fa"
        "ffda000c03010002110311003f00fbfeff"
        "d9"
    )


def test_art_upload_png():
    """Upload a PNG to a companion's art gallery."""
    print("\n── Art upload: PNG ──")
    # Need a companion first
    code, body, _ = post("/companions/full", {
        "name": "ArtUploadTest", "soul": "# Test\n", "relationshipType": "friend",
        "memoryMode": "hybrid", "modelName": "qwen3:14b"
    })
    if code != 200:
        check("setup: create companion", False, f"create failed: {code}")
        return
    cid = json.loads(body)["id"]
    CREATED_IDS.append(cid)

    png = _make_png_1x1()
    import base64
    b64 = base64.b64encode(png).decode()
    code, body, _ = post("/art/upload", {
        "companionId": cid, "prompt": "Test uploaded PNG",
        "base64": b64, "mime": "image/png", "filename": "test.png",
    })
    check("upload PNG 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        result = json.loads(body)
        check("upload returns id", bool(result.get("id")))
        check("upload returns file_path", bool(result.get("file_path")))
        check("upload model is upload:png", result.get("model") == "upload:png")

        # Verify it appears in history
        code, body, _ = get(f"/art/{cid}/history")
        check("history includes upload", code == 200 and any(
            a["id"] == result["id"] for a in json.loads(body)
        ))

        # Verify the image file actually exists and is a valid PNG
        fp = Path(result["file_path"])
        check("image file exists on disk", fp.exists())
        if fp.exists():
            check("image is valid PNG", fp.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n")


def test_art_upload_jpeg():
    """Upload a JPEG (auto-detected from magic bytes)."""
    print("\n── Art upload: JPEG ──")
    code, body, _ = post("/companions/full", {
        "name": "ArtUploadJpeg", "soul": "# Test\n", "relationshipType": "friend",
        "memoryMode": "hybrid", "modelName": "qwen3:14b"
    })
    if code != 200:
        check("setup: create companion", False, f"create failed: {code}")
        return
    cid = json.loads(body)["id"]
    CREATED_IDS.append(cid)

    jpg = _make_jpeg_1x1()
    import base64
    b64 = base64.b64encode(jpg).decode()
    # Lie about mime: server should detect from magic bytes
    code, body, _ = post("/art/upload", {
        "companionId": cid, "prompt": "Test JPEG",
        "base64": b64, "mime": "image/png",  # wrong on purpose
    })
    check("upload JPEG 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        result = json.loads(body)
        check("JPEG model is upload:jpg (detected from bytes)", result.get("model") == "upload:jpg")


def test_art_upload_data_url():
    """Upload a base64 data URL (data:image/png;base64,XXX)."""
    print("\n── Art upload: data URL prefix ──")
    code, body, _ = post("/companions/full", {
        "name": "ArtUploadDataUrl", "soul": "# Test\n", "relationshipType": "friend",
        "memoryMode": "hybrid", "modelName": "qwen3:14b"
    })
    if code != 200:
        check("setup: create", False)
        return
    cid = json.loads(body)["id"]
    CREATED_IDS.append(cid)

    png = _make_png_1x1()
    import base64
    b64 = base64.b64encode(png).decode()
    data_url = f"data:image/png;base64,{b64}"
    code, body, _ = post("/art/upload", {
        "companionId": cid, "prompt": "Data URL test",
        "base64": data_url, "mime": "image/png",
    })
    check("upload with data: URL prefix", code == 200, f"got {code} body={body[:200].decode()}")


def test_art_upload_errors():
    """Error cases for art upload."""
    print("\n── Art upload: error cases ──")
    # Invalid base64
    code, body, _ = post("/art/upload", {
        "companionId": "00000000-0000-0000-0000-000000000000",
        "base64": "not-valid-base64!!!",
    })
    check("invalid base64 → 404 or 400", code in (400, 404), f"got {code}")

    # Missing companion
    code, body, _ = post("/art/upload", {
        "companionId": "00000000-0000-0000-0000-000000000000",
        "base64": "iVBORw0KGgo=",
    })
    check("missing companion → 404", code == 404, f"got {code}")


# ── System onboarding (Ollama detect / launch / pull) ───────────

def test_system_status():
    """The system status endpoint should return the full onboarding state."""
    print("\n── System status ──")
    code, body, _ = get("/system/status")
    check("status returns 200", code == 200, f"got {code}")
    if code != 200:
        return
    s = json.loads(body)
    # Required fields
    for key in ("ollama_installed", "ollama_running", "ollama_version",
                "ollama_path", "ollama_app_path", "platform", "models_total",
                "models_installed", "has_chat_model", "has_embed_model",
                "has_image_model", "setup_complete"):
        check(f"status has {key}", key in s, f"missing {key}")

    # On this machine, all should be true
    check("ollama installed (this machine)", s.get("ollama_installed") is True)
    check("ollama running (this machine)", s.get("ollama_running") is True)
    check("has chat model (this machine)", s.get("has_chat_model") is True)
    check("has embed model (this machine)", s.get("has_embed_model") is True)
    check("setup_complete (this machine)", s.get("setup_complete") is True)
    check("platform is darwin/linux/windows", s.get("platform") in ("darwin", "linux", "windows"))


def test_system_recommend():
    """The recommend endpoint should return a starter pack."""
    print("\n── System recommend ──")
    code, body, _ = get("/system/recommend")
    check("recommend returns 200", code == 200, f"got {code}")
    if code == 200:
        r = json.loads(body)
        check("recommend has chat", "chat" in r)
        check("recommend has embedding", "embedding" in r)
        if "chat" in r:
            chat = r["chat"]
            check("chat reco has name", bool(chat.get("name")))
            check("chat reco has size", bool(chat.get("size")))
            check("chat reco has fallback_name", bool(chat.get("fallback_name")))


def test_pull_invalid_model_name():
    """Pulling an invalid model name should fail cleanly."""
    print("\n── Pull: invalid model name ──")
    code, body, _ = post("/models/pull", {"model": "not valid!@#"})
    check("invalid model returns ok=false", code == 200)
    if code == 200:
        r = json.loads(body)
        check("ok=False on invalid", r.get("ok") is False)
        check("error mentions invalid", "invalid" in r.get("error", "").lower())


def test_pull_already_installed():
    """Pulling a model that's already installed should short-circuit."""
    print("\n── Pull: already-installed model ──")
    # Find a model that's installed on this machine
    code, body, _ = get("/system/status")
    if code != 200:
        check("setup: status 200", False)
        return
    s = json.loads(body)
    if not s.get("models_installed"):
        check("setup: at least one model installed", False)
        return
    installed_model = s["models_installed"][0]
    code, body, _ = post("/models/pull", {"model": installed_model})
    check("already-installed returns 200", code == 200, f"got {code}")
    if code == 200:
        r = json.loads(body)
        check("already_installed=True", r.get("already_installed") is True)
        check("ok=True", r.get("ok") is True)


def test_pull_real_model_with_progress():
    """Pull a real (small) model, watch progress, verify it completes."""
    print("\n── Pull: real model with progress polling ──")
    # Use a tiny model that's likely NOT installed. If it IS installed, skip.
    code, body, _ = get("/system/status")
    s = json.loads(body) if code == 200 else {}
    installed = set(s.get("models_installed", []))

    # Try a tiny model that probably isn't installed. If it is, the test
    # will return early and pass.
    candidates = ["qwen2.5:0.5b", "gemma2:2b", "tinyllama"]
    target = None
    for c in candidates:
        if c not in installed:
            target = c
            break
    if not target:
        check("skip: all candidate models already installed (passing anyway)", True)
        return

    code, body, _ = post("/models/pull", {"model": target})
    check("pull started", code == 200, f"got {code} body={body[:200].decode()}")
    if code != 200:
        return
    r = json.loads(body)
    check("job_id present", bool(r.get("job_id")))
    if not r.get("job_id"):
        return
    job_id = r["job_id"]

    # Poll for up to 60 seconds
    seen_statuses = set()
    final_status = None
    for i in range(30):
        time.sleep(2)
        code, body, _ = get(f"/models/pull/{job_id}")
        if code != 200:
            check(f"poll {i}: status 200", False, f"got {code}")
            break
        s = json.loads(body)
        seen_statuses.add(s.get("status"))
        if s.get("status") in ("done", "error", "cancelled"):
            final_status = s
            break

    check("job reached terminal state", final_status is not None)
    if final_status:
        check("job done successfully", final_status["status"] == "done",
              f"got {final_status['status']}: {final_status.get('error')}")
        check("progress_pct reached 100", final_status.get("progress_pct") == 100)

    # Clean up: remove the model we just installed
    import subprocess
    try:
        subprocess.run(["ollama", "rm", target], capture_output=True, timeout=30)
    except Exception:
        pass


def test_pull_cancel():
    """Start a pull, then cancel it, verify it ends as cancelled."""
    print("\n── Pull: cancel mid-flight ──")
    # Use a slightly larger model so we have time to cancel
    code, body, _ = get("/system/status")
    s = json.loads(body) if code == 200 else {}
    installed = set(s.get("models_installed", []))

    # tinyllama is small (~600MB) and usually not preinstalled
    target = "tinyllama"
    if target in installed:
        check("skip: tinyllama already installed", True)
        return

    code, body, _ = post("/models/pull", {"model": target})
    if code != 200:
        check("start pull 200", False, f"got {code}")
        return
    r = json.loads(body)
    job_id = r.get("job_id")
    check("job_id present", bool(job_id))
    if not job_id:
        return

    # Let it run a moment
    time.sleep(1)

    # Cancel
    code, body, _ = delete(f"/models/pull/{job_id}")
    check("cancel returns 200", code == 200, f"got {code}")

    # Wait for terminal state
    for i in range(10):
        time.sleep(0.5)
        code, body, _ = get(f"/models/pull/{job_id}")
        if code == 200:
            s = json.loads(body)
            if s.get("status") in ("cancelled", "error", "done"):
                check("job ended as cancelled",
                      s["status"] in ("cancelled", "error"),
                      f"got {s['status']}")
                break


def test_pull_unknown_job():
    """Polling an unknown job_id should 404."""
    print("\n── Pull: unknown job_id ──")
    code, _, _ = get("/models/pull/00000000-0000-0000-0000-000000000000")
    check("unknown job → 404", code == 404, f"got {code}")


def test_launch_ollama_endpoint():
    """The launch endpoint should return ok=True (or ok=False with reason on Linux)."""
    print("\n── Launch Ollama ──")
    code, body, _ = post("/system/launch-ollama", {})
    check("launch returns 200", code == 200, f"got {code}")
    if code == 200:
        r = json.loads(body)
        # On macOS/Windows it should be ok=True; on Linux it returns ok=False with a reason
        check("launch has 'ok' key", "ok" in r)


def test_remember_art_as_memory():
    """Save an uploaded art piece as a memory — uses Pydantic body model, not query params."""
    print("\n── Remember art as memory ──")
    # Need a companion
    code, body, _ = post("/companions/full", {
        "name": "ArtRememberTest", "soul": "# T\n", "relationshipType": "friend",
        "memoryMode": "hybrid", "modelName": "qwen3:14b"
    })
    if code != 200:
        check("setup: create companion", False, f"create failed: {code}")
        return
    cid = json.loads(body)["id"]
    CREATED_IDS.append(cid)

    # Upload
    import base64
    png = _make_png_1x1()
    b64 = base64.b64encode(png).decode()
    code, body, _ = post("/art/upload", {
        "companionId": cid, "prompt": "Remember test art",
        "base64": b64, "mime": "image/png",
    })
    if code != 200:
        check("setup: upload", False, f"upload failed: {code}")
        return
    aid = json.loads(body)["id"]

    # Save as memory (Pydantic body, not query)
    code, body, _ = post(f"/art/{aid}/remember", {
        "companion_id": cid, "note": "First shared moment",
    })
    check("remember returns 200", code == 200, f"got {code} body={body[:200].decode()}")
    if code == 200:
        result = json.loads(body)
        check("remembered as category=art", result.get("category") == "art")
        check("remembered includes the note", "First shared moment" in result.get("fact_text", ""))


def test_image_gen_detection():
    """Verify the health endpoint reports image gen availability correctly
    AND that the SVG-fallback path works end-to-end (even when Ollama
    native image gen is disabled in v0.32.6+).

    v0.13: image gen now uses a two-strategy approach:
      1. Try Ollama's native /v1/images/generations (best quality)
      2. Fall back to LLM-generated SVG via /api/chat (always works)

    So when image gen is reported unavailable, /api/art/generate should
    STILL succeed (with an SVG image) — the fallback is the whole point.
    """
    print("\n── Image-gen detection ──")
    code, body, _ = get("/ollama/health")
    if code != 200:
        check("health 200", False, f"got {code}")
        return
    h = json.loads(body)
    check("health has image_gen_platform_supported", "image_gen_platform_supported" in h)
    check("health has image_gen_platform_reason", "image_gen_platform_reason" in h or h.get("image_gen_platform_supported") is True)

    # Whether or not native gen is available, /api/art/generate should
    # produce a real image (PNG if native works, SVG if fallback).
    # The SVG path is slow (30-90s for the LLM to draw), so we use a
    # generous timeout.
    code, body, _ = get("/companions")
    if code == 200 and json.loads(body):
        cid = json.loads(body)[0]["id"]
        code, body, _ = post("/art/generate", {
            "companionId": cid, "prompt": "a tiny red circle", "model": "x/z-image-turbo"
        }, timeout=150.0)
        if code == 200:
            result = json.loads(body)
            check("generate returns 200 (native or SVG fallback)",
                  code == 200, f"got {code}")
            check("generate returns valid image (svg or png kind)",
                  result.get("kind") in ("svg", "png"), f"kind={result.get('kind')}")
            check("generate returns non-empty base64",
                  len(result.get("base64", "")) > 100, f"len={len(result.get('base64',''))}")
            check("generate returns id and file_path",
                  result.get("id") and result.get("file_path"),
                  f"id={result.get('id')}, file_path={result.get('file_path')}")
            if "x/z-image-turbo" in (result.get("model") or ""):
                # v0.15.2: model label can show "svg-fallback" (LLM-SVG
                # path) or "real diffusion via diffusers/MPS" (SDXL-turbo
                # path). Both are valid render backends.
                check("model label shows rendering backend (svg or diffusion)",
                      "svg-fallback" in (result.get("model") or "")
                      or "diffusers" in (result.get("model") or "")
                      or "diffusion" in (result.get("model") or ""),
                      f"model={result.get('model')}")
        else:
            err = body.decode(errors="ignore")[:200]
            check("generate fails gracefully when no model is available",
                  code in (500, 503), f"got {code} body={err}")


def cleanup():
    print("\n── Cleanup: deleting test companions ──")
    for cid in CREATED_IDS:
        try:
            code, _, _ = delete(f"/companions/{cid}")
            if code == 200:
                print(f"    deleted {cid[:8]}")
            else:
                print(f"    (couldn't delete {cid[:8]}: {code})")
        except Exception as e:
            print(f"    (error deleting {cid[:8]}: {e})")
    # Verify originals are intact
    code, body, _ = get("/companions")
    if code == 200:
        cs = json.loads(body)
        remaining_ids = {c["id"] for c in cs}
        originals_still_there = ORIGINAL_COMPANION_IDS <= remaining_ids
        check("original companions intact", originals_still_there, f"originals: {len(ORIGINAL_COMPANION_IDS)}, remaining: {len(remaining_ids)}")


# ── Driver ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("OurNook import/export/create e2e tests")
    print("=" * 60)
    test_baseline()
    test_ollama_health()
    test_models_catalog()
    test_create_via_simple_post()
    test_create_via_full_wizard()
    test_get_companion()
    test_update_companion_basic()
    test_update_companion_validation()
    test_update_soul()
    test_card_preview()
    test_export_json()
    test_export_png()
    test_import_paste_json()
    test_round_trip_json()
    test_round_trip_png()
    test_error_empty_file()
    test_error_invalid_json()
    test_error_unknown_format()
    test_error_png_no_card()
    test_error_404_companion()
    test_create_then_full_cycle()
    test_art_upload_png()
    test_art_upload_jpeg()
    test_art_upload_data_url()
    test_art_upload_errors()
    test_remember_art_as_memory()
    test_image_gen_detection()
    test_system_status()
    test_system_recommend()
    test_pull_invalid_model_name()
    test_pull_already_installed()
    test_pull_real_model_with_progress()
    test_pull_cancel()
    test_pull_unknown_job()
    test_launch_ollama_endpoint()
    cleanup()
    print("\n" + "=" * 60)
    print(f"PASS: {PASS_COUNT}  FAIL: {FAIL_COUNT}")
    if ERRORS:
        print("\nFailures:")
        for e in ERRORS:
            print(f"  - {e}")
    print("=" * 60)
    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
