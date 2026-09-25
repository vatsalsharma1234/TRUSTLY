import os
import sqlite3
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent / "doorstep.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS households (
    id TEXT PRIMARY KEY,
    plus_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    locality TEXT NOT NULL,
    landmark TEXT,
    phone TEXT,
    latitude REAL,
    longitude REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_households_locality ON households (locality);

CREATE TABLE IF NOT EXISTS vouches (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES households (id) ON DELETE CASCADE,
    voucher_name TEXT NOT NULL,
    voucher_phone TEXT,
    relation TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vouches_household_id ON vouches (household_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
