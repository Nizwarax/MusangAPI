"""Run: venv/bin/python tests/test_intent_batch.py — daftar template ("buatkan semua") dipecah satu per template.

Fixture = pesan asli pengguna (chat mwum6kznuxpf2f) yang dulu menjadi SATU video dari 23.456 karakter."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intent import classify

TEXT = (Path(__file__).parent / "fixtures" / "batch_100_templates.txt").read_text(encoding="utf-8")

out = classify(TEXT)
items = out.get("items") or []
assert out["kind"] == "video", out["kind"]
assert len(items) == 100, len(items)
assert [x["n"] for x in items] == list(range(1, 101))
assert items[0]["title"] == "Jalan Tol Trans Jawa, Semarang, kabut tipis"
assert items[0]["prompt"].startswith("Jalan Tol Trans Jawa, Semarang, kabut tipis\nEarly morning first-person POV dashcam")
assert items[0]["prompt"].endswith("no readable license plates.")
assert items[99]["title"].startswith("Jalan Raya Sorong")
for x in items:  # prompt bersih: tanpa perintah, judul bagian, garis, atau template lain
    p = x["prompt"]
    assert "buatkan semua" not in p and "##" not in p and "**" not in p and "---" not in p, (x["n"], p)
    assert len(p) < 600, (x["n"], len(p))
    assert (x["duration"], x["resolution"]) == (10, "1080p"), (x["n"], x)
assert len({x["prompt"] for x in items}) == 100

# Daftar biasa bernomor juga dipecah; jenis mengikuti isinya.
two = classify("buatkan video:\n1. kucing berlari di taman, 5 detik\n2. anjing melompat ke kolam, 5 detik")
assert two["kind"] == "video" and [x["prompt"] for x in two["items"]] == [
    "kucing berlari di taman, 5 detik", "anjing melompat ke kolam, 5 detik"], two
img = classify("buatkan gambar berikut:\n1) logo kopi minimalis\n2) poster konser jazz")
assert img["kind"] == "image" and len(img["items"]) == 2, img

# Regresi: satu template tetap satu video; pertanyaan berdaftar tetap chat; nomor acak bukan daftar.
one = classify(TEXT.split("\n\n**02.")[0])
assert one["kind"] == "video" and len(one["items"]) < 2, one
assert classify("jelaskan poin berikut:\n1. kenapa video 5 detik\n2. kenapa 720p")["kind"] == "chat"
assert len(classify("buatkan video\n3. mobil\n1. motor")["items"]) < 2
print("intent_batch=PASS")
