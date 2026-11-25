"""Ingatan per percakapan, disimpan di muse2api (bukan di thread muse.ai yang terikat satu akun).

Isi: 3 prompt media terakhir, media terakhir, frame terakhir video, dan akun yang membuatnya.
Saat pengguna meminta lanjutan, frame/gambar terakhir diunggah ulang sebagai acuan ke akun mana pun.
"""
import base64
import json
import mimetypes
import os
import re
import subprocess
import threading
import time

from intent import is_continuation

_LOCK = threading.Lock()
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
KEEP_PROMPTS = 3


class ConversationMemory:
    def __init__(self, path: str, media_dir: str):
        self.path, self.media_dir = path, media_dir

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def get(self, cid: str | None) -> dict | None:
        if not cid or not _ID.match(cid):
            return None
        with _LOCK:
            return self._load().get(cid)

    def remember(self, cid: str | None, kind: str, prompt: str, filename: str, account: str | None):
        if not cid or not _ID.match(cid):
            return
        frame = self._last_frame(filename) if kind == "video" else None
        with _LOCK:
            data = self._load()
            old = data.get(cid) or {}
            data[cid] = {"prompts": (old.get("prompts", []) + [prompt.strip()[:1500]])[-KEEP_PROMPTS:],
                         "kind": kind, "media": filename, "frame": frame,
                         "account": account, "updated": time.time()}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)

    def _last_frame(self, filename: str) -> str | None:
        src = os.path.join(self.media_dir, filename)
        out = os.path.splitext(src)[0] + "_last.png"
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", src, "-frames:v", "1", out],
                           check=True, timeout=60, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            return None
        return os.path.basename(out) if os.path.exists(out) else None

    def context(self, cid: str | None, prompt: str) -> tuple[list[str], str, str | None]:
        """-> (acuan data-URL, catatan konteks, akun pilihan); kosong bila bukan permintaan lanjutan."""
        mem = self.get(cid)
        if not mem or not is_continuation(prompt):
            return [], "", None
        ref = mem.get("frame") or (mem.get("media") if mem.get("kind") == "image" else None)
        refs = []
        if ref:
            try:
                with open(os.path.join(self.media_dir, ref), "rb") as f:
                    mime = mimetypes.guess_type(ref)[0] or "image/png"
                    refs.append(f"data:{mime};base64," + base64.b64encode(f.read()).decode())
            except OSError:
                pass
        prev = " / ".join(mem.get("prompts", []))
        note = ("【连续性要求】这是同一作品的直接延续：保持上一段中的人物、车辆、地点、光线与画风一致"
                + ("，以附带的上一段最后一帧作为本段第一帧" if mem.get("frame") and refs else "")
                + f"。上一段提示词：{prev}")
        return refs, note, mem.get("account")
