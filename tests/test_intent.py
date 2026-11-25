"""Run: venv/bin/python tests/test_intent.py — akurasi router model "muse" dan pembacaan spesifikasi media."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intent import classify, parse_media_spec, is_continuation

DASHCAM = ("**01. Jalan Tol Trans Jawa, Semarang, kabut tipis**\nEarly morning first-person POV dashcam from inside a car "
           "on the Trans Java toll road near Semarang, thin morning mist over rice fields, soft pink-orange sunrise light, "
           "light traffic with trucks ahead, realistic 1080p, 10 seconds, no readable license plates.")
# Sumber: 7 prompt video asli di data/tasks (pengguna), sisanya pola permintaan pengguna di sesi ini (ID/EN/ZH).
CASES = [
    (DASHCAM, "video"),
    ("A calm ocean wave rolling onto a sandy beach at sunset, slow motion", "video"),
    ("A golden retriever puppy running through autumn leaves in slow motion", "video"),
    ("A cat yawning on a sunny windowsill", "video"),
    ("Animate this scene: the maple leaves drift down gently in the breeze, sun rays shimmer, slow cinematic camera push-in", "video"),
    ("An orange kitten slowly walking on the grass on a sunny day", "video"),
    ("Golden maple leaves gently falling in a light breeze, sunlight streaming through the treetops, cinematic", "video"),
    ("buatkan video 15 detik motor melintas di jalan pantura saat hujan", "video"),
    ("bikin klip pendek drone shot sawah terasering Bali, 9:16", "video"),
    ("生成一个10秒的视频：雨夜的城市街道", "video"),
    ("/video kucing tidur", "video"),
    ("lanjutkan, sekarang mobilnya keluar gerbang tol", "video"),           # last_kind=video
    ("buatkan gambar logo kedai kopi minimalis warna coklat", "image"),
    ("foto produk sepatu putih di atas meja kayu, studio lighting", "image"),
    ("poster konser jazz di Jakarta, gaya retro", "image"),
    ("A watercolor illustration of a lighthouse on a cliff", "image"),
    ("bikin ilustrasi anak sekolah membaca buku, flat design", "image"),
    ("帮我画一张赛博朋克风格的猫", "image"),
    ("/gambar pemandangan gunung bromo", "image"),
    ("isometric 3d render of a tiny coffee shop, 4k", "image"),
    ("apa ibu kota Jawa Tengah?", "chat"),
    ("kota nomor 2", "chat"),
    ("jelaskan bedanya video 720p dan 1080p", "chat"),
    ("kenapa hasil video saya cuma 5 detik?", "chat"),
    ("buatkan puisi pendek tentang hujan di Semarang", "chat"),
    ("tulis fungsi python untuk membaca file csv", "chat"),
    ("terjemahkan ke bahasa inggris: selamat pagi semua", "chat"),
    ("ringkas artikel berikut dalam 3 poin", "chat"),
    ("/chat buat video itu bagaimana caranya?", "chat"),
    ("terima kasih, mantap", "chat"),
]
LAST = {"lanjutkan, sekarang mobilnya keluar gerbang tol": "video"}
wrong = [(t, want, classify(t, LAST.get(t))["kind"]) for t, want in CASES if classify(t, LAST.get(t))["kind"] != want]
acc = 1 - len(wrong) / len(CASES)
for w in wrong: print("SALAH:", w)
assert len(CASES) == 30 and acc >= 0.95, f"akurasi {acc:.0%}"

assert parse_media_spec(DASHCAM) == {"duration": 10, "aspect_ratio": None, "resolution": "1080p"}
assert parse_media_spec("10-second clip, vertical")["aspect_ratio"] == "9:16"
assert parse_media_spec("buat video 15 detik 16:9")["duration"] == 15
assert parse_media_spec("生成一个10秒的视频")["duration"] == 10
assert parse_media_spec("A cat yawning")["duration"] is None
assert classify("/video kucing tidur")["prompt"] == "kucing tidur"
assert is_continuation("lanjutkan adegan berikutnya") and not is_continuation("kucing tidur")
assert classify("lanjutkan ceritanya", "chat")["kind"] == "chat"
assert classify("ubah jadi gaya anime", attachments=1)["kind"] == "image"
assert classify("animasikan, daunnya berguguran", attachments=1)["kind"] == "video"
assert classify("apa isi gambar ini?", attachments=1)["kind"] == "chat"
assert classify("ubah jadi lebih cerah")["kind"] == "chat" and classify("ubah jadi lebih cerah", attachments=2)["kind"] == "image"
for q in ("deskripsikan gambar ini", "jelaskan foto ini", "baca teks di gambar ini", "bandingkan dua gambar ini",
          "describe this image", "这张图片里是什么", "tebak ini foto di kota mana"):
    assert classify(q, attachments=1)["kind"] == "chat", q
print(f"PASS: router {acc:.0%} ({len(CASES) - len(wrong)}/{len(CASES)}), spesifikasi media terbaca")

# Jalur cepat /v1/intent: pertanyaan biasa tanpa tanda media tidak perlu bertanya ke AI muse.
from intent import obvious_chat  # noqa: E402
for q in ("Apa ibu kota Jepang? Jawab satu kalimat.", "Jelaskan cara kerja internet", "kenapa langit biru?",
          "Apa itu fotosintesis?", "Berapa 17 x 23?", "how does TCP work?", "jelaskan cara membuat kue bolu",
          "halo", "Terima kasih banyak", "tuliskan puisi tentang laut", "tolong perbaiki kode python ini: print(x"):
    assert obvious_chat(q), q
for q, last, att in (("Apa kamu bisa gambar kucing?", None, 0), ("bisakah kamu buatkan video pantai?", None, 0),
                     ("apa isi gambar ini?", None, 1), ("apa yang terjadi selanjutnya? lanjutkan", "video", 0),
                     ("kucing oranye tidur di sofa", None, 0), ("/chat apa kabar?", None, 0),
                     ("tuliskan puisi lalu buatkan gambarnya", None, 0), ("halo, bikin logo kopi", None, 0),
                     ("1. kucing\n2. anjing", None, 0),
                     ("Bagaimana kalau versi anime?", None, 0), ("berapa lama video 10 detik?", None, 0),
                     ("apa ini? " + "x" * 400, None, 0), ("", None, 0)):
    assert not obvious_chat(q, last, att), q
print("PASS: pertanyaan/sapaan/tugas teks melewati AI intent, yang bertanda media tetap ke AI")
