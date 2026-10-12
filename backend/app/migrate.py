"""Versioned schema migrations for MariaDB.

  python -m app.migrate            apply any new migrations/*.sql (idempotent), load the dataset if the fact table is empty
  python -m app.migrate --status   show which migrations are applied

Each file is applied once and recorded in `schema_migrations` with a SHA-256 checksum; if an applied file is edited later the
runner refuses to continue (fix forward with a new migration instead).  Runs as the schema OWNER account, never as the web
app's account.
"""
from __future__ import annotations

import hashlib
import re
import sys

from .config import DB_NAME, DB_USER, MIGRATIONS_DIR
from .db import DatabaseUnavailable, connect


class MigrationError(RuntimeError):
    pass


def _statements(sql: str):
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    for stmt in re.split(r";\s*(?:\n|$)", sql):
        stmt = stmt.strip()
        if stmt:
            yield stmt


def _render(sql: str) -> str:
    return sql.replace("@@DB@@", DB_NAME).replace("@@APP_USER@@", DB_USER)


def applied(conn) -> dict[str, str]:
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version VARCHAR(10) NOT NULL PRIMARY KEY, name VARCHAR(120) NOT NULL, checksum CHAR(64) NOT NULL,
        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    return {r["version"]: r["checksum"] for r in conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()}


def run_migrations(conn, verbose: bool = False) -> list[str]:
    done = applied(conn)
    ran: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        version = path.name.split("_", 1)[0]
        raw = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(raw.encode()).hexdigest()
        if version in done:
            if done[version] != checksum:
                raise MigrationError(f"Migration {path.name} was changed after it was applied. Add a new migration instead.")
            continue
        for stmt in _statements(_render(raw)):
            conn.execute(stmt)
        conn.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (?,?,?)", (version, path.name, checksum))
        conn.commit()
        ran.append(path.name)
        if verbose:
            print(f"applied {path.name}")
    return ran


def ensure_database(load_if_empty: bool = True, verbose: bool = False) -> dict:
    """Bring the database up to date: migrations, then the dataset and demo users if they are missing."""
    conn = connect(admin=True)
    try:
        ran = run_migrations(conn, verbose)
        n_orders = conn.execute("SELECT COUNT(*) c FROM fact_orders").fetchone()["c"]
        n_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        n_report = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    finally:
        conn.close()
    from . import ingest
    if load_if_empty and n_orders == 0:
        ingest.load_all(verbose=verbose)
    elif n_report != n_orders:  # self-heal: the reporting table must always mirror the fact table
        c2 = connect(admin=True)
        try:
            ingest.refresh_reporting(c2)
        finally:
            c2.close()
    if n_users == 0:
        ingest.seed_users(verbose=verbose)
    return {"migrations_applied": ran, "orders": n_orders, "users": n_users}


def main() -> int:
    try:
        if "--status" in sys.argv:
            conn = connect(admin=True)
            done = applied(conn)
            for p in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
                print(("applied  " if p.name.split("_", 1)[0] in done else "PENDING  ") + p.name)
            conn.close()
            return 0
        info = ensure_database(verbose=True)
        print(f"database up to date ({info})")
        return 0
    except DatabaseUnavailable as e:
        print(f"ERROR: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
