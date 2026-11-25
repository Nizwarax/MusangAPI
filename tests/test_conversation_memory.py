"""Run: venv/bin/python tests/test_conversation_memory.py

Kesinambungan lintas akun tanpa kuota: giliran 1 dipaksa ke akun A, giliran 2 ("lanjutkan") ke akun B.
Bukti = byte acuan yang diterima engine di giliran 2 sama dengan frame terakhir video giliran 1.
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-memory-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402


async def request(method, path, body=None):
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "server": ("test", 80), "client": ("test", 1),
             "headers": [(b"authorization", b"Bearer test-only"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(payload)).encode())]}

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    await app.app(scope, receive, send)
    return json.loads(b"".join(m.get("body", b"") for m in messages))


calls = []


def fake_generate(cookies, prompt, expect="image", timeout=0, expires=None, account_id=None,
                  on_progress=None, reference_image=None, reference_images=None):
    calls.append({"account": account_id, "prompt": prompt, "refs": reference_images or ([reference_image] if reference_image else [])})
    name = f"fake{len(calls)}.mp4"
    # Video asli kecil supaya ffmpeg benar-benar mengambil frame terakhir.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=8:duration=1",
                    "-pix_fmt", "yuv420p", os.path.join(app.CFG.media_dir, name)], check=True)
    return {"filename": name, "size": 1, "kind": "video"}


def run_video(prompt):
    tid = asyncio.run(request("POST", "/v1/videos", {"prompt": prompt, "conversation_id": "conv_1"}))["id"]
    for _ in range(200):
        t = app.store.get_task(tid)
        if t["status"] in ("completed", "failed"):
            assert t["status"] == "completed", t.get("error")
            return t
        time.sleep(0.05)
    raise AssertionError("task tidak selesai")


os.makedirs(app.CFG.media_dir, exist_ok=True)
a = app.store.add_account({"hatch_sess": "a"}, label="A")
b = app.store.add_account({"hatch_sess": "b"}, label="B")
enable = lambda aid, on: app.store.update_account(aid, enabled=on)

with patch.object(app, "_renew_and_persist", lambda aid, **k: app.store.get_account(aid)), \
        patch.object(app, "_sync_cookies", lambda aid: {}), patch.object(app, "_bind_account_proxy", lambda acc: None), \
        patch.object(app.engine, "start", lambda: None), patch.object(app.engine, "generate", fake_generate):
    enable(b["id"], False)
    run_video("Dashcam di tol Semarang, kabut tipis, 10 seconds")
    assert calls[-1]["account"] == a["id"] and not calls[-1]["refs"]
    assert "时长严格为 10 秒" in calls[-1]["prompt"]

    enable(b["id"], True); enable(a["id"], False)          # akun A sibuk/diblokir -> harus pindah ke B
    run_video("lanjutkan, sekarang mobilnya keluar gerbang tol")
    turn2 = calls[-1]
    assert turn2["account"] == b["id"], turn2["account"]
    frame = open(os.path.join(app.CFG.media_dir, "fake1_last.png"), "rb").read()
    sent = base64.b64decode(turn2["refs"][0].split(",", 1)[1])
    assert sent == frame, "acuan giliran 2 bukan frame terakhir giliran 1"
    assert "连续性要求" in turn2["prompt"] and "Dashcam di tol Semarang" in turn2["prompt"]

    enable(a["id"], True)                                    # dua akun sehat -> tetap di akun terakhir (B)
    run_video("lanjutkan adegan berikutnya, matahari mulai naik")
    assert calls[-1]["account"] == b["id"], calls[-1]["account"]
    assert base64.b64decode(calls[-1]["refs"][0].split(",", 1)[1]) == open(
        os.path.join(app.CFG.media_dir, "fake2_last.png"), "rb").read()

    run_video("Kucing tidur di jendela, 5 seconds")          # bukan lanjutan -> tanpa acuan/konteks
    assert not calls[-1]["refs"] and "连续性要求" not in calls[-1]["prompt"]

print(f"PASS: lanjutan lintas akun (A->B), byte frame terakhir {len(frame)} B cocok, akun lengket, non-lanjutan bersih")
