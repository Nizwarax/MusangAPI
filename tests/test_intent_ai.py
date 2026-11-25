"""Run: venv/bin/python tests/test_intent_ai.py

/v1/intent: jenis diputuskan AI muse (di sini dipalsukan), heuristik hanya cadangan, /perintah tidak bertanya ke AI.
Golden set = pesan asli pengguna dari data/chats.json dengan label dari pengguna (2026-11-24).
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-intent-ai-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402
from intent import ai_kind, ai_prompt  # noqa: E402

# Label pengguna: pesan 2 dan 3 = chat; pesan 1 = video (prompt adegan lengkap, 10 detik).
GOLDEN = [
    ("Jalan Raya Ngarai Sianok, Bukittinggi, saat sore**\nLate afternoon first-person POV dashcam from inside a car "
     "near the Sianok canyon, Bukittinggi, steep green cliffs, warm light, a few vehicles, realistic 1080p, 10 seconds.", "video"),
    ("# 100 Template Master Prompt: Video POV / Dashcam Perjalanan Berkendara di Indonesia\n\n" + "isi template\n" * 3000, "chat"),
    ("bisa buatkan video sekaligus banyak ? saya ada beberapa prompt", "chat"),
]

# Jawaban model diurai dengan longgar, tapi hanya kata yang sah.
assert ai_kind("chat") == "chat" and ai_kind(" Video.") == "video" and ai_kind("**image**") == "image"
assert ai_kind("") is None and ai_kind("tidak tahu") is None and ai_kind("videos") is None

# Prompt membawa konteks dan memotong teks panjang.
p = ai_prompt(GOLDEN[1][0], [{"role": "user", "content": "halo"}, {"role": "assistant", "content": "[video dibuat] x"}])
assert "user: halo" in p and "[video dibuat]" in p and "dipotong" in p and len(p) < 5000
assert f"({len(GOLDEN[1][0].strip())} characters" in p

seen = []


def fake_muse(prompt):
    seen.append(prompt)
    for text, label in GOLDEN:
        if text[:60] in prompt:
            return label
    return "chat"


def call(text, **kw):
    return app.intent(app.IntentRequest(text=text, **kw))


with patch.object(app, "_ask_muse", fake_muse):
    for text, label in GOLDEN:
        out = call(text)
        assert (out["kind"], out["reason"]) == (label, "AI muse"), (text[:60], out)
    assert call(GOLDEN[0][0])["duration"] == 10  # spesifikasi media tetap dibaca dari teks
    n = len(seen)
    assert call("/video kucing tidur")["kind"] == "video" and len(seen) == n, "perintah / tidak boleh bertanya ke AI"
    assert call("lanjutkan", last_kind="video", history=[{"role": "user", "content": "x"}])["continue"] is False

# AI gagal/tak terbaca -> heuristik lama, pesan tetap jalan.
with patch.object(app, "_ask_muse", side_effect=RuntimeError("down")):
    assert call("buatkan gambar logo kopi")["reason"] == "kata gambar"
with patch.object(app, "_ask_muse", return_value="maaf saya tidak bisa"):
    assert call("halo apa kabar")["kind"] == "chat"

print("PASS: intent AI muse (golden set pengguna 3/3, /perintah tanpa AI, cadangan heuristik)")
