"""Run: venv/bin/python tests/test_chat_files.py

File buatan muse di chat ("minta file txt/zip"): muse mengirimnya sebagai event delta.presentation (kind=file,
message_id lain), bukan di transcript message_done. Fixture = event mentah muse (ID diganti) dari permintaan .txt.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-chat-files-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402
import engine as eng  # noqa: E402

EVENTS = json.loads((ROOT / "tests/fixtures/muse_file_reply_events.json").read_text(encoding="utf-8"))

# 1. parser: teks dari message_done, file dari presentation dengan session yang sama
net = eng._NetReply()
net.feed(EVENTS)
assert net.done and net.final == "Selesai, ini filenya:\n\n", net.final
assert [(f["label"], f["mime"], f["byte_len"]) for f in net.files] == [("uji-satu.txt", "text/plain", 14)], net.files
other = eng._NetReply()
other.feed([dict(e, payload=dict(e["payload"], session_id="lain")) if e["event"] == "delta.presentation" else e for e in EVENTS])
assert other.files == [], "file dari sesi lain tidak boleh ikut"


# 2. _net_reply: teks lalu tautan file; gagal -> kalimat jelas
class FakePage:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def js(self, expr, await_promise=False, timeout=None):
        self.calls.append(expr)
        return json.dumps(self.reply)


def run(reply, sink):
    e = object.__new__(eng.MuseEngine)
    e._take_events = lambda: []
    e._local = __import__("threading").local()
    e._local.page = FakePage(reply)
    e.file_sink = sink
    n = eng._NetReply()
    n.feed(EVENTS)
    return "".join(e._net_reply(n, 10 ** 12, None)), e._local.page


saved = []
out, page = run({"ok": True, "mime": "text/plain", "b64": "c2F0dQpkdWEKdGlnYQo="},
                lambda label, mime, data: saved.append((label, mime, data)) or "/v1/files/" + "a" * 32 + ".txt?name=uji-satu.txt")
assert out == "Selesai, ini filenya:\n\n\n\n[uji-satu.txt](/v1/files/" + "a" * 32 + ".txt?name=uji-satu.txt)", out
assert saved == [("uji-satu.txt", "text/plain", b"satu\ndua\ntiga\n")], saved
assert '"workspace/your_files/uji-satu.txt", 14, "uji-satu.txt", "uji-satu.txt"' in page.calls[0], "path tanpa sandbox:// + ukuran + nama unduhan"

# 2a. label tampilan muse beda dari nama file (kasus nyata: "Sholawat Penyejuk Hati txt" vs Sholawat-Penyejuk-Hati.txt)
PRETTY = [dict(e, payload=dict(e["payload"], data={"file": dict(e["payload"]["data"]["file"], label="Uji Satu txt")}))
          if e["event"] == "delta.presentation" else e for e in EVENTS]
saved2 = []
e3 = object.__new__(eng.MuseEngine)
e3._take_events = lambda: []
e3._local = __import__("threading").local()
e3._local.page = FakePage({"ok": True, "mime": "text/plain", "b64": "c2F0dQpkdWEKdGlnYQo="})
e3.file_sink = lambda label, mime, data: saved2.append(label) or "/v1/files/" + "c" * 32 + ".txt?name=uji-satu.txt"
n3 = eng._NetReply()
n3.feed(PRETTY)
out3 = "".join(e3._net_reply(n3, 10 ** 12, None))
assert saved2 == ["uji-satu.txt"] and "[uji-satu.txt](" in out3, (saved2, out3)
assert '"uji-satu.txt", "Uji Satu txt"' in e3._local.page.calls[0], "nama file dari path, label tampilan sebagai cadangan"
out, _ = run({"ok": False, "err": "no-card"}, lambda *a: "x")
assert "uji-satu.txt dibuat muse tetapi tidak bisa diambil: no-card" in out, out


# 2b. pesan lanjutan di sesi yang sama (task masih running) ikut terbaca; sebelumnya hilang
FOLLOW = json.loads((ROOT / "tests/fixtures/muse_followup_events.json").read_text(encoding="utf-8"))
cut = next(i for i, e in enumerate(FOLLOW) if e["event"] == "delta.message_done") + 1
e2 = object.__new__(eng.MuseEngine)
e2._local = __import__("threading").local()
e2._local.page = FakePage({"ok": True, "mime": "text/csv", "b64": "bmFtYQo="})
rest = [FOLLOW[cut:]]
e2._take_events = lambda: rest.pop() if rest else []
e2.file_sink = lambda *a: "/v1/files/" + "b" * 32 + ".csv?name=data.csv"
n2 = eng._NetReply()
n2.feed(FOLLOW[:cut])
assert n2.done and n2.running, "task masih running saat pesan pertama selesai"
out2 = "".join(e2._net_reply(n2, 10 ** 12, None))
assert out2 == ("Sudah jadi, ini filenya.\n\nIsinya 3 baris data siswa dengan kolom nama dan nilai."
                "\n\n[data.csv](/v1/files/" + "b" * 32 + ".csv?name=data.csv)"), repr(out2)
assert not n2.running


# 3. route /v1/files: selalu attachment, nama ilegal ditolak, hapus butuh key
async def request(method, path, key="test-only"):
    raw_path, _, qs = path.partition("?")
    headers = [(b"authorization", f"Bearer {key}".encode())] if key else []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": raw_path, "raw_path": raw_path.encode(), "query_string": qs.encode(), "root_path": "",
             "server": ("test", 80), "client": ("test", 1), "headers": headers}
    msgs, first = [], [True]

    async def receive():
        if first.pop() if first else False:
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # FileResponse menunggu disconnect; tanpa ini receive() berputar terus

    async def send(m):
        msgs.append(m)

    await app.app(scope, receive, send)
    start = next(m for m in msgs if m["type"] == "http.response.start")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, b"".join(m.get("body", b"") for m in msgs)


async def main():
    url = app._save_chat_file("café ü.html", "text/html", b"<script>alert(1)</script>")
    name = url.split("/v1/files/")[1].split("?")[0]
    assert name.endswith(".html") and len(name) == 37, url
    st, h, body = await request("GET", url, key=None)
    assert st == 200 and body == b"<script>alert(1)</script>", st
    assert h["content-disposition"].startswith("attachment") and "caf%C3%A9%20%C3%BC.html" in h["content-disposition"], h
    assert h["content-type"] == "application/octet-stream" and h["x-content-type-options"] == "nosniff" and h["content-security-policy"] == "sandbox", h
    for bad in ("/v1/files/..%2Fchats.json", "/v1/files/" + "g" * 32, "/v1/files/" + "a" * 32 + ".toolongextension1"):
        assert (await request("GET", bad))[0] == 404, bad
    assert (await request("DELETE", "/v1/files/" + name, key=None))[0] == 401
    assert (await request("DELETE", "/v1/files/" + name))[0] == 200
    assert (await request("GET", "/v1/files/" + name))[0] == 404
    print("ok: file chat muse (parser fixture, tautan, gagal jelas, route aman)")


asyncio.run(main())
