"""Run: venv/bin/python tests/test_chats_two_tabs_browser.py

Dua tab /chat (server asli, data sementara, tanpa muse): tab yang dibuka lebih dulu tidak boleh menghapus
percakapan yang dibuat tab lain saat menyimpan, dan percakapan yang dihapus di satu tab tidak hidup lagi.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cdp import CDP  # noqa: E402

KEY = "test-two-tabs"
HOME = tempfile.mkdtemp(prefix="m2a-two-tabs-")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


port, dport = free_port(), free_port()
BASE = f"http://127.0.0.1:{port}"
env = dict(os.environ, MUSE2API_HOME=HOME, MUSE2API_PROFILE_ROOT=HOME, MUSE2API_KEY=KEY)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
                       cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
chrome = shutil.which("chromium") or shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
br = subprocess.Popen([chrome, "--headless=new", f"--remote-debugging-port={dport}", f"--user-data-dir={HOME}/prof",
                       "--no-first-run", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def server_titles():
    req = urllib.request.Request(BASE + "/v1/chats", headers={"Authorization": "Bearer " + KEY})
    return sorted(c["title"] for c in json.load(urllib.request.urlopen(req)))


def wait(fn, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def page():
    req = urllib.request.Request(f"http://127.0.0.1:{dport}/json/new?about:blank", method="PUT")
    c = CDP(json.load(urllib.request.urlopen(req))["webSocketDebuggerUrl"])
    c.send("Page.enable")
    c.send("Page.navigate", {"url": f"{BASE}/chat?key={KEY}"})
    assert wait(lambda: c.js("typeof persist==='function' && document.readyState==='complete'")), "halaman tidak termuat"
    time.sleep(0.5)
    return c


def add(c, cid, title):
    c.js(f"chats.push({{id:{json.dumps(cid)},title:{json.dumps(title)},model:'muse',updated:Date.now(),"
         "messages:[{id:'m'+Date.now(),role:'user',content:'hi',ts:Date.now()}]}); persist(); render()")


fails = 0


def ok(name, cond, detail=""):
    global fails
    fails += not cond
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))


try:
    assert wait(lambda: urllib.request.urlopen(BASE + "/chat", timeout=1).status == 200), "server tidak hidup"
    assert wait(lambda: urllib.request.urlopen(f"http://127.0.0.1:{dport}/json/version", timeout=1)), "Chrome tidak hidup"
    a = page()          # tab A dibuka lebih dulu: daftarnya di memori tidak tahu percakapan dari B
    b = page()
    add(b, "b1", "dari B")
    wait(lambda: server_titles() == ["dari B"])
    add(a, "a1", "dari A")
    ok("tab lama menyimpan tanpa menghapus percakapan tab lain",
       wait(lambda: server_titles() == ["dari A", "dari B"], 5), server_titles())
    ok("percakapan tab lain muncul di daftar tab lama", wait(lambda: a.js("chats.some(c=>c.id==='b1')"), 5))

    b.js("pullChats()")  # sama seperti tab B kembali terlihat (visibilitychange)
    wait(lambda: b.js("!!document.querySelector('.th[data-id=\"a1\"] .del')"), 5)
    b.js("document.querySelector('.th[data-id=\"a1\"] .del').click()")
    b.js("document.querySelector('.th[data-id=\"a1\"] .del').click()")
    wait(lambda: server_titles() == ["dari B"], 5)
    add(a, "a2", "dari A lagi")  # tab A masih memegang a1 di memori
    ok("percakapan yang dihapus di tab lain tidak hidup lagi",
       wait(lambda: server_titles() == ["dari A lagi", "dari B"], 5), server_titles())
finally:
    br.kill()
    srv.kill()
    shutil.rmtree(HOME, ignore_errors=True)

print("ok: dua tab" if not fails else f"{fails} gagal")
sys.exit(1 if fails else 0)
