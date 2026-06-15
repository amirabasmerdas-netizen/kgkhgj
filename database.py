"""
AMEL SELF55 v2 — پایگاه داده
SQLite کامل با پشتیبانی از تمام توابع مورد نیاز
"""

import sqlite3
import logging
from datetime import datetime
import pytz

from config import DB_PATH, TIMEZONE

logger = logging.getLogger(__name__)
tz = pytz.timezone(TIMEZONE)


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def now_iso():
    return datetime.now(tz).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
#  راه‌اندازی جداول
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    c = _conn()
    cur = c.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        owner_id  INTEGER,
        key       TEXT,
        value     TEXT,
        PRIMARY KEY (owner_id, key)
    );

    CREATE TABLE IF NOT EXISTS users (
        owner_id    INTEGER PRIMARY KEY,
        tg_user_id  INTEGER,
        session_str TEXT,
        created_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS friends (
        owner_id  INTEGER,
        user_id   INTEGER,
        username  TEXT,
        name      TEXT,
        added_at  TEXT,
        PRIMARY KEY (owner_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS enemies (
        owner_id  INTEGER,
        user_id   INTEGER,
        username  TEXT,
        name      TEXT,
        added_at  TEXT,
        PRIMARY KEY (owner_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS silent_chats (
        owner_id INTEGER,
        chat_id  INTEGER,
        PRIMARY KEY (owner_id, chat_id)
    );

    CREATE TABLE IF NOT EXISTS silent_users (
        owner_id INTEGER,
        user_id  INTEGER,
        PRIMARY KEY (owner_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS deleted_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id    INTEGER,
        chat_id     INTEGER,
        message_id  INTEGER,
        sender_id   INTEGER,
        sender_name TEXT,
        text        TEXT,
        media_path  TEXT,
        deleted_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS message_slots (
        owner_id   INTEGER,
        slot       INTEGER,
        content    TEXT,
        saved_at   TEXT,
        PRIMARY KEY (owner_id, slot)
    );

    CREATE TABLE IF NOT EXISTS scheduled_messages (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id  INTEGER,
        chat_id   INTEGER,
        message   TEXT,
        send_at   TEXT,
        sent      INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS tokens (
        owner_id INTEGER PRIMARY KEY,
        balance  INTEGER DEFAULT 0
    );
    """)

    c.commit()
    c.close()
    logger.info("✅ پایگاه داده راه‌اندازی شد.")


# ══════════════════════════════════════════════════════════════════════════════
#  تنظیمات
# ══════════════════════════════════════════════════════════════════════════════

def get_setting(owner_id: int, key: str, default=None):
    c = _conn()
    try:
        row = c.execute(
            "SELECT value FROM settings WHERE owner_id=? AND key=?",
            (owner_id, key)
        ).fetchone()
        return row["value"] if row else default
    finally:
        c.close()


def set_setting(owner_id: int, key: str, value: str):
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO settings (owner_id, key, value) VALUES (?,?,?)",
            (owner_id, key, str(value))
        )
        c.commit()
    finally:
        c.close()


def get_all_settings(owner_id: int) -> dict:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT key, value FROM settings WHERE owner_id=?", (owner_id,)
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  کاربران / سشن
# ══════════════════════════════════════════════════════════════════════════════

def save_session(owner_id: int, session_str: str):
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO users (owner_id, session_str, created_at) VALUES (?,?,?)",
            (owner_id, session_str, now_iso())
        )
        c.commit()
    finally:
        c.close()


def get_session(owner_id: int) -> str:
    c = _conn()
    try:
        row = c.execute(
            "SELECT session_str FROM users WHERE owner_id=?", (owner_id,)
        ).fetchone()
        return row["session_str"] if row else ""
    finally:
        c.close()


def save_telegram_user_id(owner_id: int, tg_id: int):
    c = _conn()
    try:
        c.execute(
            "UPDATE users SET tg_user_id=? WHERE owner_id=?", (tg_id, owner_id)
        )
        if c.execute("SELECT changes()").fetchone()[0] == 0:
            c.execute(
                "INSERT OR IGNORE INTO users (owner_id, tg_user_id, created_at) VALUES (?,?,?)",
                (owner_id, tg_id, now_iso())
            )
        c.commit()
    finally:
        c.close()


def get_telegram_id_by_owner(owner_id: int):
    c = _conn()
    try:
        row = c.execute(
            "SELECT tg_user_id FROM users WHERE owner_id=?", (owner_id,)
        ).fetchone()
        return row["tg_user_id"] if row else None
    finally:
        c.close()


def get_all_users() -> list:
    c = _conn()
    try:
        return [dict(r) for r in c.execute("SELECT * FROM users").fetchall()]
    finally:
        c.close()


def delete_user(owner_id: int):
    c = _conn()
    try:
        c.execute("DELETE FROM users WHERE owner_id=?", (owner_id,))
        c.execute("DELETE FROM settings WHERE owner_id=?", (owner_id,))
        c.commit()
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  دوستان
# ══════════════════════════════════════════════════════════════════════════════

def add_friend(owner_id: int, user_id: int, username: str = "", name: str = ""):
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO friends (owner_id,user_id,username,name,added_at) VALUES (?,?,?,?,?)",
            (owner_id, user_id, username or "", name or "", now_iso())
        )
        c.execute("DELETE FROM enemies WHERE owner_id=? AND user_id=?", (owner_id, user_id))
        c.commit()
    finally:
        c.close()


def remove_friend(owner_id: int, user_id: int) -> bool:
    c = _conn()
    try:
        c.execute("DELETE FROM friends WHERE owner_id=? AND user_id=?", (owner_id, user_id))
        c.commit()
        return c.execute("SELECT changes()").fetchone()[0] > 0
    finally:
        c.close()


def is_friend(owner_id: int, user_id: int) -> bool:
    c = _conn()
    try:
        return bool(c.execute(
            "SELECT 1 FROM friends WHERE owner_id=? AND user_id=?", (owner_id, user_id)
        ).fetchone())
    finally:
        c.close()


def get_friends(owner_id: int) -> list:
    c = _conn()
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM friends WHERE owner_id=? ORDER BY added_at DESC", (owner_id,)
        ).fetchall()]
    finally:
        c.close()


def clear_friends(owner_id: int):
    c = _conn()
    try:
        c.execute("DELETE FROM friends WHERE owner_id=?", (owner_id,))
        c.commit()
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  دشمنان
# ══════════════════════════════════════════════════════════════════════════════

def add_enemy(owner_id: int, user_id: int, username: str = "", name: str = ""):
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO enemies (owner_id,user_id,username,name,added_at) VALUES (?,?,?,?,?)",
            (owner_id, user_id, username or "", name or "", now_iso())
        )
        c.execute("DELETE FROM friends WHERE owner_id=? AND user_id=?", (owner_id, user_id))
        c.commit()
    finally:
        c.close()


def remove_enemy(owner_id: int, user_id: int) -> bool:
    c = _conn()
    try:
        c.execute("DELETE FROM enemies WHERE owner_id=? AND user_id=?", (owner_id, user_id))
        c.commit()
        return c.execute("SELECT changes()").fetchone()[0] > 0
    finally:
        c.close()


def is_enemy(owner_id: int, user_id: int) -> bool:
    c = _conn()
    try:
        return bool(c.execute(
            "SELECT 1 FROM enemies WHERE owner_id=? AND user_id=?", (owner_id, user_id)
        ).fetchone())
    finally:
        c.close()


def get_enemies(owner_id: int) -> list:
    c = _conn()
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM enemies WHERE owner_id=? ORDER BY added_at DESC", (owner_id,)
        ).fetchall()]
    finally:
        c.close()


def clear_enemies(owner_id: int):
    c = _conn()
    try:
        c.execute("DELETE FROM enemies WHERE owner_id=?", (owner_id,))
        c.commit()
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  سایلنت
# ══════════════════════════════════════════════════════════════════════════════

def add_silent_chat(owner_id: int, chat_id: int):
    c = _conn()
    try:
        c.execute("INSERT OR IGNORE INTO silent_chats VALUES (?,?)", (owner_id, chat_id))
        c.commit()
    finally:
        c.close()


def remove_silent_chat(owner_id: int, chat_id: int):
    c = _conn()
    try:
        c.execute("DELETE FROM silent_chats WHERE owner_id=? AND chat_id=?", (owner_id, chat_id))
        c.commit()
    finally:
        c.close()


def is_silent_chat(owner_id: int, chat_id: int) -> bool:
    c = _conn()
    try:
        return bool(c.execute(
            "SELECT 1 FROM silent_chats WHERE owner_id=? AND chat_id=?", (owner_id, chat_id)
        ).fetchone())
    finally:
        c.close()


def add_silent_user(owner_id: int, user_id: int):
    c = _conn()
    try:
        c.execute("INSERT OR IGNORE INTO silent_users VALUES (?,?)", (owner_id, user_id))
        c.commit()
    finally:
        c.close()


def remove_silent_user(owner_id: int, user_id: int):
    c = _conn()
    try:
        c.execute("DELETE FROM silent_users WHERE owner_id=? AND user_id=?", (owner_id, user_id))
        c.commit()
    finally:
        c.close()


def is_silent_user(owner_id: int, user_id: int) -> bool:
    c = _conn()
    try:
        return bool(c.execute(
            "SELECT 1 FROM silent_users WHERE owner_id=? AND user_id=?", (owner_id, user_id)
        ).fetchone())
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  ضد حذف
# ══════════════════════════════════════════════════════════════════════════════

def save_deleted_message(owner_id, chat_id, message_id, sender_id, sender_name, text, media_path=""):
    c = _conn()
    try:
        c.execute("""
            INSERT INTO deleted_messages
            (owner_id,chat_id,message_id,sender_id,sender_name,text,media_path,deleted_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (owner_id, chat_id, message_id, sender_id, sender_name, text, media_path, now_iso()))
        c.commit()
    finally:
        c.close()


def get_recent_deleted(owner_id: int, chat_id: int = 0, limit: int = 5) -> list:
    c = _conn()
    try:
        if chat_id:
            rows = c.execute("""
                SELECT * FROM deleted_messages WHERE owner_id=? AND chat_id=?
                ORDER BY deleted_at DESC LIMIT ?
            """, (owner_id, chat_id, limit)).fetchall()
        else:
            rows = c.execute("""
                SELECT * FROM deleted_messages WHERE owner_id=?
                ORDER BY deleted_at DESC LIMIT ?
            """, (owner_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  اسلات پیام
# ══════════════════════════════════════════════════════════════════════════════

def save_message_slot(owner_id: int, slot: int, content: str):
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO message_slots (owner_id,slot,content,saved_at) VALUES (?,?,?,?)",
            (owner_id, slot, content, now_iso())
        )
        c.commit()
    finally:
        c.close()


def get_message_slot(owner_id: int, slot: int):
    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM message_slots WHERE owner_id=? AND slot=?", (owner_id, slot)
        ).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def get_all_slots(owner_id: int) -> list:
    c = _conn()
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM message_slots WHERE owner_id=? ORDER BY slot", (owner_id,)
        ).fetchall()]
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  ارسال زمان‌بندی‌شده
# ══════════════════════════════════════════════════════════════════════════════

def add_scheduled_message(owner_id: int, chat_id: int, message: str, send_at: str):
    c = _conn()
    try:
        c.execute(
            "INSERT INTO scheduled_messages (owner_id,chat_id,message,send_at) VALUES (?,?,?,?)",
            (owner_id, chat_id, message, send_at)
        )
        c.commit()
    finally:
        c.close()


def get_pending_scheduled(owner_id: int) -> list:
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c = _conn()
    try:
        return [dict(r) for r in c.execute("""
            SELECT * FROM scheduled_messages
            WHERE owner_id=? AND sent=0 AND send_at <= ?
        """, (owner_id, now)).fetchall()]
    finally:
        c.close()


def mark_scheduled_sent(msg_id: int):
    c = _conn()
    try:
        c.execute("UPDATE scheduled_messages SET sent=1 WHERE id=?", (msg_id,))
        c.commit()
    finally:
        c.close()


# ══════════════════════════════════════════════════════════════════════════════
#  توکن
# ══════════════════════════════════════════════════════════════════════════════

def get_token_balance(owner_id: int) -> int:
    c = _conn()
    try:
        row = c.execute("SELECT balance FROM tokens WHERE owner_id=?", (owner_id,)).fetchone()
        return row["balance"] if row else 0
    finally:
        c.close()


def add_tokens(owner_id: int, amount: int):
    c = _conn()
    try:
        c.execute(
            "INSERT INTO tokens (owner_id,balance) VALUES (?,?) ON CONFLICT(owner_id) DO UPDATE SET balance=balance+?",
            (owner_id, amount, amount)
        )
        c.commit()
    finally:
        c.close()


def deduct_tokens(owner_id: int, amount: int):
    c = _conn()
    try:
        c.execute(
            "UPDATE tokens SET balance=MAX(0,balance-?) WHERE owner_id=?", (amount, owner_id)
        )
        c.commit()
    finally:
        c.close()
