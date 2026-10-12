"""One-time setup of the MariaDB side (run once, as an administrator of the server).

  python -m app.bootstrap_db [--root-user root] [--root-password ""] [--host 127.0.0.1] [--port 3307]

Creates the `panorama` database (utf8mb4) and two accounts with generated passwords that are written to backend/.env:
  * panorama_owner - owns the schema (migrations, bulk load, maintenance)
  * panorama_app   - what the web app uses at runtime (granted only what migration 004 allows)
Safe to re-run: existing accounts keep (and are re-synchronised to) the passwords in backend/.env.
"""
from __future__ import annotations

import argparse
import re
import secrets
import subprocess
import sys

import pymysql

from .config import BASE_DIR, DB_HOST, DB_NAME, DB_OWNER_USER, DB_PORT, DB_USER

ENV_FILE = BASE_DIR / ".env"


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


def _set_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Z_]+)\s*=", line)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            seen.add(m.group(1))
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-user", default="root")
    ap.add_argument("--root-password", default="")
    ap.add_argument("--host", default=DB_HOST)
    ap.add_argument("--port", type=int, default=DB_PORT)
    ap.add_argument("--no-migrate", action="store_true")
    a = ap.parse_args()

    env = _read_env()
    pw_app = env.get("DB_PASSWORD") or secrets.token_urlsafe(24)
    pw_owner = env.get("DB_OWNER_PASSWORD") or secrets.token_urlsafe(24)

    try:
        root = pymysql.connect(host=a.host, port=a.port, user=a.root_user, password=a.root_password, charset="utf8mb4", connect_timeout=5)
    except pymysql.err.OperationalError as e:
        print(f"ERROR: cannot connect to MariaDB at {a.host}:{a.port} as {a.root_user}: {e.args[-1]}")
        print("Start XAMPP's MySQL first (start.bat does it), or pass --root-password if root has one.")
        return 2
    cur = root.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    for host in ("localhost", "127.0.0.1"):
        for user, pw in ((DB_OWNER_USER, pw_owner), (DB_USER, pw_app)):
            cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (user, host, pw))
            cur.execute("ALTER USER %s@%s IDENTIFIED BY %s", (user, host, pw))  # keep the account in sync with backend/.env
        cur.execute(f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO %s@%s WITH GRANT OPTION", (DB_OWNER_USER, host))
    cur.execute("FLUSH PRIVILEGES")
    root.commit()
    root.close()
    _set_env({"DB_HOST": a.host, "DB_PORT": str(a.port), "DB_NAME": DB_NAME, "DB_USER": DB_USER, "DB_PASSWORD": pw_app,
              "DB_OWNER_USER": DB_OWNER_USER, "DB_OWNER_PASSWORD": pw_owner})
    print(f"database '{DB_NAME}' and accounts '{DB_OWNER_USER}' / '{DB_USER}' are ready (passwords saved in backend/.env)")
    if a.no_migrate:
        return 0
    # a fresh process, so the new passwords in backend/.env are picked up
    return subprocess.call([sys.executable, "-m", "app.migrate"], cwd=str(BASE_DIR))


if __name__ == "__main__":
    sys.exit(main())
