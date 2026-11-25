"""Run: venv/bin/python tests/test_chat_disconnect.py — klien memutus stream (tombol Hentikan) menghentikan muse.

Bug di HP (satu akun): Hentikan saat muse belum menulis kata pertama tidak sampai ke engine, sehingga muse
menulis jawaban 800 kata sampai selesai dan semua pesan berikutnya antre di belakangnya.
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-disconnect-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402

stopped = threading.Event()
started = threading.Event()


def slow_chat_stream(cookies, prompt, expires=None, timeout=None, account_id=None, stop_event=None, images=None):
    """Seperti muse yang masih 'berpikir': belum ada kata pertama, hanya memeriksa stop_event."""
    started.set()
    deadline = time.time() + 8
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            stopped.set()
            return
        time.sleep(0.05)
    yield "terlambat"


async def call_then_disconnect(after: float):
    body = json.dumps({"model": "muse-spark", "stream": True,
                       "messages": [{"role": "user", "content": "cerita panjang"}]}).encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/v1/chat/completions", "raw_path": b"/v1/chat/completions", "query_string": b"",
             "root_path": "", "server": ("t", 80), "client": ("t", 1),
             "headers": [(b"authorization", b"Bearer test-only"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(body)).encode())]}
    sent = []

    async def receive():
        if not sent:
            sent.append(1)
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(after)
        return {"type": "http.disconnect"}

    async def send(_m):
        pass

    await asyncio.wait_for(app.app(scope, receive, send), timeout=15)


app.store.add_account({"hatch_sess": "a"}, label="A")
with patch.object(app, "_renew_and_persist", lambda aid, **k: app.store.get_account(aid)), \
     patch.object(app, "_sync_cookies", lambda aid: {}), patch.object(app, "_bind_account_proxy", lambda acc: None), \
     patch.object(app.engine, "start", lambda: None), patch.object(app.engine, "chat_stream", slow_chat_stream), \
     patch.object(app.engine, "close_current_page"), patch.object(app.engine, "reset_thread"):
    t0 = time.time()
    asyncio.run(call_then_disconnect(after=1.0))
    assert started.wait(5), "engine tidak pernah dipanggil"
    assert stopped.wait(3), "stop_event tidak di-set setelah klien putus: muse terus menulis dan akun tertahan"
    print(f"ok: engine berhenti {time.time() - t0:.1f}s setelah permintaan (klien putus di 1,0s)")


def quick_chat_stream(cookies, prompt, expires=None, timeout=None, account_id=None, stop_event=None, images=None):
    yield "oke"


async def call_full():
    body = json.dumps({"model": "muse-spark", "stream": True, "messages": [{"role": "user", "content": "x"}]}).encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/v1/chat/completions", "raw_path": b"/v1/chat/completions", "query_string": b"",
             "root_path": "", "server": ("t", 80), "client": ("t", 1),
             "headers": [(b"authorization", b"Bearer test-only"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(body)).encode())]}
    sent, out = [], []

    async def receive():
        if not sent:
            sent.append(1)
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(3600)

    async def send(m):
        out.append(m.get("body", b""))
    await asyncio.wait_for(app.app(scope, receive, send), timeout=15)
    return b"".join(out).decode()


# Stream yang selesai normal tetap harus ditutup finish_reason=stop + [DONE] (UI menandai "terputus" tanpa itu).
with patch.object(app, "_renew_and_persist", lambda aid, **k: app.store.get_account(aid)), \
     patch.object(app, "_sync_cookies", lambda aid: {}), patch.object(app, "_bind_account_proxy", lambda acc: None), \
     patch.object(app.engine, "start", lambda: None), patch.object(app.engine, "chat_stream", quick_chat_stream), \
     patch.object(app.engine, "close_current_page"), patch.object(app.engine, "reset_thread"):
    text = asyncio.run(call_full())
    assert '"content": "oke"' in text and '"finish_reason": "stop"' in text and text.rstrip().endswith("data: [DONE]"), text[-300:]
    print("ok: stream normal diakhiri finish_reason=stop dan [DONE]")
print("test_chat_disconnect OK")
