"""Database access. SQLite for local work, hosted Postgres when DATABASE_URL is set.

The app writes plain SQL with `?` placeholders; this module adapts it for Postgres so the
rest of the code is identical for both databases.
"""
import os
import sqlite3
from contextlib import closing

from dotenv import load_dotenv

load_dotenv()


class Row(tuple):
    """A result row that works like sqlite3.Row: row[0], row["name"], dict(row), row.keys()."""

    def __new__(cls, values, cols):
        obj = super().__new__(cls, values)
        obj._cols = list(cols)
        return obj

    def keys(self):
        return list(self._cols)

    def __getitem__(self, k):
        return super().__getitem__(self._cols.index(k) if isinstance(k, str) else k)


def _pg_sql(sql: str) -> str:
    sql = sql.replace("?", "%s")
    if sql.lstrip().upper().startswith("INSERT OR IGNORE"):
        sql = sql.replace("INSERT OR IGNORE", "INSERT", 1) + " ON CONFLICT DO NOTHING"
    return sql


class PGCursor:
    def __init__(self, cur):
        self.cur = cur

    def _wrap(self, values):
        return Row(values, [d.name for d in self.cur.description])

    def fetchone(self):
        r = self.cur.fetchone()
        return None if r is None else self._wrap(r)

    def fetchall(self):
        return [self._wrap(r) for r in self.cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PGConn:
    """Mimics the parts of sqlite3.Connection the app uses. `with conn:` commits or rolls back."""

    def __init__(self, url: str):
        import psycopg  # only needed when DATABASE_URL is set

        self.conn = psycopg.connect(url)

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(_pg_sql(sql), params)
        return PGCursor(cur)

    def executescript(self, sql):
        self.conn.execute(sql)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.rollback() if exc_type else self.conn.commit()

    def close(self):
        self.conn.close()


def db():
    url = os.getenv("DATABASE_URL")
    if url:
        return PGConn(url)
    c = sqlite3.connect(os.getenv("DB_PATH", "study.db"))
    c.row_factory = sqlite3.Row
    return c


def init_db():
    schema = "schema_pg.sql" if os.getenv("DATABASE_URL") else "schema.sql"
    with closing(db()) as c, c:
        c.executescript(open(schema).read())
