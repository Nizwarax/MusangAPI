"""Chat reply extraction keeps markdown, and streamed deltas stay pure appends.

Real Chromium, no Muse account or network.
Run: python tests/test_chat_markdown_browser.py [--root /path/to/candidate]
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
from types import SimpleNamespace

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
args = parser.parse_args()
root = args.root.resolve()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location('chat_md_candidate', root / 'engine.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# --- _stream_safe: every delta must extend what was already sent ---
growth = [
    'Ibu', 'Ibu kota **Ja', 'Ibu kota **Jakarta**', 'Ibu kota **Jakarta**.\n\n1. Satu',
    'Ibu kota **Jakarta**.\n\n1. Satu\n2. Dua', 'Ibu kota **Jakarta**.\n\n1. Satu\n2. Dua\n\n```python\nprint(1)\n```',
    # Real muse.ai capture: a code line grows after it was already followed by the closing fence.
    'Ibu kota **Jakarta**.\n\n1. Satu\n2. Dua\n\n```python\nprint(1)\nprint(\n```',
    'Ibu kota **Jakarta**.\n\n1. Satu\n2. Dua\n\n```python\nprint(1)\nprint(2)\n```',
    'Ibu kota **Jakarta**.\n\n1. Satu\n2. Dua\n\n```python\nprint(1)\nprint(2)\n```\n\nPakai `x` ya',
]
sent = ''
for cur in growth:
    safe = module._stream_safe(cur)
    assert safe.startswith(sent), (sent, safe)
    sent = safe
assert growth[-1].startswith(sent)  # chat_stream flushes the rest at the end
assert module._stream_safe('**Ya**') == ''

# --- chat_stream over a recorded muse.ai re-render: no duplicated text ---
FINAL = '```python\nangka = [1, 2]\nfor n in angka:\n    print(n)\n```\n\nLoop ini **penting**.'
polls = [(0, '', False),                                    # baseline before send
         (1, '```python\nangka = [1, 2]\nfor n in\n```', True),
         (1, '```python\nangka = [1, 2]\nfor n in angka:\n    print(n)\n```\n\nLoop ini', True),
         (1, FINAL, True),
         (1, '```python\n\n```\n\nLoop ini **penting**.', True),  # code block re-rendered empty
         (1, FINAL, False), (1, FINAL, False), (1, FINAL, False), (1, FINAL, False)]
fake = module.MuseEngine.__new__(module.MuseEngine)
fake.cfg = SimpleNamespace(chat_timeout=30)
fake.ensure_page = lambda *a, **k: None
fake.reset_thread = lambda *a, **k: None
fake._send = lambda prompt: 'clicked'
fake._poll_chat = lambda: polls.pop(0) if len(polls) > 1 else polls[0]
real_sleep, module.time.sleep = module.time.sleep, lambda s: None
try:
    deltas = list(fake.chat_stream({}, 'x'))
finally:
    module.time.sleep = real_sleep
assert ''.join(deltas) == FINAL, deltas

# --- __md against a muse.ai-shaped bubble in real Chromium ---
BUBBLE = '''
<main><div class="hatch-chat-groupable-bubble rounded-22 bg-[var(--hatch-agent-bubble-bg)] w-full">
 <div class="flex flex-col gap-2"><div class="prose"><div class="space-y-4 whitespace-normal">
  <p>Ibu kota <strong>Jakarta</strong>,
     lihat <a href="https://id.wikipedia.org/wiki/Jakarta">wiki</a> dan <a href="javascript:alert(1)">ini</a>.</p>
  <ol><li class="py-1"><p>Jakarta</p></li><li><p>Surabaya</p><ul><li>Jatim</li></ul></li></ol>
  <div class="my-4"><div class="h-8"><span>python</span></div>
       <div class="sticky"><div><button><svg></svg></button><button><svg></svg></button></div></div>
       <div class="language-python"><pre class="language-python"><code><span class="block"><span>print("Jakarta")</span></span>
<span class="block"><span>for</span> <span>i</span> in range(2):</span>
<span class="block">    print(i)</span></code></pre></div></div>
  <p>Pakai <code>x</code> dan <em>miring</em>.</p>
 </div><div class="hidden" style="display:none">tersembunyi</div></div></div>
 <div class="mt-3"><button><span>Saran lanjutan</span></button></div>
</div></main>'''
EXPECTED = '''Ibu kota **Jakarta**, lihat [wiki](https://id.wikipedia.org/wiki/Jakarta) dan ini.

1. Jakarta
2. Surabaya
   - Jatim

```python
print("Jakarta")
for i in range(2):
    print(i)
```

Pakai `x` dan *miring*.'''

with tempfile.TemporaryDirectory(prefix='muse-md-test-', dir=Path.home()) as home:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    cfg = SimpleNamespace(
        chromium=shutil.which('chromium') or shutil.which('google-chrome') or next(
            (p for p in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'] if Path(p).exists()), None),
        cdp_port=port, home_dir=str(Path.home()), extra_path='',
        profile_dir=home + '/profile', data_dir=home, download_dir=home + '/downloads')
    Path(cfg.download_dir).mkdir()
    engine = module.MuseEngine(cfg)
    try:
        engine.start()
        engine.page = engine._open_page()
        engine.page.js('document.body.innerHTML=' + json.dumps(BUBBLE))
        cnt, txt, _ = engine._poll_chat()
        assert cnt == 1, cnt
        assert txt == EXPECTED, '\n--- got ---\n' + txt + '\n--- want ---\n' + EXPECTED
        # Plain pre-line bubbles (no prose markup) keep their line breaks.
        engine.page.js('document.body.innerHTML=' + json.dumps(
            '<main><div class="hatch-chat-groupable-bubble bg-[var(--hatch-agent-bubble-bg)]">'
            '<p style="white-space:pre-line">baris satu\nbaris dua</p></div></main>'))
        assert engine._poll_chat()[1] == 'baris satu\nbaris dua'
    finally:
        engine.stop()
print('chat markdown extraction OK')
