"""Pool-mode video: a region refusal fails over to another account and is remembered."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGION = "模型未生成媒体，仅返回文本: 视频生成功能在这个账号所在的国家/地区不可用"

with tempfile.TemporaryDirectory() as home:
    os.environ.update(MUSE2API_HOME=home, MUSE2API_PROFILE_ROOT=home,
                      MUSE2API_KEY="test-only")
    spec = importlib.util.spec_from_file_location("video_failover_candidate", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)
    one = app.store.add_account({"hatch_sess": "one", "hatch_vml": "one",
                                 "hatch_native_auth_device": "one"}, "one")
    two = app.store.add_account({"hatch_sess": "two", "hatch_vml": "two",
                                 "hatch_native_auth_device": "two"}, "two")
    calls = []
    refusal = {"one": REGION}

    def generate(cookies, prompt, **kwargs):
        sess = cookies["hatch_sess"]
        calls.append(sess)
        if sess in refusal:
            raise app.MuseModelRefusalError(refusal[sess])
        return {"kind": "video", "url": "x.mp4"}

    def run(kind="video"):
        calls.clear()
        app.store.get_account(one["id"])["ok"] = True
        return app._run_generation_locked("p", kind, 30, deadline=app.time.monotonic() + 30)

    mocks = (patch.object(app, "_renew_and_persist", side_effect=lambda ident, **_: app.store.get_account(ident)),
             patch.object(app.engine, "start"), patch.object(app.engine, "generate", side_effect=generate),
             patch.object(app.engine, "reset_thread"), patch.object(app.engine, "close_current_page"))
    for m in mocks:
        m.start()

    # 1) Refused account "one" is tried first: request must fail over to "two" and remember "one".
    app.VIDEO_BLOCKED.clear()
    first_pick = {"done": False}
    real_pick = app.store.pick_account

    def pick_one_first(**kw):
        if not first_pick["done"]:
            first_pick["done"] = True
            return app.store.get_account(one["id"])
        return real_pick(**kw)

    with patch.object(app.store, "pick_account", side_effect=pick_one_first):
        res, used = run()
    assert used == two["id"] and calls == ["one", "two"], (used, calls)
    assert one["id"] in app.VIDEO_BLOCKED

    # 2) Next video request skips the remembered account entirely.
    res, used = run()
    assert used == two["id"] and calls == ["two"], (used, calls)

    # 3) Every account refused -> the refusal is raised, no endless wait.
    refusal["two"] = REGION
    app.VIDEO_BLOCKED.clear()
    try:
        run()
    except (app.MuseModelRefusalError, app.MuseGenerationError):
        pass
    else:
        raise AssertionError("all-refused video did not raise")
    try:
        run()
    except app.MuseGenerationError as exc:
        assert "video" in str(exc).lower(), exc
    else:
        raise AssertionError("all-blocked video did not raise a clear error")

    # 4) Images keep the old rule: a refusal is terminal, no second account.
    app.VIDEO_BLOCKED.clear()
    refusal.pop("two")
    first_pick["done"] = False
    with patch.object(app.store, "pick_account", side_effect=pick_one_first):
        try:
            run("image")
        except app.MuseModelRefusalError:
            pass
        else:
            raise AssertionError("image refusal rotated")
    assert calls == ["one"], calls

    for m in mocks:
        m.stop()
print("PASS: video region refusal fails over, is remembered, and images stay terminal")
