"""Updater: tidak menurunkan / menimpa pekerjaan lokal, dan restart menjalankan ulang proses (bukan hanya keluar).

Memakai repo git sungguhan di folder sementara: "remote" (bare) + "lokal" (clone) sebagai BASE_DIR.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MUSE2API_KEY", "test")
import app
from fastapi import HTTPException


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


root = Path(tempfile.mkdtemp())
remote, seed, local = root / "remote.git", root / "seed", root / "local"
git(root, "init", "-q", "--bare", "-b", "main", str(remote))
git(root, "init", "-q", "-b", "main", str(seed))
(seed / "a.txt").write_text("v1\n")
git(seed, "add", "."); git(seed, "commit", "-qm", "c1")
git(seed, "remote", "add", "origin", str(remote)); git(seed, "push", "-q", "origin", "main")
c1 = git(seed, "rev-parse", "HEAD")
git(root, "clone", "-q", str(remote), str(local))
(seed / "a.txt").write_text("v2\n")
git(seed, "commit", "-qam", "c2"); git(seed, "push", "-q", "origin", "main")
c2 = git(seed, "rev-parse", "HEAD")

app.BASE_DIR = str(local)
git(local, "fetch", "-q", "origin", "main")

# Tertinggal (lokal c1, remote c2): aman di-upgrade, dan bukan "lebih baru".
assert app._local_work_at_risk(c2) == ""
assert app._local_is_ahead(c2) is False

# Perubahan belum di-commit: upgrade akan menimpanya -> ditolak.
(local / "a.txt").write_text("edit lokal\n")
assert "未提交" in app._local_work_at_risk(c2)
git(local, "checkout", "-q", "--", "a.txt")

# Commit lokal yang belum di-push (lokal = c2 + c3): bukan update, dan upgrade ditolak.
git(local, "merge", "-q", "--ff-only", "origin/main")
(local / "b.txt").write_text("fitur lokal\n")
git(local, "add", "."); git(local, "commit", "-qm", "c3")
c3 = git(local, "rev-parse", "HEAD")
assert app._local_is_ahead(c2) is True, "remote sudah ada di riwayat lokal = lokal lebih baru"
assert "未推送" in app._local_work_at_risk(c2)

# Jalur upgrade penuh: 409, TANPA jatuh ke tarball, dan lokal tidak berubah.
with patch.object(app, "_check_update_sync", return_value={"remote_commit": c2}), \
     patch.object(app, "_ensure_git_repo", lambda token="": None), \
     patch.object(app, "store", SimpleNamespace(tasks={})), \
     patch.object(app, "REPO_REF", "main"), \
     patch("requests.get", side_effect=AssertionError("tidak boleh mengunduh tarball")):
    try:
        app._upgrade_from_github_sync()
        raise AssertionError("upgrade seharusnya ditolak")
    except HTTPException as exc:
        assert exc.status_code == 409, exc.status_code
assert git(local, "rev-parse", "HEAD") == c3, "branch lokal tidak boleh digeser"
assert (local / "b.txt").exists(), "file commit lokal tidak boleh hilang"

# Repo yang baru di-init updater (belum ada HEAD): tidak ada pekerjaan lokal untuk dilindungi.
fresh = root / "fresh"; git(root, "init", "-q", str(fresh))
app.BASE_DIR = str(fresh)
assert app._local_work_at_risk(c1) == ""

# Restart menjalankan ulang perintah asli, bukan hanya keluar.
calls = []
with patch.object(app.engine, "stop", lambda: None), \
     patch("os.execv", lambda path, argv: calls.append((path, argv)) or (_ for _ in ()).throw(SystemExit)):
    try:
        app._restart_self()
    except SystemExit:
        pass
assert calls == [(sys.executable, sys.orig_argv)], calls

print("PASS: updater menolak menimpa pekerjaan lokal, tidak jatuh ke tarball, dan restart lewat execv")
