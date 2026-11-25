"""Run: venv/bin/python tests/test_media_empty_prompt.py

"/gambar" atau "/video" tanpa teks dan tanpa gambar acuan ditolak 400, bukan dikirim ke muse (kuota terbuang).
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-empty-prompt-")
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
    for path in ("/v1/images/tasks", "/v1/images/generations", "/v1/videos"):
        for prompt in ("", "   "):
            status, body = await request("POST", path, {"prompt": prompt})
            assert status == 400 and body["error"]["message"] == "prompt 为空", (path, prompt, status, body)
    print("ok: prompt kosong ditolak di 3 endpoint media")


asyncio.run(main())
