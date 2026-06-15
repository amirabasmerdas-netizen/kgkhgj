"""
AMEL SELF55 - پایگاه داده
مدیریت SQLite برای تنظیمات، دوستان، دشمنان و سشن‌ها
"""

import sqlite3
import json
import logging
from datetime import datetime
from config import DB_PATH, TIMEZONE

import pytz

logger = logging.getLogger(__name__)
tz = pytz.timezone(TIMEZONE)


def get_connection():
    """اتصال به پایگاه داده با پشتیبانی از thread"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """ایجاد جداول پایگاه داده"""
    conn = get_connection()
    cursor = conn.cursor()

    # ── جدول تنظیمات ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── جدول دوستان ───────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── جدول دشمنان ───────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enemies (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── جدول پیام‌های حذف‌شده (ضد حذف) ─────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deleted_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            sender_id INTEGER,
            sender_name TEXT,
            text TEXT,
            media_path TEXT,
            deleted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── جدول اسلات‌های ذخیره پیام ────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_slots (
            slot INTEGER PRIMARY KEY,
            content TEXT,
            saved_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── جدول پیام‌های زمان‌بندی‌شده ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message TEXT,
            send_at TEXT,
            sent INTEGER DEFAULT 0
        )
    """)

    # ── تنظیمات پیش‌فرض ───────────────────────────────────────────────────────
    defaults = {
        "self_active": "true",
        "secretary_active": "false",
        "anti_delete_active": "false",
        "pv_lock_active": "false",
        "anti_link_active": "false",
        "auto_seen_active": "false",
        "auto_reaction_active": "false",
        "default_reaction": "👍",
        "secretary_message": "سلام! در حال حاضر در دسترس نیستم. به زودی پاسخ می‌دهم. 🌸",
        "spam_count": "5",
        "translator_default_lang": "en",
    }

    for key, value in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    conn.commit()
    conn.close()
    logger.info("✅ پایگاه داده با موفقیت راه‌اندازی شد.")


# ════════════════════════════════════════════════════════════════════════════════
#  توابع تنظیمات
# ════════════════════════════════════════════════════════════════════════════════

def get_setting(key: str, default=None):
    """دریافت یک تنظیم از پایگاه داده"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str):
    """ذخیره یک تنظیم در پایگاه داده"""
    conn = get_connection()
    try:
        now = datetime.now(tz).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(value), now)
        )
        conn.commit()
    finally:
        conn.close()


def get_all_settings() -> dict:
    """دریافت همه تنظیمات"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════════
#  توابع دوستان
# ════════════════════════════════════════════════════════════════════════════════

def add_friend(user_id: int, username: str = "", name: str = ""):
    """اضافه کردن دوست"""
    conn = get_connection()
    try:
        now = datetime.now(tz).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO friends (user_id, username, name, added_at) VALUES (?, ?, ?, ?)",
            (user_id, username, name, now)
        )
        conn.commit()
        # اگر دشمن بود، حذف کن
        conn.execute("DELETE FROM enemies WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def remove_friend(user_id: int):
    """حذف دوست"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM friends WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_friend(user_id: int) -> bool:
    """بررسی دوست بودن کاربر"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM friends WHERE user_id=?", (user_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def get_all_friends() -> list:
    """دریافت لیست همه دوستان"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM friends ORDER BY added_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════════
#  توابع دشمنان
# ════════════════════════════════════════════════════════════════════════════════

def add_enemy(user_id: int, username: str = "", name: str = ""):
    """اضافه کردن دشمن"""
    conn = get_connection()
    try:
        now = datetime.now(tz).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO enemies (user_id, username, name, added_at) VALUES (?, ?, ?, ?)",
            (user_id, username, name, now)
        )
        conn.commit()
        # اگر دوست بود، حذف کن
        conn.execute("DELETE FROM friends WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def remove_enemy(user_id: int):
    """حذف دشمن"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM enemies WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_enemy(user_id: int) -> bool:
    """بررسی دشمن بودن کاربر"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM enemies WHERE user_id=?", (user_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def get_all_enemies() -> list:
    """دریافت لیست همه دشمنان"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM enemies ORDER BY added_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════════
#  توابع ضد حذف
# ════════════════════════════════════════════════════════════════════════════════

def save_deleted_message(chat_id: int, message_id: int, sender_id: int,
                          sender_name: str, text: str, media_path: str = ""):
    """ذخیره پیام حذف‌شده"""
    conn = get_connection()
    try:
        now = datetime.now(tz).isoformat()
        conn.execute("""
            INSERT INTO deleted_messages 
            (chat_id, message_id, sender_id, sender_name, text, media_path, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, message_id, sender_id, sender_name, text, media_path, now))
        conn.commit()
    finally:
        conn.close()


def get_recent_deleted(chat_id: int, limit: int = 5) -> list:
    """دریافت پیام‌های حذف‌شده اخیر یک چت"""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM deleted_messages 
            WHERE chat_id=? ORDER BY deleted_at DESC LIMIT ?
        """, (chat_id, limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════════
#  توابع اسلات پیام
# ════════════════════════════════════════════════════════════════════════════════

def save_message_slot(slot: int, content: str):
    """ذخیره پیام در اسلات"""
    conn = get_connection()
    try:
        now = datetime.now(tz).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO message_slots (slot, content, saved_at) VALUES (?, ?, ?)",
            (slot, content, now)
        )
        conn.commit()
    finally:
        conn.close()


def get_message_slot(slot: int) -> str | None:
    """دریافت پیام از اسلات"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT content FROM message_slots WHERE slot=?", (slot,)).fetchone()
        return row["content"] if row else None
    finally:
        conn.close()


def get_all_slots() -> list:
    """دریافت همه اسلات‌ها"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT slot, content, saved_at FROM message_slots ORDER BY slot").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
