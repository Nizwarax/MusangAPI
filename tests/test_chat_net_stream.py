"""Run: venv/bin/python tests/test_chat_net_stream.py

Balasan chat dibaca dari event delta.* muse (bentuk sama dengan rekaman jaringan asli 2026-11-24), bukan dari DOM:
markdown utuh (blok kode tidak hilang), sesi lain (judul otomatis) diabaikan, message_done = teks final.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import MuseEngine, _NetReply, MuseGenerationError  # noqa: E402

MID, OTHER = "assistant-msg-a", "assistant-msg-title"


def start(mid, surface="main_chat"):
    return {"event": "delta.message_start", "payload": {"message_id": mid, "transcript_surface": surface, "session_id": "s"}}


def append(mid, text):
    return {"event": "delta.text_append", "payload": {"message_id": mid, "text": text}}


def done(mid, text):
    return {"event": "delta.message_done", "payload": {"message_id": mid, "status": "completed", "transcript": {
        "messages": [{"role": "assistant", "content": [{"type": "text", "status": "done", "text": text}]}]}}}


FINAL = '- Apple\n- Banana\n- Cherry\n\n```python\nprint("hi")\n```'
BATCHES = [
    [start(OTHER, "session_title"), append(OTHER, "Fruit list")],      # sesi lain di socket yang sama
    [start(MID), append(MID, "- Apple\n- Banana\n- Cherry\n\n```")],
    [append(MID, "python\nprint"), append(OTHER, " and code")],
    [append(MID, '("hi")\n'), append(MID, "```")],
    [done(OTHER, "Fruit list and code"), done(MID, FINAL)],
]

r = _NetReply()
for b in BATCHES:
    r.feed(b)
assert r.mid == MID and r.done and r.text == FINAL and r.final == FINAL, (r.text, r.final)


class FakeEngine:
    _net_reply = MuseEngine._net_reply

    def __init__(self, batches):
        self.batches = list(batches)

    def _take_events(self):
        return self.batches.pop(0) if self.batches else []


import time  # noqa: E402

net = _NetReply()
net.feed(BATCHES[0] + BATCHES[1])
eng = FakeEngine(BATCHES[2:])
out = "".join(eng._net_reply(net, time.time() + 5, None))
assert out == FINAL, repr(out)

# Final berbeda dari potongan (muse menulis ulang): yang terkirim tidak diulang, tidak ada sisa ganda.
net = _NetReply()
net.feed([start(MID), append(MID, "Halo")])
out = "".join(FakeEngine([[done(MID, "Halo dunia")]])._net_reply(net, time.time() + 5, None))
assert out == "Halo dunia", out

# Tanpa message_done sampai batas waktu -> error yang jelas.
net = _NetReply()
net.feed([start(MID), append(MID, "x")])
try:
    "".join(FakeEngine([])._net_reply(net, time.time() + 0.3, None))
    raise AssertionError("harus timeout")
except MuseGenerationError:
    pass

print("PASS: balasan dari event delta.* (markdown utuh, sesi lain diabaikan, final dari message_done)")

# Di HP muse kadang hanya mengirim message_done (tanpa message_start/text_append): balasan tetap terbaca utuh,
# tapi hanya untuk sesi yang mulai "running" di giliran ini.
def status(sess, st):
    return {"event": "task.status", "payload": {"session_id": sess, "status": st}}


def done_main(mid, sess, text):
    d = done(mid, text)
    d["payload"].update(transcript_surface="main_chat", session_id=sess)
    return d


net = _NetReply()
net.feed([status("lama", "completed"), done_main("m0", "lama", "sisa thread lain")])
assert net.mid is None and not net.done, vars(net)
net.feed([status("baru", "running"), done_main("m1", "baru", "chat")])
assert net.mid == "m1" and net.done and net.final == "chat", vars(net)
print("ok: message_done tanpa message_start diterima hanya untuk sesi baru")
