"""Status Browser di admin: Chrome yang dipakai ulang (tanpa proc milik server) tetap dihitung berjalan."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine as eng

e = eng.MuseEngine.__new__(eng.MuseEngine)  # tanpa __init__: tidak membuka Chrome
e.cfg = SimpleNamespace(cdp_port=1)

e.proc, e.browser = None, None
assert e.browser_alive() is False, "belum ada Chrome sama sekali = idle"

e.proc = SimpleNamespace(poll=lambda: None)
assert e.browser_alive() is True, "Chrome milik sendiri masih hidup"
e.proc = SimpleNamespace(poll=lambda: 0)
assert e.browser_alive() is False, "Chrome milik sendiri sudah keluar"

e.proc, e.browser = None, object()
with patch.object(eng, "http_json", return_value={"webSocketDebuggerUrl": "ws://x"}):
    assert e.browser_alive() is True, "Chrome dipakai ulang dan CDP menjawab"
with patch.object(eng, "http_json", side_effect=OSError("refused")):
    assert e.browser_alive() is False, "Chrome dipakai ulang tapi sudah mati"

print("PASS: browser_alive membedakan idle, milik sendiri, dan dipakai ulang")
