"""Backup and restore with XAMPP's mysqldump / mysql tools.

  python -m app.backup                      -> ../backups/panorama_YYYYMMDD_HHMMSS.sql   (schema + data + views, single transaction)
  python -m app.backup --restore FILE.sql   -> restores into the database (as the schema owner)

The password is passed through the MYSQL_PWD environment variable, never on the command line.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from .config import BACKUP_DIR, DB_HOST, DB_NAME, DB_OWNER_PASSWORD, DB_OWNER_USER, DB_PORT, XAMPP_DIR

BIN = XAMPP_DIR / "mysql" / "bin"


def _env() -> dict:
    return {**os.environ, "MYSQL_PWD": DB_OWNER_PASSWORD}


def backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    out = BACKUP_DIR / f"panorama_{dt.datetime.now():%Y%m%d_%H%M%S}.sql"
    cmd = [str(BIN / "mysqldump.exe"), "-h", DB_HOST, "-P", str(DB_PORT), "-u", DB_OWNER_USER, "--single-transaction",
           "--routines", "--events", "--default-character-set=utf8mb4", "--result-file", str(out), DB_NAME]
    subprocess.run(cmd, env=_env(), check=True)
    return out


def restore(path: Path) -> None:
    with open(path, "rb") as f:
        subprocess.run([str(BIN / "mysql.exe"), "-h", DB_HOST, "-P", str(DB_PORT), "-u", DB_OWNER_USER, "--default-character-set=utf8mb4", DB_NAME],
                       env=_env(), stdin=f, check=True)


def main() -> int:
    if "--restore" in sys.argv:
        f = Path(sys.argv[sys.argv.index("--restore") + 1])
        restore(f)
        print(f"restored {f}")
        return 0
    out = backup()
    print(f"backup written: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
