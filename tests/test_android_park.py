"""Run: venv/bin/python tests/test_android_park.py — tab muse simpanan di Chrome Android (engine.close_current_page park).

Memuat muse di HP ~14 dtk, jadi tab yang selesai normal disimpan dan dipakai lagi oleh permintaan berikutnya
(akun sama). Chat di tab simpanan harus memulai thread baru (lewat router), kalau gagal memuat ulang halaman.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.TemporaryDirectory(prefix="muse-park-test-")
os.environ.update(MUSE2API_HOME=HOME.name, MUSE2API_PROFILE_ROOT=HOME.name)
from config import Config  # noqa: E402
from engine import MuseEngine  # noqa: E402


class Browser:
    def __init__(self):
        self.sent = []

    def send(self, method, params=None, *a, **k):
        self.sent.append((method, params))
        return {"result": {}}


class Page:
    """Halaman muse palsu: jawaban js() menurut potongan ekspresi."""

    def __init__(self, bubbles=0, router=True):
        self.closed, self.bubbles, self.router, self.pushed, self.navigated = False, bubbles, router, 0, 0

    def close(self):
        self.closed = True

    def send(self, method, params=None, *a, **k):
        if method == "Page.navigate":
            self.navigated += 1
            self.bubbles = 0
        return {"result": {}}

    def js(self, expr, *a, **k):
        if "router.push" in expr:
            if not self.router:
                return False
            self.pushed += 1
            self.bubbles = 0
            return True
        if "forChat" in expr:  # keputusan reset_thread
            return "new" if self.bubbles else False
        if "location.pathname === '/thread/new'" in expr:
            return self.bubbles == 0
        if "readyState" in expr and "hydrat" in expr:  # _wait_ws_ready
            return "ready"
        if "querySelector('textarea')" in expr:
            return True
        return True


def engine(android=True):
    e = MuseEngine(Config())
    e.android, e.browser = android, Browser()
    return e


def hold(e, page, acc="a1", ctx="ctx1"):
    e.page, e.current_acc_id, e.current_context_id = page, acc, ctx
    e._active_contexts.add(ctx)


# 1. Android: tab disimpan, lalu dipakai lagi oleh akun yang sama tanpa membuka tab baru.
e, p = engine(), Page()
hold(e, p)
e.close_current_page(park=True)
assert not p.closed and e.page is None and e._parked["a1"]["page"] is p
assert e.ensure_page({}, account_id="a1") is p and e.current_acc_id == "a1" and e._parked == {}
assert not any(m == "Target.createTarget" for m, _ in e.browser.sent), e.browser.sent
print("ok: tab simpanan dipakai lagi oleh akun yang sama")

# 2. Dua akun (intent dan jawaban di akun berbeda): masing-masing punya tab simpanan, tidak saling menutup.
e, p1, p2 = engine(), Page(), Page()
hold(e, p1, acc="a1", ctx="c1")
e.close_current_page(park=True)
hold(e, p2, acc="a2", ctx="c2")
e.close_current_page(park=True)
assert not p1.closed and not p2.closed and set(e._parked) == {"a1", "a2"}
e._adopt_parked("a3")
assert e.page is None and set(e._parked) == {"a1", "a2"}
e._adopt_parked("a2")
assert e.page is p2 and set(e._parked) == {"a1"}
print("ok: satu tab simpanan per akun")

# 3. Bukan Android / tanpa park / tab berproxy: tetap ditutup seperti dulu.
for android, park, proxy in ((False, True, None), (True, False, None), (True, True, {"server": "x"})):
    e, p = engine(android), Page()
    hold(e, p)
    e._ensure_local().proxy_config = proxy
    e.close_current_page(park=park)
    assert p.closed and e._parked == {}, (android, park, proxy)
print("ok: Mac, kegagalan/dihentikan, dan tab berproxy tetap ditutup")

# 4. Akun yang sama menyimpan tab lagi: tab lamanya ditutup beserta konteksnya.
e, p1, p2 = engine(), Page(), Page()
hold(e, p1, ctx="c1")
e.close_current_page(park=True)
hold(e, p2, ctx="c2")
e.close_current_page(park=True)
assert p1.closed and not p2.closed and e._parked["a1"]["page"] is p2
assert ("Target.disposeBrowserContext", {"browserContextId": "c1"}) in e.browser.sent and "c1" not in e._active_contexts
print("ok: tab lama akun yang sama ditutup")

# 5. Chat di tab yang sudah berisi thread lama: thread baru lewat router, tanpa memuat ulang halaman.
e, p = engine(), Page(bubbles=4)
e.page = p
e.reset_thread(for_chat=True)
assert p.pushed == 1 and p.navigated == 0 and p.bubbles == 0, vars(p)
# Router gagal: cadangan muat ulang /thread/new.
e, p = engine(), Page(bubbles=4, router=False)
e.page = p
e.reset_thread(for_chat=True)
assert p.navigated == 1, vars(p)
# Tab baru (tanpa gelembung): tidak ada navigasi sama sekali.
e, p = engine(), Page(bubbles=0)
e.page = p
e.reset_thread(for_chat=True)
assert p.pushed == 0 and p.navigated == 0
print("ok: thread baru lewat router, cadangan reload")

# 6. Penjaga: tab muse milik engine yang menjadi tab terpilih (urutan pertama /json/list) -> /chat diaktifkan lagi.
import engine as engine_mod  # noqa: E402

LIST = []
engine_mod.http_json = lambda url, timeout=0: LIST
e = engine()
e._own_targets = {"muse1"}
LIST[:] = [{"type": "page", "id": "muse1", "url": "https://muse.ai/thread/x"},
           {"type": "page", "id": "ui1", "url": "http://127.0.0.1:18610/chat"},
           {"type": "page", "id": "ui0", "url": "http://127.0.0.1:18610/chat"}]
e._android_ui_guard_step()
assert e.browser.sent[-1] == ("Target.activateTarget", {"targetId": "ui1"}), e.browser.sent
e._ui_tab = "ui0"  # tab /chat terakhir yang terlihat lebih diutamakan
e._android_ui_guard_step()
assert e.browser.sent[-1] == ("Target.activateTarget", {"targetId": "ui0"}), e.browser.sent
# Tab muse milik pengguna sendiri, atau /chat sudah di depan: tidak disentuh.
for first in ({"type": "page", "id": "user-muse", "url": "https://muse.ai/"}, {"type": "page", "id": "ui1", "url": "http://127.0.0.1:18610/chat"}):
    LIST[0] = first
    n = len(e.browser.sent)
    e._android_ui_guard_step()
    assert len(e.browser.sent) == n, first
# Tab ditutup engine: id dilepas dari daftar milik engine.
e, p = engine(), Page()
p.target_id = "muse9"
e._own_targets.add("muse9")
hold(e, p)
e.close_current_page()
assert "muse9" not in e._own_targets
print("ok: penjaga mengembalikan /chat ke depan, tab muse pengguna tidak disentuh")

# 7. stop(): tab simpanan ikut ditutup.
e, p = engine(), Page()
hold(e, p)
e.close_current_page(park=True)
e.stop()
assert p.closed and e._parked == {}
print("test_android_park OK")
