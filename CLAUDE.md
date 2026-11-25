# CLAUDE.md: GemuseAPI (repo `muse2api`)

GemuseAPI by Deki_niswara adalah fork dari `czg86389-hub/muse2api`. Aplikasi ini mengendalikan web muse.ai lewat Chrome headless (CDP) lalu membukanya sebagai API yang kompatibel dengan OpenAI. Fiturnya: chat, gambar, video, dan file buatan muse. Ada juga UI `/chat` dan konsol admin.
Kode dan teks asli repo upstream berbahasa Mandarin. Kode baru dan komentar dari fork ini berbahasa Indonesia.

## Menjalankan

```sh
venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 18610   # dari root repo
```
- FastAPI hanya terpasang di `venv/`, tidak di Python sistem. API key ada di `.env` dengan nama `MUSE2API_KEY`. Contoh variabel lain ada di `.env.example`.
- **Port harus tetap 18610.** Pengguna membuka `http://127.0.0.1:18610/chat`. Port lain berarti origin lain, sehingga key dan riwayat di browser terlihat hilang.
- Mematikan proses server milik pengguna diblokir oleh mode otomatis. Minta pengguna yang me-restart setelah kode server berubah.
- Cek cepat: `curl -s 127.0.0.1:18610/healthz` harus mengembalikan `{"status":"ok",...}`.

## Test

Tidak ada pytest. Setiap file di `tests/` adalah skrip yang berdiri sendiri. Test dianggap lulus kalau exit code-nya 0.
```sh
venv/bin/python tests/test_intent.py            # satu file
node tests/test_extension_cookie_store.mjs      # file .mjs
venv/bin/python tests/test_vm_wait.py engine.py # butuh path modul sebagai argumen
```
- Test browser mencari `chromium` di PATH atau `MUSE2API_CHROMIUM`. Di macOS: buat symlink `chromium` di folder sementara yang dimasukkan ke PATH, mengarah ke `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, lalu set `MUSE2API_CHROMIUM` ke path yang sama.
- Jalankan semua test di **foreground**. Di proses background, semua test tercatat gagal karena lingkungannya berbeda.
- Kondisi awal per 2026-11-24, dengan Chrome dan argumen di atas: semua lulus **kecuali** `test_admin_layout`, `test_reference_upload_browser`, `test_full_image_viewer`, dan `test_extension_upgrade_notice` (gagal karena isi `version.json`). Kalau sebuah test gagal, bandingkan dengan daftar ini sebelum menyimpulkan perubahan Anda yang merusaknya.
- Utamakan test dengan backend palsu (misalnya `test_chat_flows_browser.py` lewat CDP dengan backend deterministik). **Setiap uji nyata ke muse memakai kuota akun.** Minta izin dan sebutkan jumlahnya sebelum membuat gambar atau video sungguhan.
- Eval chat langsung: `venv/bin/python tools/chat_eval.py [--memory] [--only 1,2] [--out f.json]`. Skor "bahasa" dan "format" dari alat ini **tidak bisa dipercaya**: jawaban berisi kode, tabel, atau angka dianggap salah bahasa, dan muse menulis judul dengan `**tebal**`, bukan `#`. Selalu cek teks jawabannya langsung.

## Peta kode

| File | Isi |
|---|---|
| `app.py` | Semua route FastAPI (`/v1/*` OpenAI, `/admin/*`, `/chat`), antrean generasi, failover akun, update dari repo |
| `engine.py` | Mengendalikan halaman muse.ai lewat CDP: chat stream, generasi media, pengambilan file |
| `cdp.py` / `proxy.py` | Klien CDP minimal / proxy per akun dan relay autentikasi |
| `store.py` | Pool akun dan task (JSON, ditulis atomik) di `data/` |
| `intent.py` | Menentukan jenis pesan (chat/gambar/video), spesifikasi media, `split_items` untuk daftar template bernomor |
| `memory.py` | Ingatan per `conversation_id` (`data/conversations.json`): media/frame terakhir dan akun pembuatnya, untuk permintaan lanjutan lintas akun |
| `chat.html` | UI chat. `/` dan `/chat` adalah shell (rail + chat). Admin dimuat di iframe `/admin?embed=1` |
| `admin.html` | Konsol admin (6 tab). i18n memetakan **teks sumber Mandarin persis** ke bahasa Inggris, jadi kalau teks Mandarin diubah, kuncinya ikut diubah |
| `theme.css` | Satu-satunya sumber token warna dan ukuran untuk chat dan admin |

Isi `data/`: `accounts.json` (cookie, rahasia), `tasks.json`, `chats.json` (riwayat /chat, GET/PUT `/v1/chats`), `conversations.json`, `video-blocked.json`, `files/` (file buatan muse), `media/`, `thumbnails/`, `server.log`.

## Aturan yang tidak terlihat dari kode

- **Nama**: teks yang dilihat pengguna memakai "GemuseAPI". Nama teknis tetap `muse2api`, yaitu `MUSE2API_*`, kunci localStorage, IndexedDB `muse2api`, path deploy, dan nama zip. Kalau nama teknis diganti, key dan riwayat chat pengguna hilang.
- **Repo**: semua link dan pengecekan update mengarah ke `Nizwarax/MusangAPI` (`REPO_SLUG` di `app.py`, `version.json`, header userscript). Upstream `czg86389-hub/muse2api` disebut sebagai kredit di README. Untuk mengambil perubahan upstream, tambahkan remote upstream tersendiri dan gunakan `git fetch upstream`.
- **Modul baru** wajib ditambahkan ke `TRACKED_REPO_PATHS` (`app.py`) **dan** `COPY` di `Dockerfile`, karena `test_release_integration.py` memeriksanya. `GENERATION_QUEUE.md` dan `VERSION_REPORTING.md` wajib ada di daftar itu, jadi jangan dihapus.
- **Shell dan iframe**: admin dan chat sama-sama punya global `$`, `KEY`, `api`, dan handler `onclick` inline, jadi tidak bisa digabung dalam satu dokumen. Di dalam iframe, `@media` mengikuti lebar iframe. Tabel akun harus tetap berupa `<table>` dengan `td.ellip`, karena itu kontrak `test_admin_layout`.
- **Intent**: `/v1/intent` bertanya ke chat muse (`intent.ai_prompt` + 6 pesan terakhir, timeout 60 detik). `classify` hanya cadangan kalau muse gagal. Perintah `/video`, `/gambar`, dan `/chat` melewati AI, begitu juga `intent.obvious_chat` (pertanyaan, sapaan, tugas teks tanpa satu pun tanda media): langsung chat, hemat 1 panggilan muse. Kalimat "percakapan" lain tetap ke AI karena bisa berupa prompt gambar tanpa kata kunci. Daftar template bernomor dipecah `split_items`, lalu chat.html meminta konfirmasi dan menjalankan satu tugas per template, maksimal 3 sekaligus.
- **Membaca jawaban muse**: WebSocket muse (`hatch.metaaivm.com`) terenkripsi Noise, jadi jaringan CDP hanya melihat ciphertext. Engine membungkus `JSON.parse` di halaman (`window.__museEvt`) dan membaca event ndjson `delta.message_start`, `delta.text_append`, `delta.message_done`, dan `task.status`. Filter memakai `session_id` thread dan `transcript_surface=="main_chat"`. Polling DOM hanya cadangan, dan cara itu pernah kehilangan isi blok kode.
- **File buatan muse** datang sebagai `delta.presentation kind:"file"` dengan `message_id` yang **berbeda** dari jawabannya. Byte file **hanya** bisa diambil lewat UI muse (kartu file, More actions, Download, lalu tangkap Blob). Cara `fetch(variants.original)`, `Network.loadNetworkResource`, dan `/api/session/fileserver-read` semuanya terbukti gagal. Blob dicocokkan lewat `<a download=nama>` dan ukurannya dicek terhadap `byte_len`. Muse kadang mengirim file di pesan lanjutan, jadi engine mengikuti `task.status` sampai selesai (maksimal 180 detik).
- **Keamanan `/v1/files/<32hex>.<ext>`**: selalu `attachment`, `application/octet-stream`, `nosniff`, `CSP: sandbox`, dan nama file divalidasi `_FILE_NAME_RE`. Jangan dilonggarkan, karena HTML buatan muse tidak boleh berjalan di origin ini.
- **Izin video ditentukan per akun di server Meta** (403 `video_not_available` "country or region"), bukan oleh IP atau perangkat, dan VPN tidak membantu. Di mode pool, akun yang ditolak dicatat di `data/video-blocked.json` (TTL 7 hari) lalu tugas dipindah ke akun lain. Akun eksplisit dan permintaan gambar tidak ikut failover.
- **Pemutus `MUSE_OUTAGE`**: 2 kali error 5xx berturut-turut per jenis membuat permintaan ditolak langsung selama 10 menit, lalu dicoba sekali. Penolakan karena wilayah atau konten tidak dihitung.
- **Hemat kuota**: prompt media kosong tanpa gambar acuan ditolak dengan 400 (`_require_prompt`). `/v1/videos` dan `/v1/images/tasks` menerima `Idempotency-Key`. Untuk gambar yang lama, gunakan `/v1/images/tasks` lalu poll, dan jangan kirim ulang hanya karena polling timeout.
- **Media**: durasi hanya disuntik kalau pengguna menyebut angka. Durasi sampai 30 detik terbukti jalan. Muse mengirim video 1280x720 walaupun diminta 1080p.
- **Sinkron `/v1/chats`**: PUT mengganti seluruh daftar, jadi klien harus GET dan merge dulu (dua tab). `chats.json` yang rusak dipindah ke `chats.json.corrupt-<ts>` dan tidak boleh ditimpa.

## Android (Termux) (per 2026-11-25)

- **Termux** (`deploy/termux/`): server mengendalikan Chrome HP lewat `adb forward tcp:9333 localabstract:chrome_devtools_remote`; `engine.start()` memakai ulang CDP itu dan men-set `engine.android` dari `Android-Package` di `/json/version`. Socket DevTools hanya ada kalau Chrome dibuka **setelah** debugging aktif.
- Tab Chrome Android di latar belakang **tidak pernah di-render**: `_ANDROID_BG_JS` mengganti `requestAnimationFrame` (tanpanya hydration muse macet di "server") dan `IntersectionObserver` (tanpanya gambar muse tertahan di skeleton). Tab CDP baru selalu dipindah ke depan (`background:true` diabaikan), jadi `_android_refocus` mengembalikan tab `/chat`.
- Chrome Android menolak WebSocket CDP yang membawa header Origin: `cdp.py` memakai `suppress_origin=True`.
- **Tab muse simpanan (Android)**: memuat muse di HP ~14 dtk, jadi tab yang selesai normal disimpan (satu per akun; dengan 2 akun intent dan jawaban memakai akun berbeda) (`close_current_page(park=True)` di `safe_chat_stream` dan pemanasan) dan dipakai lagi oleh akun yang sama. Chat di tab simpanan membuka thread baru lewat `window.next.router.push('/thread/new')` (~1 dtk, tanpa reload; cadangan `Page.navigate`). `Emulation.setFocusEmulationEnabled` wajib: tanpanya muse memutus WebSocket ~13 dtk setelah tab tersembunyi. Akibatnya `visibilityState` tab muse selalu `visible` (tidak bisa dipakai untuk tahu tab mana yang tampil).
- Tab baru yang dibuat saat Chrome di latar (pengguna di Termux) menjadi tab terpilih, dan `activateTarget` tidak berpengaruh saat itu. `_android_ui_guard` mengecek `/json/list` (diurutkan dari tab yang terakhir aktif) tiap detik dan mengaktifkan `/chat` lagi bila tab pertama adalah tab muse milik engine.
- Di HP muse kadang hanya mengirim `delta.message_done` tanpa `message_start`/`text_append`. `_NetReply` menerimanya untuk sesi yang mulai `running` di giliran ini, dan di Android batas tunggu sebelum fallback DOM 6 dtk (bukan 2).
- Kecepatan di HP (Pixel 4, 1 akun, per 2026-11-25): kata pertama tampil ~6 dtk untuk pertanyaan (jalur `obvious_chat`), ~17 dtk bila intent ke AI; sebelumnya 42-51 dtk. Rincian: `PLAN-cepat-hp.md`. Klien yang memutus stream harus menghentikan muse (`client_gone` di `chat_completions`), kalau tidak satu-satunya akun tertahan.
- Belum beres: file buatan muse tidak bisa diambil di Android (tombol More actions = dialog sentuh, bukan menu). Catatan percobaan: `PLAN-uji-hp.md`.

## Masalah terbuka (per 2026-11-24)

- **Kata pertama lebih lambat sekitar 3 detik, dan 2/20 intent lewat 60 detik**, sejak fitur file (`0aafcd4`). Dugaan yang belum terbukti: penahanan di `engine._net_reply` setelah `message_done` (0,3 detik, plus sampai 180 detik selama task muse masih `running`) juga terkena `_ask_muse`. Langkah selanjutnya: catat lama penahanan di log, lalu kalau terbukti, lewati penahanan itu untuk intent.
- File besar (6 MB) dari muse gagal dengan respons CDP kosong `{}`. Penyebabnya belum diketahui, dan bukan batas ukuran CDP.
- Belum ada satu thread muse per percakapan. Riwayat masih ditempel sebagai transkrip 用户/助手 dan dipotong dari yang tertua kalau lebih dari 30 ribu karakter.
- Pesan yang bukan `obvious_chat` masih memakai 1 panggilan chat muse tambahan untuk intent (di HP ~10 dtk ekstra karena antre di akun yang sama).

## Dokumen lain

`README.md` untuk pengguna (bawaan upstream), `extension/README.md` (ikut dikemas di zip extension), `GENERATION_QUEUE.md` dan `VERSION_REPORTING.md` (spesifikasi fitur dan wajib ada di daftar rilis), `PLAN.md` (rencana kerja yang sedang berjalan, dihapus setelah selesai), dan `docs/chat-flows/*.gif` (rekaman alur chat).
