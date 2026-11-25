"""Ukur chat /chat seperti yang dialami pengguna: waktu intent, waktu kata pertama, total, kecepatan, format, ingatan.

Run: venv/bin/python tools/chat_eval.py [--base http://127.0.0.1:18610] [--only 1,5] [--memory] [--out hasil.json]
Memakai panggilan chat muse saja (tanpa gambar/video). Key dibaca dari .env (MUSE2API_KEY).
"""
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (prompt, fitur markdown yang diharapkan, bahasa jawaban yang diharapkan)
EVAL = [
    ("Tulis fungsi Python untuk membalik string, sertakan contoh pemakaian.", ["code"], "id"),
    ("Buat tabel perbandingan 3 bahasa pemrograman: Python, Go, Rust (kolom: kecepatan, kemudahan, pemakaian).", ["table"], "id"),
    ("Sebutkan 5 tips tidur nyenyak dalam bentuk daftar bernomor.", ["olist"], "id"),
    ("Jelaskan perbedaan TCP dan UDP secara singkat.", [], "id"),
    ("Explain recursion to a 10-year-old in 3 sentences.", [], "en"),
    ("Write a bash one-liner that counts lines in all .py files recursively.", ["code"], "en"),
    ("Apa itu fotosintesis? Jawab dengan judul dan poin-poin.", ["heading", "ulist"], "id"),
    ("Terjemahkan ke bahasa Inggris: 'Saya sedang belajar memasak rendang.'", [], "en_or_id"),
    ("Ringkas dalam 2 kalimat: Internet adalah jaringan global yang menghubungkan miliaran perangkat, memungkinkan pertukaran informasi, komunikasi, dan layanan seperti web, email, dan streaming.", [], "id"),
    ("Hitung 17 x 23 dan tunjukkan langkahnya.", [], "id"),
    ("Buat contoh JSON untuk data pengguna dengan nama, umur, dan hobi (array).", ["code"], "id"),
    ("Tulis puisi pendek 4 baris tentang hujan di Jakarta.", [], "id"),
    ("Bagaimana cara membuat virtual environment Python di macOS? Beri langkah dan perintahnya.", ["code", "olist"], "id"),
    ("Apa kelebihan dan kekurangan kerja remote? Pisahkan dua bagian dengan subjudul.", ["heading", "ulist"], "id"),
    ("Write a SQL query to get the top 5 customers by total order amount.", ["code"], "en"),
    ("Berikan 3 ide nama untuk kedai kopi di Bandung beserta alasannya.", ["olist_or_ulist"], "id"),
    ("Apa beda 'affect' dan 'effect'? Beri contoh kalimat.", [], "id"),
    ("Tulis regex untuk memvalidasi alamat email sederhana dan jelaskan bagian-bagiannya.", ["code"], "id"),
    ("Jelaskan big-O dari binary search dengan contoh kode JavaScript.", ["code"], "id"),
    ("Sebutkan ibu kota 5 negara ASEAN dalam tabel.", ["table"], "id"),
]

# Ingatan: fakta di giliran 1, ditanyakan di giliran terakhir.
MEMORY = [
    "Halo, nama kucing saya Mochi dan dia berumur 3 tahun. Ingat ya.",
    "Apa makanan yang baik untuk kucing dewasa?",
    "Berapa kali sehari sebaiknya diberi makan?",
    "Bagaimana cara memotong kuku kucing?",
    "Apa tanda kucing sedang stres?",
    "Mainan apa yang bagus untuk kucing rumahan?",
    "Perlukah kucing dimandikan?",
    "Vaksin apa saja yang wajib untuk kucing?",
    "Bagaimana cara melatih kucing memakai litter box?",
    "Siapa nama kucing saya dan berapa umurnya?",
]

FEATURES = {
    "code": re.compile(r"^```", re.M),
    "table": re.compile(r"^\s*\|.*\|\s*$\n^\s*\|?\s*:?-{3,}", re.M),
    "olist": re.compile(r"^\s*\d+[.)]\s+\S", re.M),
    "ulist": re.compile(r"^\s*[-*•]\s+\S", re.M),
    "heading": re.compile(r"^#{1,6}\s+\S", re.M),
}
ID_WORDS = re.compile(r"\b(yang|dan|untuk|dengan|adalah|ini|tidak|dari|bisa)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|is|to|of|that|you|with|for)\b", re.I)


def has(feature, text):
    if feature == "olist_or_ulist":
        return bool(FEATURES["olist"].search(text) or FEATURES["ulist"].search(text))
    return bool(FEATURES[feature].search(text))


def lang(text):
    i, e = len(ID_WORDS.findall(text)), len(EN_WORDS.findall(text))
    return "id" if i > e else "en" if e > i else "?"


def post(base, key, path, body, stream=False, timeout=300):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def turn(base, key, messages, parallel=True):
    """Satu giliran seperti chat.html: /v1/intent dan /v1/chat/completions (stream).

    parallel=True meniru chat.html sekarang (keduanya bersamaan; teks tampil setelah intent menjawab);
    False meniru versi lama (intent dulu, baru chat)."""
    if parallel:
        from concurrent.futures import ThreadPoolExecutor
        t0 = time.time()
        with ThreadPoolExecutor(2) as ex:
            fi = ex.submit(lambda: (json.load(post(base, key, "/v1/intent", {"text": messages[-1]["content"]})), time.time() - t0))
            r = _chat(base, key, messages)
            it, t_intent = fi.result()
        r.update(kind=it.get("kind"), intent_s=round(t_intent, 2),
                 user_first_word_s=round(max(t_intent, r["ttft_s"] if r["ttft_s"] >= 0 else r["total_s"]), 2))
        return r
    t0 = time.time()
    it = json.load(post(base, key, "/v1/intent", {"text": messages[-1]["content"]}))
    t_intent = time.time() - t0
    r = _chat(base, key, messages)
    r.update(kind=it.get("kind"), intent_s=round(t_intent, 2),
             user_first_word_s=round(t_intent + (r["ttft_s"] if r["ttft_s"] >= 0 else r["total_s"]), 2))
    return r


def _chat(base, key, messages):
    t1 = time.time()
    first, text, err = None, "", None
    r = post(base, key, "/v1/chat/completions", {"model": "muse-spark", "stream": True, "messages": messages})
    for raw in r:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            j = json.loads(data)
        except ValueError:
            continue
        if j.get("error"):
            err = str(j["error"])[:200]
            break
        piece = ((j.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
        if piece and first is None:
            first = time.time() - t1
        text += piece
    total = time.time() - t1
    gen = total - (first or total)
    return {"ttft_s": round(first or -1, 2), "total_s": round(total, 2),
            "chars": len(text), "chars_per_s": round(len(text) / gen, 1) if gen > 0.05 else None,
            "error": err, "text": text}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18610")
    ap.add_argument("--only", default="")
    ap.add_argument("--memory", action="store_true", help="jalankan tes ingatan 10 giliran")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    key = next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("MUSE2API_KEY="))
    rows = []
    pick = {int(x) for x in a.only.split(",") if x} or set(range(1, len(EVAL) + 1))
    for n, (prompt, feats, want) in enumerate(EVAL, 1):
        if n not in pick:
            continue
        r = turn(a.base, key, [{"role": "user", "content": prompt}])
        r.update(n=n, prompt=prompt, missing=[f for f in feats if not has(f, r["text"])], lang=lang(r["text"]),
                 lang_ok=want == "en_or_id" or lang(r["text"]) == want)
        rows.append(r)
        print(f"{n:2} {r['kind']:5} intent {r['intent_s']:5}s  kata-1 {r['user_first_word_s']:5}s  total {r['total_s']:5}s  "
              f"{r['chars']:5}ch {r['chars_per_s'] or '-':>6}ch/s  format-hilang={r['missing'] or '-'}  bahasa={r['lang']}"
              f"{'' if r['lang_ok'] else ' SALAH'}{'  ERR ' + r['error'] if r['error'] else ''}", flush=True)
    mem = None
    if a.memory:
        msgs = []
        for q in MEMORY:
            msgs.append({"role": "user", "content": q})
            r = turn(a.base, key, msgs)
            msgs.append({"role": "assistant", "content": r["text"]})
        last = msgs[-1]["content"]
        mem = {"ok": "mochi" in last.lower() and "3" in last, "answer": last[:300], "last_turn": {k: v for k, v in r.items() if k != "text"}}
        print("ingatan 10 giliran:", "OK" if mem["ok"] else "GAGAL", "|", last[:160].replace("\n", " "))
    if rows:
        med = lambda k: sorted(x[k] for x in rows)[len(rows) // 2]
        print(f"MEDIAN: intent {med('intent_s')}s, kata pertama yang dilihat pengguna {med('user_first_word_s')}s, "
              f"total {med('total_s')}s | format lengkap {sum(not x['missing'] for x in rows)}/{len(rows)} | "
              f"bahasa benar {sum(x['lang_ok'] for x in rows)}/{len(rows)} | error {sum(bool(x['error']) for x in rows)}")
    if a.out:
        Path(a.out).write_text(json.dumps({"rows": rows, "memory": mem}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
