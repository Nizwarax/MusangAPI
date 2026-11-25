"""Run: venv/bin/python tests/test_chat_images.py — pertanyaan tentang isi gambar di chat (tanpa muse.ai).

1. engine.chat_stream: gambar dilampirkan SEBELUM prompt dikirim, folder sementara dihapus walau stream gagal.
2. /v1/chat/completions: image_url di pesan user terakhir sampai ke engine byte-identik; riwayat tidak ikut.
"""
import asyncio
import base64
import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-chatimg-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402
from engine import MuseEngine, MuseGenerationError  # noqa: E402

png_path = os.path.join(HOME.name, "q.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48", "-frames:v", "1", png_path], check=True)
PNG = open(png_path, "rb").read()
DATA = "data:image/png;base64," + base64.b64encode(PNG).decode()

# ---- 1. engine ----
eng = MuseEngine(SimpleNamespace(profile_dir=HOME.name, chat_timeout=5))
order, polls = [], itertools.chain([(0, "", False)], itertools.repeat((1, "Ini pola warna uji.", False)))
upload_dir = tempfile.mkdtemp(dir=HOME.name)
eng.ensure_page = lambda *a, **k: None
eng.reset_thread = lambda **k: None
eng._poll_chat = lambda: next(polls)
eng._attach_images = lambda imgs: order.append(("attach", imgs)) or {"dir": upload_dir, "hashes": set()}
eng._send = lambda p: order.append(("send", p)) or "clicked"
out = "".join(eng.chat_stream({}, "apa isi gambar ini?", images=[DATA]))
assert out == "Ini pola warna uji.", out
assert [o[0] for o in order] == ["attach", "send"] and order[0][1] == [DATA], order
assert not os.path.exists(upload_dir), "folder unggahan tidak dihapus"

upload_dir2 = tempfile.mkdtemp(dir=HOME.name)
eng._attach_images = lambda imgs: {"dir": upload_dir2, "hashes": set()}
eng._send = lambda p: (_ for _ in ()).throw(MuseGenerationError("gagal kirim"))
try:
    list(eng.chat_stream({}, "x", images=[DATA]))
except MuseGenerationError:
    pass
assert not os.path.exists(upload_dir2), "folder unggahan tidak dihapus saat gagal"
order.clear()
polls = itertools.chain([(0, "", False)], itertools.repeat((1, "Halo.", False)))
eng._attach_images = lambda imgs: order.append("attach")
eng._send = lambda p: order.append("send") or "clicked"
assert "".join(eng.chat_stream({}, "halo")) == "Halo." and order == ["send"], order

# ---- 2. API ----
async def call(body, path="/v1/chat/completions", raw=False):
    payload = json.dumps(body).encode()
    msgs = []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "server": ("t", 80), "client": ("t", 1),
             "headers": [(b"authorization", b"Bearer test-only"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(payload)).encode())]}

    sent_body = []

    async def receive():
        # Respons stream memantau klien putus lewat receive(); setelah body terkirim, tunggu (dibatalkan Starlette saat selesai).
        if sent_body:
            await asyncio.sleep(3600)
        sent_body.append(1)
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(m):
        msgs.append(m)
    await app.app(scope, receive, send)
    status = next(m["status"] for m in msgs if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in msgs)
    return status, (data.decode() if raw else json.loads(data))

seen = []

def fake_chat_stream(cookies, prompt, expires=None, timeout=None, account_id=None, stop_event=None, images=None):
    seen.append({"prompt": prompt, "images": images})
    yield "Gambar berisi pola warna."

app.store.add_account({"hatch_sess": "a"}, label="A")
with patch.object(app, "_renew_and_persist", lambda aid, **k: app.store.get_account(aid)), \
        patch.object(app, "_sync_cookies", lambda aid: {}), patch.object(app, "_bind_account_proxy", lambda acc: None), \
        patch.object(app.engine, "start", lambda: None), patch.object(app.engine, "chat_stream", fake_chat_stream):
    st, res = asyncio.run(call({"model": "muse-spark", "messages": [
        {"role": "user", "content": [{"type": "text", "text": "lihat ini"}, {"type": "image_url", "image_url": {"url": DATA}}]},
        {"role": "assistant", "content": "oke"},
        {"role": "user", "content": [{"type": "text", "text": "apa isi gambar ini?"},
                                     {"type": "image_url", "image_url": {"url": DATA}},
                                     {"type": "image_url", "image_url": {"url": DATA}}]}]}))
    assert st == 200 and res["choices"][0]["message"]["content"] == "Gambar berisi pola warna.", (st, res)
    imgs = seen[-1]["images"]
    assert len(imgs) == 2 and all(base64.b64decode(i.split(",", 1)[1]) == PNG for i in imgs), "gambar tidak byte-identik"
    assert "apa isi gambar ini?" in seen[-1]["prompt"]

    asyncio.run(call({"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": DATA}}]},
                                   {"role": "assistant", "content": "oke"}, {"role": "user", "content": "terima kasih"}]}))
    assert seen[-1]["images"] is None, "gambar riwayat ikut terkirim"

    st, res = asyncio.run(call({"messages": [{"role": "user", "content": [{"type": "text", "text": "x"}] + [
        {"type": "image_url", "image_url": {"url": DATA}}] * 11}]}))
    assert st == 400 and len(seen) == 2, (st, res)

    # ---- 3. /v1/responses (Codex) ----
    R = "/v1/responses"
    st, res = asyncio.run(call({"model": "muse-spark", "input": [{"role": "user", "content": [
        {"type": "input_text", "text": "apa isi gambar ini?"}, {"type": "input_image", "image_url": DATA}]}]}, R))
    assert st == 200 and res["output"][0]["content"][0]["text"] == "Gambar berisi pola warna.", (st, res)
    assert len(seen[-1]["images"]) == 1 and base64.b64decode(seen[-1]["images"][0].split(",", 1)[1]) == PNG
    assert "[图片]" in seen[-1]["prompt"] and "apa isi gambar ini?" in seen[-1]["prompt"]

    asyncio.run(call({"input": [{"type": "input_text", "text": "jelaskan"}, {"type": "input_image", "image_url": {"url": DATA}}]}, R))
    assert len(seen[-1]["images"]) == 1, "item input_image lepas tidak diteruskan"

    st, body = asyncio.run(call({"stream": True, "input": [{"role": "user", "content": [
        {"type": "input_text", "text": "apa ini?"}, {"type": "input_image", "image_url": DATA}, {"type": "input_image", "image_url": DATA}]}]}, R, raw=True))
    assert st == 200 and "response.output_text.delta" in body and "Gambar berisi pola warna." in body, body[:300]
    assert len(seen[-1]["images"]) == 2, "stream: gambar tidak diteruskan"

    asyncio.run(call({"instructions": "singkat", "input": "halo"}, R))
    assert seen[-1]["images"] is None
    n = len(seen)
    st, _ = asyncio.run(call({"input": [{"role": "user", "content": [{"type": "input_image", "image_url": DATA}] * 11}]}, R))
    assert st == 400 and len(seen) == n

print("PASS: lampiran sebelum kirim + folder dibersihkan (juga saat gagal); API meneruskan 2 gambar byte-identik; riwayat tidak ikut; >10 gambar ditolak 400; /v1/responses (pesan, item lepas, stream) sama")
