"""Load allowed login codes/emails from a survey export.

Usage: python import_codes.py survey_export.csv COLUMN_NAME
Safe to run repeatedly; existing participants are kept.
"""
import csv
import os
import sqlite3
import sys

path, col = sys.argv[1], sys.argv[2]
db = sqlite3.connect(os.getenv("DB_PATH", "study.db"))
db.executescript(open("schema.sql").read())
ids = {r[col].strip().lower() for r in csv.DictReader(open(path, encoding="utf-8-sig")) if r[col].strip()}
db.executemany("INSERT OR IGNORE INTO participants(id, created_at) VALUES (?, strftime('%s','now'))", [(i,) for i in ids])
db.commit()
print(len(ids), "identifiers processed;", db.execute("SELECT COUNT(*) FROM participants").fetchone()[0], "participants in total")
