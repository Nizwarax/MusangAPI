"""Run: venv/bin/python tests/test_chats_sync.py

Riwayat /chat disimpan di server: PUT lalu GET mengembalikan daftar yang sama; tanpa key ditolak.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-chats-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402


async def request(method, path, body=None, key="test-only"):
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    if key:
        headers.append((b"authorization", f"Bearer {key}".encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "server": ("test", 80), "client": ("test", 1), "headers": headers}

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    await app.app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    return status, json.loads(b"".join(m.get("body", b"") for m in messages))


async def main():
    assert await request("GET", "/v1/chats") == (200, [])
    chats = [{"id": "a1", "title": "halo", "model": "muse", "updated": 1,
              "messages": [{"id": "m1", "role": "user", "content": "halo", "ts": 1}]}]
    assert (await request("PUT", "/v1/chats", chats))[0] == 200
    assert await request("GET", "/v1/chats") == (200, chats)
    assert (await request("GET", "/v1/chats", key=None))[0] == 401
    assert (await request("PUT", "/v1/chats", {"bukan": "list"}))[0] == 422
    assert await request("GET", "/v1/chats") == (200, chats)
    # file rusak: GET kosong, tapi isinya disimpan dulu sebelum PUT berikutnya menimpa
    Path(app.CHATS_PATH).write_text('[{"id": "a1", "title": "pot', encoding="utf-8")
    assert await request("GET", "/v1/chats") == (200, [])
    saved = list(Path(app.CHATS_PATH).parent.glob("chats.json.corrupt-*"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8").startswith('[{"id": "a1"'), saved
    print("ok: chats sync")


asyncio.run(main())
