"""Load allowed login codes/emails from a survey export.

Usage: python import_codes.py survey_export.csv COLUMN_NAME
Safe to run repeatedly; existing participants are kept.
Works with SQLite locally and with Postgres when DATABASE_URL is set.
(With LimeSurvey API sync configured in .env you may not need this at all.)
"""
import csv
import sys
import time
from contextlib import closing

from db import db, init_db

path, col = sys.argv[1], sys.argv[2]
init_db()
ids = {r[col].strip().lower() for r in csv.DictReader(open(path, encoding="utf-8-sig")) if r[col].strip()}
with closing(db()) as c, c:
    for i in ids:
        c.execute("INSERT OR IGNORE INTO participants(id, created_at) VALUES (?, ?)", (i, time.time()))
    total = c.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
print(len(ids), "identifiers processed;", total, "participants in total")
