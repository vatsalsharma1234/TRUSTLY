import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_household(
    conn: sqlite3.Connection,
    *,
    name: str,
    locality: str,
    plus_code: str,
    landmark: Optional[str],
    phone: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
) -> dict:
    household_id = new_id()
    conn.execute(
        """
        INSERT INTO households
            (id, plus_code, name, locality, landmark, phone, latitude, longitude, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (household_id, plus_code, name, locality, landmark, phone, latitude, longitude, now_iso()),
    )
    conn.commit()
    return get_household_by_id(conn, household_id)


def get_household_by_id(conn: sqlite3.Connection, household_id: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM households WHERE id = ?", (household_id,)).fetchone()
    return dict(row) if row else None


def get_household_by_plus_code(conn: sqlite3.Connection, plus_code: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM households WHERE plus_code = ?", (plus_code,)).fetchone()
    return dict(row) if row else None


def list_households(conn: sqlite3.Connection, locality: Optional[str] = None) -> list[dict]:
    if locality:
        rows = conn.execute(
            "SELECT * FROM households WHERE locality LIKE ? ORDER BY created_at DESC",
            (f"%{locality}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM households ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def list_vouches(conn: sqlite3.Connection, household_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM vouches WHERE household_id = ? ORDER BY created_at DESC",
        (household_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def create_vouch(
    conn: sqlite3.Connection,
    *,
    household_id: str,
    voucher_name: str,
    voucher_phone: Optional[str],
    relation: str,
    note: Optional[str],
) -> dict:
    vouch_id = new_id()
    conn.execute(
        """
        INSERT INTO vouches
            (id, household_id, voucher_name, voucher_phone, relation, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (vouch_id, household_id, voucher_name, voucher_phone, relation, note, now_iso()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM vouches WHERE id = ?", (vouch_id,)).fetchone()
    return dict(row)
