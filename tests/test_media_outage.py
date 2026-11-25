"""Run: venv/bin/python tests/test_media_outage.py — pemutus gangguan layanan media muse (tanpa muse.ai)."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-outage-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name, MUSE2API_KEY="test-only")
import app  # noqa: E402
from engine import MuseGenerationError, MuseModelRefusalError  # noqa: E402

E502 = "模型未生成媒体，仅返回文本: 生成失败了，系统返回了上游错误（502），重试 3 次后仍不可用。"
E503 = "模型未生成媒体，仅返回文本: 视频这次没能生成，视频服务现在过载了，这次没出片。"
REGION = "模型未生成媒体，仅返回文本: 视频生成功能在这个账号所在的国家/地区不可用，是长期限制。"
OTHER = "模型未生成媒体，仅返回文本: 这个请求涉及真实人物，我不能生成。"
calls, script = [], []


def fake_generate(cookies, prompt, expect="image", **kw):
    calls.append(expect)
    step = script.pop(0)
    if isinstance(step, str):
        raise MuseModelRefusalError(step)
    return {"filename": "x.mp4", "size": 1, "kind": expect}


def run(kind="video"):
    t = time.monotonic()
    try:
        app._run_generation("p", kind, 30)
        return "ok", time.monotonic() - t
    except MuseGenerationError as exc:
        return str(exc), time.monotonic() - t


app.store.add_account({"hatch_sess": "a"}, label="A")
with patch.object(app, "_renew_and_persist", lambda aid, **k: app.store.get_account(aid)), \
        patch.object(app, "_sync_cookies", lambda aid: {}), patch.object(app, "_bind_account_proxy", lambda acc: None), \
        patch.object(app.engine, "start", lambda: None), patch.object(app.engine, "generate", fake_generate):
    script[:] = [E502, E503]
    assert "502" in run()[0] and "过载" in run()[0]
    n = len(calls)
    msg, took = run()
    assert msg.startswith("MUSE_OUTAGE video 2 ") and len(calls) == n and took < 0.5, (msg, took)

    script[:] = [{"ok": 1}]
    assert run("image")[0] == "ok", "gangguan video tidak boleh memblokir gambar"

    app.MEDIA_OUTAGE["video"] = [t - app.OUTAGE_COOLDOWN - 1 for t in app.MEDIA_OUTAGE["video"]]
    script[:] = [E502]
    assert "502" in run()[0] and len(calls) == n + 2, "setelah jeda, satu percobaan harus diteruskan ke muse"
    assert run()[0].startswith("MUSE_OUTAGE"), "percobaan uji gagal -> pemutus terbuka lagi"

    app.MEDIA_OUTAGE["video"] = [t - app.OUTAGE_COOLDOWN - 1 for t in app.MEDIA_OUTAGE["video"]]
    script[:] = [{"ok": 1}]
    assert run()[0] == "ok" and app.MEDIA_OUTAGE["video"] == [], "sukses harus menutup pemutus"

    app.MEDIA_OUTAGE["video"].clear()
    app.store.add_account({"hatch_sess": "b"}, label="B")  # cadangan supaya penolakan wilayah bisa pindah akun
    script[:] = [REGION, OTHER, OTHER, OTHER]
    run(); run(); run()
    assert app.MEDIA_OUTAGE["video"] == [], "penolakan wilayah/konten bukan gangguan layanan"
    assert not run()[0].startswith("MUSE_OUTAGE")

print("PASS: 2 kegagalan 5xx -> ditolak instan tanpa memanggil muse; gambar tidak ikut; uji pemulihan setelah jeda; sukses menutup; wilayah/konten tidak dihitung")
