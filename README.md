# GemuseAPI

**Dikelola oleh Deki_niswara**

GemuseAPI mengubah akun web [muse.ai](https://muse.ai/) menjadi API yang kompatibel dengan OpenAI. Anda bisa chat, membuat gambar, membuat video, dan menerima file buatan muse dari aplikasi apa pun yang sudah bisa memanggil OpenAI. Cukup ganti `base_url`-nya.

Aplikasi ini juga punya UI chat siap pakai di `/chat` dan konsol admin untuk mengelola akun, tugas, dan media.

> Proyek tidak resmi. Tidak berafiliasi dengan Meta atau muse.ai. Anda bertanggung jawab memakainya sesuai ketentuan layanan muse.ai.

## Cara kerja singkat

muse.ai tidak menyediakan API publik. GemuseAPI menjalankan Chrome headless, masuk dengan cookie akun muse Anda, lalu mengendalikan halaman web muse lewat Chrome DevTools Protocol. Jawaban dibaca langsung dari event halaman, jadi teks, tabel, dan blok kode sampai utuh. Setiap akun berjalan di konteks browser terpisah, sehingga beberapa akun bisa dipakai bersamaan.

## Fitur

- **API kompatibel OpenAI**: `/v1/chat/completions` dan `/v1/responses` (stream SSE dan non-stream), `/v1/images/generations`, `/v1/images/edits`, `/v1/videos`.
- **Chat UI di `/chat`**: riwayat tersimpan di server, Stop, Ulangi, Edit pesan terakhir, tabel dan kode, lampiran gambar (tombol, tempel, atau seret), serta tampilan HP. Jenis pesan dipilih otomatis oleh AI muse. Perintah `/gambar`, `/video`, dan `/chat` memaksa jenis tertentu.
- **Batch template**: tempel daftar prompt bernomor, konfirmasi sekali, lalu setiap template jadi tugas sendiri (maksimal 3 berjalan bersamaan).
- **File buatan muse**: txt, zip, pdf, docx, csv, md, dan json bisa diunduh lewat `/v1/files/…`.
- **Pool akun**: banyak akun muse sekaligus, rotasi otomatis, proxy HTTP/SOCKS5 per akun, dan keepalive sesi.
- **Failover video**: akun yang ditolak membuat video karena wilayah dicatat, lalu tugas dipindah ke akun lain.
- **Konsol admin di `/admin`**: akun, impor cookie, tugas, media (unduh satu atau ZIP), uji API, dan dokumentasi endpoint.
- **Ingatan percakapan**: permintaan lanjutan ("buat versi malam", "lanjutkan videonya") memakai gambar atau frame terakhir sebagai acuan, walaupun pindah akun.

## Mulai cepat

### Docker Compose

```bash
git clone https://github.com/Nizwarax/MusangAPI.git
cd MusangAPI
cp .env.example .env        # isi MUSE2API_KEY, atau kosongkan agar dibuat otomatis
docker compose up -d
```

Buka `http://<server>:18610/chat`. Kalau `MUSE2API_KEY` dikosongkan, key yang dibuat otomatis tercetak di log container (`docker compose logs`).

### Tanpa Docker (macOS / Linux)

Butuh Python 3.10+, Chrome atau Chromium, dan `ffmpeg` (untuk thumbnail video).

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 18610
```

Kalau Chrome tidak ditemukan otomatis, isi `MUSE2API_CHROMIUM` dengan path-nya. Di macOS: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

### VPS dengan systemd dan Nginx

Contoh service ada di `deploy/muse2api.service`, dan contoh Nginx ada di `deploy/nginx.example.conf`. Di belakang reverse proxy, **wajib** set:

```nginx
proxy_read_timeout 600s;     # video bisa butuh beberapa menit
proxy_buffering off;         # supaya stream chat tidak tersendat
client_max_body_size 200M;   # unggahan gambar acuan
```

### HP Android (Termux), tanpa extension

GemuseAPI bisa berjalan langsung di HP dan mengendalikan Chrome HP lewat debug nirkabel, jadi tidak perlu Chromium tambahan atau extension. Di Termux:

```bash
curl -fsSL https://raw.githubusercontent.com/Nizwarax/MusangAPI/main/deploy/termux/install.sh | bash
```

Installer memandu pairing debug nirkabel (pakai layar terpisah Termux + Setelan), memasang dependensi (sekali kompilasi Rust, 10-20 menit), lalu menyalakan server di `http://127.0.0.1:18610/chat`. Setelah login muse.ai di Chrome HP, jalankan `gemuse login` untuk mengimpor sesinya. Perintah lain: `gemuse start|stop|status|update|logs|key`. Menjalankan ulang installer = update; `data/` dan `.env` tidak disentuh.

Batasan di HP: jawaban mulai tampil sekitar 6-9 detik untuk pertanyaan biasa dan sekitar 17 detik untuk pesan yang perlu dipilihkan jenisnya oleh muse (dengan 1 akun keduanya antre); file buatan muse belum bisa diambil; Debug nirkabel kadang mati sendiri saat Wi-Fi berganti, nyalakan lagi lalu `gemuse start`.

#### Menambah akun muse kedua di HP

Akun kedua membuat pesan tidak perlu antre di satu akun, dan kuotanya bertambah. Akun ini harus akun Meta yang berbeda (email atau Facebook lain).

1. **Jangan tekan "Log out" di muse.ai.** Sesi akun pertama masih dipakai GemuseAPI.
2. Hapus data login muse.ai di Chrome saja: **Chrome ⋮ → Setelan → Setelan situs → Semua situs → muse.ai → Hapus data**. Langkah ini hanya menghapus login di Chrome. Akun pertama yang sudah tersimpan di GemuseAPI tidak ikut terhapus.
3. Buka muse.ai di Chrome HP, lalu login dengan akun kedua. Kalau Chrome langsung masuk ke akun lama lewat Facebook, pilih untuk memakai akun lain.
4. Di Termux jalankan `gemuse login akun-2` (`akun-2` hanya nama, bebas diganti).
5. Cek di `http://127.0.0.1:18610/admin`, tab akun: sekarang ada 2 akun.

Sesudahnya Chrome HP login sebagai akun kedua. Setiap akun memakai satu tab muse yang tetap terbuka di Chrome HP supaya jawaban cepat.

## Menambahkan akun muse

1. Login ke [muse.ai](https://muse.ai/) di browser biasa.
2. Impor cookie-nya dengan salah satu cara berikut:
   - **Extension Chrome/Edge (disarankan)**: unduh dari Admin, tab Cookie (atau folder `extension/`). Buka `chrome://extensions`, aktifkan Developer mode, klik Load unpacked, lalu isi alamat server dan API key di popup. Setelah itu klik impor.
   - **Userscript Tampermonkey**: pasang [`tools/muse2api_cookie_importer.user.js`](https://raw.githubusercontent.com/Nizwarax/MusangAPI/main/tools/muse2api_cookie_importer.user.js).
   - **Manual**: tempel cookie di Admin, tab Akun, Tambah akun.
3. Klik **Tes** pada akun di Admin untuk memastikan sesinya aktif.

## Pemakaian API

Semua endpoint kecuali `/healthz`, `/readyz`, dan `/v1/media/*` butuh header `Authorization: Bearer <MUSE2API_KEY>`.

Model yang tersedia: `muse-spark` (chat), `muse-image` (gambar), dan `muse-video` (video). Nama populer seperti `gpt-4o`, `gpt-image-1`, atau `sora` otomatis dipetakan ke model yang sesuai.

**Chat**

```bash
curl http://localhost:18610/v1/chat/completions \
  -H "Authorization: Bearer $MUSE2API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"muse-spark","stream":true,
       "messages":[{"role":"user","content":"Jelaskan fotosintesis dalam 3 poin"}]}'
```

Bisa juga dipakai dengan SDK OpenAI: `OpenAI(base_url="http://localhost:18610/v1", api_key=MUSE2API_KEY)`. muse tidak mengembalikan `tool_calls` terstruktur, jadi function calling tidak didukung.

**Gambar**

```bash
curl http://localhost:18610/v1/images/generations \
  -H "Authorization: Bearer $MUSE2API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"muse-image","prompt":"kucing oranye tidur di jendela, cahaya pagi",
       "size":"16:9","response_format":"url"}'
```

Untuk gambar dengan acuan, kirim `images: [{"url": "..."}]` (maksimal 10, masing-masing 40 MB dan total 100 MB), atau gunakan `/v1/images/edits` dalam format multipart. Kalau klien Anda punya timeout pendek, gunakan `POST /v1/images/tasks` lalu poll `GET /v1/images/tasks/{id}`.

**Video** (asinkron)

```bash
curl http://localhost:18610/v1/videos \
  -H "Authorization: Bearer $MUSE2API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: video-001" \
  -d '{"prompt":"daun maple jatuh pelan diterpa angin","duration":10,"size":"16:9"}'
# -> {"id":"task_…","status":"queued"}

curl http://localhost:18610/v1/videos/task_… -H "Authorization: Bearer $MUSE2API_KEY"
```

`Idempotency-Key` membuat permintaan yang terkirim ulang tidak membuat video kedua. Jangan kirim ulang permintaan hanya karena polling timeout. Cukup poll ID yang sama.

## Konfigurasi

Semua variabel diisi di `.env`. Contoh lengkapnya ada di `.env.example`.

| Variabel | Default | Fungsi |
|---|---|---|
| `MUSE2API_KEY` | dibuat otomatis | API key untuk admin dan API (awalan `m2a_`) |
| `MUSE2API_HOST` / `MUSE2API_PORT` | `127.0.0.1` / `18610` | Alamat server. Di Docker pakai `0.0.0.0` |
| `MUSE2API_PUBLIC_BASE` | kosong | URL publik untuk tautan media. Kosong berarti mengikuti alamat yang diakses |
| `MUSE2API_CHROMIUM` | dicari otomatis | Path Chrome/Chromium |
| `MUSE2API_CONCURRENCY` | `2` | Jumlah generasi yang boleh berjalan bersamaan |
| `MUSE2API_IMAGE_TIMEOUT` / `_VIDEO_TIMEOUT` / `_CHAT_TIMEOUT` | `240` / `600` / `300` | Batas waktu dalam detik |
| `MUSE2API_REF_IMAGE_LOCAL_FILES` | `0` | `1` mengizinkan gambar acuan dari path lokal server. Hanya untuk pemakai tunggal yang tepercaya |
| `MUSE2API_REF_IMAGE_PRIVATE_FETCH` | `0` | `1` mengizinkan URL jaringan privat atau localhost |

Nama variabel masih memakai awalan `MUSE2API_` agar kompatibel dengan instalasi lama.

## Batasan yang perlu diketahui

- **Video tergantung akun.** Meta menentukan izin membuat video per akun (error `video_not_available`, "country or region"). VPN tidak membantu. Gunakan beberapa akun supaya failover bisa bekerja.
- **Resolusi video** yang dikirim muse saat ini 1280×720, walaupun diminta 1080p. Durasi sampai 30 detik sudah terbukti jalan.
- **Kuota.** Setiap chat, gambar, dan video memakai kuota akun muse. Di UI chat, setiap pesan juga memakai satu panggilan chat tambahan untuk menentukan jenis pesan.
- **Kecepatan.** Kata pertama dari muse biasanya muncul setelah 7–15 detik. Gambar butuh sekitar 30 detik, video 1–3 menit.

## Pengembangan

Setiap file di `tests/` adalah skrip mandiri:

```bash
venv/bin/python tests/test_intent.py
```

Test browser butuh Chrome (`MUSE2API_CHROMIUM`). Panduan lengkap untuk kontributor dan agen AI, termasuk peta kode, aturan penting, dan masalah yang masih terbuka, ada di [`CLAUDE.md`](CLAUDE.md).

## Keamanan dan privasi

- Cookie akun, tugas, riwayat chat, dan media disimpan lokal di `data/`. Jangan commit folder ini.
- Tidak ada telemetri atau server perantara pihak ketiga.
- File buatan muse selalu dikirim sebagai unduhan (`attachment`, `nosniff`, `CSP: sandbox`), jadi tidak bisa menjalankan skrip di origin server Anda.

## Lisensi dan kredit

MIT. Lihat [`LICENSE`](LICENSE).
GemuseAPI adalah fork dari [muse2api](https://github.com/czg86389-hub/muse2api) karya czg86389-hub dan kontributornya. Bagian inti (engine CDP, pool akun, endpoint OpenAI, admin) berasal dari sana. Gebang Studio menambahkan UI chat, file buatan muse, batch template, ingatan percakapan, failover video, dan terjemahan Indonesia.
