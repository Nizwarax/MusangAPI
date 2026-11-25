#!/data/data/com.termux/files/usr/bin/bash
# Installer GemuseAPI untuk Termux (Android). Tanpa extension: server mengendalikan Chrome HP langsung.
#   curl -fsSL https://raw.githubusercontent.com/Nizwarax/MusangAPI/main/deploy/termux/install.sh | bash
# Menjalankan ulang = update. Folder data/ (akun, riwayat) dan .env tidak pernah ditimpa.
set -euo pipefail

REPO="${GEMUSE_REPO:-https://github.com/Nizwarax/MusangAPI.git}"
DIR="${GEMUSE_DIR:-$HOME/GemuseAPI}"
BRANCH="${GEMUSE_BRANCH:-main}" # untuk menguji branch sebelum merge

say() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31mGAGAL:\033[0m %s\n' "$*" >&2; exit 1; }

if [ -z "${PREFIX:-}" ] || ! command -v pkg >/dev/null; then die "Script ini khusus aplikasi Termux di Android."; fi

# Kompilasi bisa 20+ menit; tanpa wake-lock Android menidurkan Termux saat layar mati.
termux-wake-lock 2>/dev/null || true

say "1/5 Memasang paket Termux (python, git, adb)…"
# </dev/null: saat dijalankan lewat `curl | bash`, stdin adalah script ini sendiri; apt tidak boleh memakannya.
DPKG=(-y -o Dpkg::Options::=--force-confnew)
{ pkg upgrade "${DPKG[@]}" && pkg install "${DPKG[@]}" python git android-tools curl termux-tools; } </dev/null \
  || die "pkg gagal. Jalankan: termux-change-repo (pilih mirror lain), lalu ulangi installer."

say "2/5 Mengambil kode GemuseAPI ke $DIR…"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only \
    || die "Ada perubahan lokal di $DIR sehingga update dibatalkan (data Anda aman). Hubungi pengembang."
else
  git clone --depth 1 -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

say "3/5 Memasang dependensi Python…"
[ -x venv/bin/python ] || python -m venv venv
REQ=$(mktemp)
# uvloop/httptools dari [standard] tidak perlu dan sulit dikompilasi di Android.
sed 's/uvicorn\[standard\]/uvicorn/' requirements.txt >"$REQ"
ANDROID_API_LEVEL=$(getprop ro.build.version.sdk)
export ANDROID_API_LEVEL # dibutuhkan maturin saat mengompilasi pydantic-core
if ! venv/bin/pip install -q -r "$REQ"; then
  say "Perlu mengompilasi pydantic-core dengan Rust. Sekali saja, bisa 10-20 menit, jangan tutup Termux…"
  pkg install -y rust binutils || die "Gagal memasang Rust."
  venv/bin/pip install -q -r "$REQ" || die "Gagal memasang dependensi Python."
fi
rm -f "$REQ"

say "4/5 Menyiapkan konfigurasi…"
mkdir -p data
chmod 700 data
if [ ! -f .env ]; then
  KEY="sk-$(venv/bin/python -c 'import secrets; print(secrets.token_hex(24))')"
  printf 'MUSE2API_KEY=%s\n' "$KEY" >.env
fi
grep -q '^MUSE2API_CDP_PORT=' .env || printf 'MUSE2API_CDP_PORT=9333\n' >>.env
chmod 600 .env
chmod +x deploy/termux/gemuse
ln -sf "$DIR/deploy/termux/gemuse" "$PREFIX/bin/gemuse"

say "5/5 Menyalakan server…"
gemuse stop >/dev/null 2>&1 || true
gemuse start </dev/tty

cat <<EOF

Selesai. Langkah berikutnya:
  1. Buka Chrome di HP ini, login ke https://muse.ai
  2. Kembali ke Termux, ketik:  gemuse login
  3. Buka di Chrome:  http://127.0.0.1:18610/chat
     API key Anda:    $(gemuse key)

Perintah lain: ketik  gemuse
EOF
