import secrets
import sqlite3
from datetime import datetime

from werkzeug.security import check_password_hash

import database as db


def init_security():
    with sqlite3.connect(db.DATABASE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_recovery_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT
            )
        """)
        conn.commit()


def create_recovery_code(user_id):
    raw = secrets.token_hex(8).upper()
    code = "-".join(raw[index:index + 4] for index in range(0, 16, 4))
    with sqlite3.connect(db.DATABASE) as conn:
        conn.execute(
            "UPDATE password_recovery_codes SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
            (datetime.now().isoformat(timespec="seconds"), user_id),
        )
        conn.execute(
            "INSERT INTO password_recovery_codes (user_id, code_hash, created_at) VALUES (?, ?, ?)",
            (user_id, db.hash_secret(code), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    return code


def has_recovery_code(user_id):
    with sqlite3.connect(db.DATABASE) as conn:
        return conn.execute(
            "SELECT 1 FROM password_recovery_codes WHERE user_id = ? AND used_at IS NULL LIMIT 1",
            (user_id,),
        ).fetchone() is not None


def use_recovery_code(username, code):
    user = db.get_user_by_username((username or "").strip())
    if not user:
        return None
    with sqlite3.connect(db.DATABASE) as conn:
        rows = conn.execute(
            "SELECT id, code_hash FROM password_recovery_codes WHERE user_id = ? AND used_at IS NULL",
            (user["id"],),
        ).fetchall()
        for code_id, code_hash in rows:
            if check_password_hash(code_hash, (code or "").strip().upper()):
                conn.execute(
                    "UPDATE password_recovery_codes SET used_at = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), code_id),
                )
                conn.commit()
                return user
    return None
