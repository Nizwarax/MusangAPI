"""Pengganti extension di Android: ambil cookie login muse.ai dari Chrome HP lewat CDP, kirim ke GemuseAPI.

Dipanggil oleh `gemuse login`. Pakai: python import_cookies.py <cdp_port> <server_url> <api_key> [label]
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from cdp import CDP  # noqa: E402

ESSENTIAL = "hatch_sess"  # sama dengan extension/popup.js


def muse_cookies(all_cookies: list[dict]) -> tuple[dict, dict]:
    """Tiru chrome.cookies.getAll({url: 'https://muse.ai/api/session'}): domain cocok, path prefiks,
    path terpanjang menang untuk nama yang sama."""
    match = [c for c in all_cookies
             if c.get("domain", "").lstrip(".") == "muse.ai"
             and "/api/session".startswith(c.get("path", "/").rstrip("/") or "/")]
    match.sort(key=lambda c: -len(c.get("path", "/")))
    out, exp = {}, {}
    for c in match:
        if c["name"] in out:
            continue
        out[c["name"]] = c["value"]
        if c.get("expires", -1) > 0:
            exp[c["name"]] = int(c["expires"])
    return out, exp


def main() -> int:
    cdp_port, server, key = sys.argv[1], sys.argv[2].rstrip("/"), sys.argv[3]
    label = sys.argv[4] if len(sys.argv) > 4 else ""
    browser = CDP(f"ws://127.0.0.1:{cdp_port}/devtools/browser", timeout=30)
    res = browser.send("Storage.getCookies", {})  # context default = sesi Chrome yang dipakai pengguna
    cookies, expires = muse_cookies(res.get("result", {}).get("cookies", []))
    if ESSENTIAL not in cookies:
        print("Belum ada login muse.ai di Chrome HP ini.\n"
              "Buka Chrome, masuk ke https://muse.ai lalu login, kemudian jalankan `gemuse login` lagi.")
        return 1
    req = urllib.request.Request(
        server + "/admin/accounts",
        data=json.dumps({"label": label, "cookies": cookies, "expires": expires}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"Server menolak ({e.code}): {e.read()[:300].decode(errors='replace')}")
        return 1
    added = data.get("added") or data.get("accounts") or []
    print(f"Berhasil: {len(cookies)} cookie diimpor sebagai akun"
          f" {', '.join(a.get('label') or a.get('id', '') for a in added) or '(baru)'}.")
    return 0


if __name__ == "__main__":
    # Self-check pencocokan cookie (dijalankan: python import_cookies.py --selftest).
    if sys.argv[1:] == ["--selftest"]:
        o, e = muse_cookies([
            {"name": "hatch_sess", "value": "root", "domain": ".muse.ai", "path": "/", "expires": 99},
            {"name": "hatch_sess", "value": "deep", "domain": "muse.ai", "path": "/api", "expires": -1},
            {"name": "x", "value": "1", "domain": "evil.ai", "path": "/"},
            {"name": "y", "value": "1", "domain": "muse.ai", "path": "/other"},
        ])
        assert o == {"hatch_sess": "deep"} and e == {}, (o, e)
        print("selftest ok")
        sys.exit(0)
    sys.exit(main())
