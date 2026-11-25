"""Satu model "muse": tebak jenis permintaan (chat/gambar/video) dan baca spesifikasi media dari teks.

Dipakai server (POST /v1/intent, build_video_prompt, ingatan percakapan) supaya klien mana pun
mendapat keputusan yang sama. Heuristik murni, tanpa jaringan: jenis harus diketahui sebelum kuota terpakai.
"""
import re

_OVERRIDE = {
    "video": "video", "vid": "video", "视频": "video",
    "gambar": "image", "image": "image", "img": "image", "foto": "image", "图片": "image",
    "chat": "chat", "teks": "chat", "text": "chat",
}
_OVERRIDE_RE = re.compile(r"^\s*/(\S+)\s*", re.I)

_W = lambda words: re.compile(r"(?<![\w])(?:" + "|".join(words) + r")(?![\w])", re.I)
_VIDEO_NOUN = _W([r"video", r"videos", r"klip", r"clip", r"animasi", r"animate", r"animation", r"dashcam",
                  r"footage", r"timelapse", r"time-lapse", r"slow[ -]motion", r"b-roll", r"cinemagraph",
                  r"drone shot", r"tracking shot", r"camera (?:pans?|push(?:es)?[- ]in|dolly|orbits?)", r"push-in",
                  r"reels?", r"shorts", r"animasikan", r"gerakkan", r"jadikan video"])
_VIDEO_CJK = re.compile(r"视频|动画|短片|镜头")
_IMAGE_NOUN = _W([r"gambar", r"foto", r"image", r"images", r"picture", r"photo", r"photograph", r"ilustrasi",
                  r"illustration", r"poster", r"logo", r"wallpaper", r"lukisan", r"painting", r"sketsa", r"sketch",
                  r"potret", r"portrait photo", r"icon", r"ikon", r"stiker", r"sticker", r"thumbnail", r"banner",
                  r"infografis", r"mockup"])
_IMAGE_CJK = re.compile(r"图片|图像|照片|海报|插画|画一|壁纸")
_VERB = _W([r"buat", r"buatkan", r"bikin", r"bikinin", r"generate", r"create", r"make", r"render", r"draw",
            r"gambarkan", r"lukis", r"lukiskan", r"design", r"desain", r"hasilkan", r"produce", r"animasikan"])
_VERB_CJK = re.compile(r"生成|做一|画一|制作|帮我画")
# Kata kerja gerak bentuk -ing: deskripsi adegan yang bergerak -> video, yang diam -> gambar.
_MOTION = _W([r"walking", r"running", r"rolling", r"falling", r"flying", r"drifting", r"dancing", r"yawning",
              r"swimming", r"driving", r"moving", r"flowing", r"blowing", r"spinning", r"jumping", r"waving",
              r"crashing", r"pouring", r"melting", r"burning", r"rising", r"turning", r"zooming", r"panning",
              r"sliding", r"galloping", r"splashing", r"floating", r"walks", r"runs", r"drives"])
_STYLE = _W([r"photorealistic", r"hyperrealistic", r"realistic", r"realistis", r"watercolor", r"cat air", r"anime",
              r"pixel art", r"3d render", r"digital art", r"oil painting", r"studio lighting", r"bokeh", r"8k", r"4k",
              r"golden hour", r"macro shot", r"close-up", r"wide shot", r"low angle", r"flat design", r"vector",
              r"minimalist", r"isometric", r"cinematic"])
_QUESTION_START = _W([r"apa", r"apakah", r"bagaimana", r"gimana", r"kenapa", r"mengapa", r"siapa", r"kapan",
                      r"berapa", r"dimana", r"di mana", r"jelaskan", r"terjemahkan", r"ringkas", r"ringkaskan",
                      r"what", r"how", r"why", r"who", r"when", r"where", r"which", r"explain", r"translate",
                      r"summarize", r"is", r"are", r"does", r"do", r"can you explain", r"tolong jelaskan",
                      # Meminta penjelasan isi (biasanya tentang gambar terlampir), bukan meminta dibuatkan.
                      r"deskripsikan", r"describe", r"analisis", r"analisa", r"analyze", r"analyse", r"identifikasi",
                      r"identify", r"baca", r"read", r"tebak", r"periksa", r"cek", r"bandingkan", r"compare", r"ada apa"])
_QUESTION_CJK = re.compile(r"什么|吗[？?]?$|描述|识别|是谁|哪里")
_CONTINUE = _W([r"lanjut", r"lanjutkan", r"lanjutannya", r"sambung", r"sambungkan", r"terusan", r"teruskan",
                r"continue", r"continuation", r"next scene", r"adegan berikutnya", r"scene berikutnya",
                r"part 2", r"bagian (?:2|dua|berikutnya)", r"yang sama", r"same (?:character|car|scene|person|style)",
                r"seperti tadi", r"yang tadi", r"sebelumnya", r"previous (?:scene|video|image)"])
# Sapaan dan tugas teks: tanpa kata media, ini pasti chat (lihat obvious_chat).
_TEXT_TASK = _W([r"halo", r"hai", r"hi", r"hello", r"hey", r"pagi", r"siang", r"sore", r"malam", r"terima kasih",
                 r"makasih", r"thanks", r"thank you", r"ok(?:e|ay)?", r"sip", r"tulis", r"tuliskan", r"puisi", r"pantun",
                 r"cerita", r"cerpen", r"esai", r"artikel", r"surat", r"email", r"caption", r"kode", r"code", r"script",
                 r"skrip", r"fungsi", r"function", r"program", r"terjemah", r"ringkas", r"rangkum", r"resep", r"saran",
                 r"rekomendasi", r"contoh", r"hitung", r"koreksi", r"perbaiki", r"write", r"poem", r"story", r"essay",
                 r"summary", r"recipe", r"fix", r"debug"])
_CONTINUE_CJK = re.compile(r"继续|接着|同一个|刚才")

_DURATION = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s*(?:-\s*)?(?:s|sec|secs|second|seconds|detik|dtk|秒)(?![a-z])", re.I)
_RATIO = re.compile(r"(?<!\d)(16:9|9:16|1:1|4:3|3:4|21:9|4:5)(?!\d)")
_RES = re.compile(r"(?<![\w])(2160p|1440p|1080p|720p|480p|4k)(?![\w])", re.I)


def parse_media_spec(text: str) -> dict:
    """Durasi (detik), rasio, resolusi yang ditulis di prompt; None bila tidak disebut."""
    t = text or ""
    d = _DURATION.search(t)
    r = _RATIO.search(t)
    if not r:
        if re.search(r"vertical|vertikal|portrait|potret|tegak|竖屏|reels?\b|shorts\b|tiktok", t, re.I):
            ratio = "9:16"
        elif re.search(r"landscape|horizontal|widescreen|横屏", t, re.I):
            ratio = "16:9"
        else:
            ratio = None
    else:
        ratio = r.group(1)
    res = _RES.search(t)
    return {"duration": round(float(d.group(1).replace(",", "."))) if d else None,
            "aspect_ratio": ratio,
            "resolution": res.group(1).lower() if res else None}


_ITEM = re.compile(r"^[ \t]*(?:\*\*)?(\d{1,3})[.)][ \t]+(.+?)(?:\*\*)?[ \t]*$", re.M)
_ITEM_END = re.compile(r"^[ \t]*(?:#|-{3,}|\*{3,}|_{3,})", re.M)  # judul bagian / garis pemisah menutup template


def split_items(text: str) -> tuple[str, list[dict]]:
    """Daftar bernomor ("**01. Judul**\\nprompt" atau "1. prompt") -> (teks sebelum daftar, satu dict per item).

    Nomor harus naik tanpa duplikat; selain itu bukan daftar (mis. "3. ... 1. ...")."""
    t = text or ""
    found = list(_ITEM.finditer(t))
    nums = [int(m.group(1)) for m in found]
    if len(found) < 2 or nums != sorted(set(nums)):
        return t, []
    items = []
    for m, nxt in zip(found, found[1:] + [None]):
        body = t[m.end():nxt.start() if nxt else len(t)]
        body = _ITEM_END.split(body, 1)[0].strip()
        title = m.group(2).strip().strip("*").strip()
        prompt = title + ("\n" + body if body else "")
        items.append({"n": int(m.group(1)), "title": title, "prompt": prompt, **parse_media_spec(prompt)})
    return t[:found[0].start()], items


def is_continuation(text: str) -> bool:
    return bool(_CONTINUE.search(text or "") or _CONTINUE_CJK.search(text or ""))


def obvious_chat(text: str, last_kind: str | None = None, attachments: int = 0) -> bool:
    """Pertanyaan, sapaan, atau tugas teks tanpa tanda media sama sekali: pasti chat, /v1/intent tidak bertanya ke AI muse.

    Menghemat 1 panggilan muse per pesan; di HP (1 akun) AI intent menahan jawaban ~10 dtk lebih lama.
    Yang menyebut gambar/video/buat/gaya/durasi, lanjutan media, lampiran, atau teks panjang tetap ke AI."""
    t = (text or "").strip()
    if attachments or not t or len(t) > 300 or _OVERRIDE_RE.match(t):
        return False
    r = classify(t, last_kind)
    if r["items"] or not (r["reason"] == "pertanyaan" or (r["reason"] == "percakapan" and _TEXT_TASK.search(t))):
        return False  # "percakapan" lain bisa berupa prompt gambar tanpa kata kunci ("kucing tidur di sofa")
    hints = (_VIDEO_NOUN, _VIDEO_CJK, _IMAGE_NOUN, _IMAGE_CJK, _VERB, _VERB_CJK, _MOTION, _STYLE, _DURATION, _RATIO, _RES)
    return not any(rx.search(t) for rx in hints) and not (is_continuation(t) and last_kind in ("image", "video"))


def classify(text: str, last_kind: str | None = None, attachments: int = 0) -> dict:
    """-> {kind, prompt, reason, continue, duration, aspect_ratio, resolution}.

    attachments > 0: gambar acuan ikut dikirim; permintaan non-pertanyaan jadi edit gambar (atau video bila disebut)."""
    raw = (text or "").strip()
    prompt, kind, reason = raw, None, ""
    m = _OVERRIDE_RE.match(raw)
    if m and m.group(1).lower() in _OVERRIDE:
        kind, reason = _OVERRIDE[m.group(1).lower()], "perintah /" + m.group(1).lower()
        prompt = raw[m.end():].strip()
    cont = is_continuation(prompt)
    if not kind:
        t = prompt
        video = bool(_VIDEO_NOUN.search(t) or _VIDEO_CJK.search(t))
        image = bool(_IMAGE_NOUN.search(t) or _IMAGE_CJK.search(t))
        verb = bool(_VERB.search(t) or _VERB_CJK.search(t))
        head = t.lstrip("*#>-• \t\n")
        question = bool(_QUESTION_START.match(head) or _QUESTION_CJK.search(t)) or t.rstrip().endswith(("?", "？"))
        spec = parse_media_spec(t)
        if question and not verb:
            kind, reason = "chat", "pertanyaan"
        elif video:
            kind, reason = "video", "kata video"
        elif image:
            kind, reason = "image", "kata gambar"
        elif cont and last_kind in ("image", "video"):
            kind, reason = last_kind, "lanjutan " + last_kind
        elif spec["duration"] and (verb or len(t) > 40):
            kind, reason = "video", "durasi disebut"
        elif len(t) > 25 and _MOTION.search(t) and not question:
            kind, reason = "video", "adegan bergerak"
        elif _STYLE.search(t) and not question:
            kind, reason = "image", "gaya visual"
        else:
            kind, reason = "chat", "percakapan"
        if attachments and kind == "chat" and reason != "pertanyaan":
            kind, reason = "image", "gambar acuan"
    head, items = split_items(prompt)
    if items and not reason.startswith("perintah /"):
        # "buatkan semua" + daftar: jenis dari kalimat perintah ("buatkan video:"), bila tidak disebut dari template pertama.
        if _VERB.search(head) or _VERB_CJK.search(head):
            k = classify(head)["kind"] if head.strip() else "chat"
            k = k if k != "chat" else classify(items[0]["prompt"])["kind"]
            if k != "chat":
                kind, reason = k, f"daftar {len(items)} template"
    return {"kind": kind, "prompt": prompt, "reason": reason,
            "continue": cont and kind != "chat", "items": items, **parse_media_spec(prompt)}


_AI_ANSWER = re.compile(r"\b(chat|image|video)\b", re.I)


def ai_prompt(text: str, history: list[dict] | None = None, attachments: int = 0) -> str:
    """Pertanyaan klasifikasi untuk model chat muse: dia membaca konteks, bukan sekadar kata kunci."""
    t = (text or "").strip()
    body = t if len(t) <= 2000 else t[:1500] + "\n[... dipotong ...]\n" + t[-400:]
    lines = []
    for h in (history or [])[-6:]:
        c = str(h.get("content") or "").strip().replace("\n", " ")
        lines.append(f"{h.get('role', 'user')}: {c[:400]}")
    return (
        "You are a request router. Do NOT answer the user and do NOT create any image or video yourself. Only classify.\n"
        "The assistant can: chat (text reply), generate an image, or generate a video.\n"
        "Decide what the user's LAST message wants right now:\n"
        "- chat: questions (including asking whether something is possible or how to do it), discussion, feedback, "
        "pasting documents, templates, lists or many prompts to read/discuss/plan, anything that is not a clear request "
        "to produce one piece of media now.\n"
        "- image: clearly wants a still image produced now (or an edit of the attached image).\n"
        "- video: clearly wants a video produced now; a single scene/video prompt meant to be rendered counts.\n\n"
        "Recent conversation:\n" + ("\n".join(lines) or "(none)") + "\n\n"
        f"LAST message ({len(t)} characters, {attachments} attached image(s)):\n<<<\n{body}\n>>>\n\n"
        "Reply with exactly one word: chat, image, or video."
    )


def ai_kind(reply: str) -> str | None:
    """Kata pertama chat/image/video di jawaban model; None bila tidak terbaca."""
    m = _AI_ANSWER.search(reply or "")
    return m.group(1).lower() if m else None
