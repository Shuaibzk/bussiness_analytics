"""MariaDB access layer (XAMPP, MySQL-compatible) built on PyMySQL.

Small on purpose: a thread-safe connection pool and a thin adapter that keeps the call style the rest of the app uses
(`db.execute(sql, params).fetchone()["col"]`, `?` placeholders, rows addressable by name or index) so the SQL stays in one
place and is parameterised everywhere.  Two kinds of connections:

  * connect() / get_db()            - the web app's least-privilege account (pooled)
  * connect(admin=True)             - the schema owner (migrations, bulk load, audit housekeeping, tests); never pooled
"""
from __future__ import annotations

import queue
import threading
from contextlib import contextmanager

import pymysql
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions

from .config import DB_HOST, DB_NAME, DB_OWNER_PASSWORD, DB_OWNER_USER, DB_PASSWORD, DB_POOL_SIZE, DB_PORT, DB_USER

# DECIMAL columns come back as exact numbers: scale-0 -> int (counts), otherwise float (money / averages)
def _dec(s):
    s = s.decode() if isinstance(s, (bytes, bytearray)) else s
    return int(s) if "." not in s else float(s)


_CONV = conversions.copy()
_CONV[FIELD_TYPE.NEWDECIMAL] = _dec
_CONV[FIELD_TYPE.DECIMAL] = _dec

# strict mode: bad data is rejected instead of silently truncated; timestamps are UTC
_INIT = ("SET SESSION sql_mode='STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ZERO_IN_DATE,NO_ZERO_DATE,NO_ENGINE_SUBSTITUTION', "
         "time_zone='+00:00'")


class DatabaseUnavailable(RuntimeError):
    """MariaDB cannot be reached or the credentials are wrong - with a message a human can act on."""


class Row(tuple):
    """A result row addressable by position (row[0]) or column name (row["name"]); dict(row) works."""

    _index: dict

    def __new__(cls, cols, values):
        obj = tuple.__new__(cls, values)
        obj._cols = cols
        obj._index = {c: i for i, c in enumerate(cols)}
        return obj

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._index[k])
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._cols)

    def get(self, k, default=None):
        return tuple.__getitem__(self, self._index[k]) if k in self._index else default


class Result:
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []
        self.rowcount = cur.rowcount
        self.lastrowid = cur.lastrowid

    def _wrap(self, values):
        return Row(self._cols, values)

    def fetchone(self):
        v = self._cur.fetchone()
        return self._wrap(v) if v is not None else None

    def fetchall(self):
        return [self._wrap(v) for v in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


def _prepare(sql: str) -> str:
    # PyMySQL uses %s placeholders: escape literal % first, then translate ? -> %s
    return sql.replace("%", "%%").replace("?", "%s")


class Conn:
    def __init__(self, raw, pooled: bool):
        self._raw = raw
        self._pooled = pooled

    def execute(self, sql: str, params=()) -> Result:
        cur = self._raw.cursor()
        try:
            cur.execute(_prepare(sql), tuple(params) if params else None)
        except Exception:
            cur.close()
            raise
        return Result(cur)

    def executemany(self, sql: str, seq) -> int:
        cur = self._raw.cursor()
        try:
            cur.executemany(_prepare(sql), seq)
            return cur.rowcount
        finally:
            cur.close()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        if self._pooled:
            _release(self._raw)
        else:
            try:
                self._raw.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------- pool
_pool: queue.LifoQueue = queue.LifoQueue(maxsize=DB_POOL_SIZE)
_lock = threading.Lock()


def _open(admin: bool):
    user, pw = (DB_OWNER_USER, DB_OWNER_PASSWORD) if admin else (DB_USER, DB_PASSWORD)
    try:
        return pymysql.connect(host=DB_HOST, port=DB_PORT, user=user, password=pw, database=DB_NAME, charset="utf8mb4",
                               conv=_CONV, init_command=_INIT, autocommit=False, connect_timeout=5, read_timeout=60, write_timeout=60)
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else 0
        if code in (2002, 2003, 2013):
            raise DatabaseUnavailable(
                f"Cannot reach MariaDB at {DB_HOST}:{DB_PORT}. Start XAMPP's MySQL (or run start.bat) and try again.") from e
        if code == 1045:
            raise DatabaseUnavailable(f"MariaDB rejected the login for '{user}'. Check DB_USER / DB_PASSWORD in backend/.env "
                                      "(run `python -m app.bootstrap_db` to create the accounts).") from e
        if code == 1049:
            raise DatabaseUnavailable(f"Database '{DB_NAME}' does not exist. Run `python -m app.bootstrap_db` first.") from e
        raise


def _release(raw) -> None:
    try:
        raw.rollback()  # never hand a connection back with an open transaction (stale REPEATABLE READ snapshot)
        _pool.put_nowait(raw)
    except queue.Full:
        raw.close()
    except Exception:
        try:
            raw.close()
        except Exception:
            pass


def _acquire():
    while True:
        try:
            raw = _pool.get_nowait()
        except queue.Empty:
            return _open(admin=False)
        try:
            raw.ping(reconnect=True)
            return raw
        except Exception:
            try:
                raw.close()
            except Exception:
                pass


def connect(admin: bool = False) -> Conn:
    return Conn(_open(True) if admin else _acquire(), pooled=not admin)


@contextmanager
def get_db(admin: bool = False):
    """Commit on a clean exit, roll back on an exception; the connection always goes back to the pool."""
    conn = connect(admin)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def read_df(sql: str, params=()):
    """Query -> pandas DataFrame (no SQLAlchemy needed)."""
    import pandas as pd

    with get_db() as db:
        res = db.execute(sql, params)
        rows = res.fetchall()
        return pd.DataFrame([tuple(r) for r in rows], columns=res._cols)


def ping() -> dict:
    """Health probe used by /api/health and the admin page."""
    with get_db() as db:
        v = db.execute("SELECT VERSION() v").fetchone()["v"]
        mb = db.execute("SELECT COALESCE(SUM(data_length + index_length), 0) / 1048576 mb FROM information_schema.tables "
                        "WHERE table_schema = DATABASE()").fetchone()["mb"]
    return {"engine": f"MariaDB {v.split('-')[0]}", "size_mb": round(float(mb), 2), "host": f"{DB_HOST}:{DB_PORT}", "database": DB_NAME}
