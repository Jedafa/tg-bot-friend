"""SQLite-хранилище: пользователи и админы, ID админов лежат только в зашифрованном виде."""
import os
import sqlite3
from pathlib import Path

import crypto

data_dir = Path(os.getenv("DATA_DIR") or ("/data" if Path("/data").is_dir() else "data"))
data_dir.mkdir(parents=True, exist_ok=True)

_db = sqlite3.connect(data_dir / "botfriend.db")
_db.execute(
    "CREATE TABLE IF NOT EXISTS users ("
    "chat_id INTEGER PRIMARY KEY, "
    "username TEXT NOT NULL DEFAULT '', "
    "full_name TEXT NOT NULL DEFAULT '', "
    "registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)
_db.execute(
    "CREATE TABLE IF NOT EXISTS admins ("
    "secret TEXT PRIMARY KEY, "
    "added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)
_db.execute(
    "CREATE TABLE IF NOT EXISTS one_time_admin ("
    "id INTEGER PRIMARY KEY CHECK (id = 1), "
    "available INTEGER NOT NULL DEFAULT 1, "
    "used_by TEXT NOT NULL DEFAULT '', "
    "used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)
_db.execute("INSERT OR IGNORE INTO one_time_admin (id) VALUES (1)")
_db.commit()


def register_user(chat_id: int, username: str, full_name: str) -> None:
    _db.execute(
        "INSERT OR REPLACE INTO users (chat_id, username, full_name) VALUES (?, ?, ?)",
        (chat_id, username, full_name),
    )
    _db.commit()


def all_users() -> list:
    return _db.execute("SELECT chat_id, username, full_name FROM users ORDER BY chat_id").fetchall()


def user_label(chat_id: int) -> str:
    row = _db.execute("SELECT chat_id, username, full_name FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    name = row_label(row) if row else "неизвестный"
    return f"{name} · ID {chat_id}"


def row_label(row: tuple) -> str:
    _, username, full_name = row
    return f"@{username}" if username else (full_name or "без имени")


def add_admin(chat_id: int) -> None:
    _db.execute("INSERT OR REPLACE INTO admins (secret) VALUES (?)", (crypto.encrypt_identifier(chat_id),))
    _db.commit()


def admin_ids() -> list:
    found = []
    for (secret,) in _db.execute("SELECT secret FROM admins").fetchall():
        try:
            found.append(crypto.decrypt_identifier(secret))
        except ValueError:
            continue
    return found


def admin_count() -> int:
    return len(_db.execute("SELECT secret FROM admins").fetchall())


def is_admin(chat_id: int) -> bool:
    return chat_id in admin_ids()


def remove_admin(chat_id: int) -> None:
    for (secret,) in _db.execute("SELECT secret FROM admins").fetchall():
        try:
            stored = crypto.decrypt_identifier(secret)
        except ValueError:
            continue
        if stored == chat_id:
            _db.execute("DELETE FROM admins WHERE secret = ?", (secret,))
    _db.commit()


def one_time_admin_state() -> tuple:
    return _db.execute("SELECT available, used_by, used_at FROM one_time_admin WHERE id = 1").fetchone()


def claim_one_time_admin(chat_id: int) -> bool:
    cursor = _db.execute(
        "UPDATE one_time_admin SET available = 0, used_by = ?, used_at = CURRENT_TIMESTAMP WHERE id = 1 AND available = 1",
        (crypto.encrypt_identifier(chat_id),),
    )
    _db.commit()
    return cursor.rowcount == 1


def rearm_one_time_admin() -> None:
    _db.execute("UPDATE one_time_admin SET available = 1 WHERE id = 1")
    _db.commit()


def bootstrap_owner(owner_id: int) -> None:
    if owner_id and admin_count() == 0:
        add_admin(owner_id)
