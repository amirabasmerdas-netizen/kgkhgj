"""
AMEL SELF55 - مدیریت دیتابیس
SQLite با پشتیبانی از کاربران نامحدود
"""

import sqlite3
import json
import logging
from datetime import datetime
import pytz
from config import DATABASE_PATH, TIMEZONE

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)


def get_now():
    """زمان فعلی به وقت تهران"""
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_connection():
    """اتصال به دیتابیس"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # بهینه‌سازی برای تعداد زیاد کاربران
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_db():
    """
    ایجاد جداول دیتابیس
    محدودیتی برای تعداد کاربران وجود ندارد
    """
    conn = get_connection()
    c = conn.cursor()

    # ── جدول کاربران (نامحدود) ──────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER UNIQUE NOT NULL,
            phone         TEXT,
            session_string TEXT,
            created_at    TEXT DEFAULT '',
            last_seen     TEXT DEFAULT '',
            is_active     INTEGER DEFAULT 1
        )
    """)

    # ── جدول تنظیمات هر کاربر ───────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id           INTEGER PRIMARY KEY,
            self_active       INTEGER DEFAULT 1,
            secretary_active  INTEGER DEFAULT 0,
            anti_delete       INTEGER DEFAULT 0,
            pv_lock           INTEGER DEFAULT 0,
            anti_link         INTEGER DEFAULT 0,
            auto_seen         INTEGER DEFAULT 0,
            auto_reaction     INTEGER DEFAULT 0,
            auto_forward      INTEGER DEFAULT 0,
            spam_active       INTEGER DEFAULT 0,
            updated_at        TEXT DEFAULT ''
        )
    """)

    # ── جدول دشمنان ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS enemies (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id   INTEGER NOT NULL,
            target_id  INTEGER NOT NULL,
            username   TEXT DEFAULT '',
            added_at   TEXT DEFAULT '',
            UNIQUE(owner_id, target_id)
        )
    """)

    # ── جدول دوستان ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id   INTEGER NOT NULL,
            target_id  INTEGER NOT NULL,
            username   TEXT DEFAULT '',
            added_at   TEXT DEFAULT '',
            UNIQUE(owner_id, target_id)
        )
    """)

    # ── جدول پیام‌های حذف‌شده ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS deleted_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id    INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            sender_id   INTEGER,
            text        TEXT DEFAULT '',
            media_path  TEXT DEFAULT '',
            deleted_at  TEXT DEFAULT ''
        )
    """)

    # ── جدول اسلات‌های پیام (1 تا 10) ────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS message_slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id  INTEGER NOT NULL,
            slot_num  INTEGER NOT NULL,
            content   TEXT DEFAULT '',
            saved_at  TEXT DEFAULT '',
            UNIQUE(owner_id, slot_num)
        )
    """)

    # ── جدول پیام‌های زمان‌بندی‌شده ──────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id    INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            text        TEXT NOT NULL,
            send_at     TEXT NOT NULL,
            sent        INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT ''
        )
    """)

    # ── جدول رسانه‌های ذخیره‌شده ──────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS saved_media (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id    INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            file_path   TEXT NOT NULL,
            media_type  TEXT DEFAULT 'photo',
            saved_at    TEXT DEFAULT ''
        )
    """)

    # ── ایندکس‌ها برای بهبود عملکرد با کاربران زیاد ──────────────────────────
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_enemies_owner ON enemies(owner_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_friends_owner ON friends(owner_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_deleted_owner ON deleted_messages(owner_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_owner ON scheduled_messages(owner_id)")

    conn.commit()
    conn.close()
    logger.info("✅ دیتابیس با موفقیت راه‌اندازی شد (ظرفیت نامحدود)")


# ═══════════════════════════════════════════════════════════════════════════════
#  مدیریت کاربران
# ═══════════════════════════════════════════════════════════════════════════════

def register_user(user_id: int, phone: str, session_string: str) -> bool:
    """
    ثبت‌نام کاربر جدید — بدون هیچ محدودیتی در تعداد
    """
    conn = get_connection()
    try:
        now = get_now()
        conn.execute(
            """INSERT INTO users (user_id, phone, session_string, created_at, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   session_string = excluded.session_string,
                   phone = excluded.phone,
                   last_seen = excluded.last_seen,
                   is_active = 1""",
            (user_id, phone, session_string, now, now)
        )
        # تنظیمات پیش‌فرض برای کاربر جدید
        conn.execute(
            """INSERT OR IGNORE INTO settings (user_id, updated_at)
               VALUES (?, ?)""",
            (user_id, now)
        )
        conn.commit()
        logger.info(f"✅ کاربر {user_id} با موفقیت ثبت‌نام شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ثبت‌نام کاربر {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_user(user_id: int) -> dict | None:
    """دریافت اطلاعات کاربر"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_active_users() -> list[dict]:
    """دریافت تمام کاربران فعال — بدون محدودیت"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_active = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_users_count() -> int:
    """تعداد کل کاربران ثبت‌نام‌شده"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_active = 1").fetchone()
        return row["cnt"]
    finally:
        conn.close()


def update_user_session(user_id: int, session_string: str):
    """بروزرسانی سشن کاربر"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET session_string = ?, last_seen = ? WHERE user_id = ?",
            (session_string, get_now(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


def deactivate_user(user_id: int):
    """غیرفعال‌کردن کاربر"""
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  تنظیمات
# ═══════════════════════════════════════════════════════════════════════════════

def get_settings(user_id: int) -> dict:
    """دریافت تنظیمات کاربر"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        # مقادیر پیش‌فرض
        return {
            "user_id": user_id,
            "self_active": 1,
            "secretary_active": 0,
            "anti_delete": 0,
            "pv_lock": 0,
            "anti_link": 0,
            "auto_seen": 0,
            "auto_reaction": 0,
            "auto_forward": 0,
            "spam_active": 0,
        }
    finally:
        conn.close()


def update_setting(user_id: int, key: str, value: int):
    """بروزرسانی یک تنظیم خاص"""
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE settings SET {key} = ?, updated_at = ? WHERE user_id = ?",
            (value, get_now(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  سیستم دشمن / دوست
# ═══════════════════════════════════════════════════════════════════════════════

def add_enemy(owner_id: int, target_id: int, username: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO enemies (owner_id, target_id, username, added_at) VALUES (?,?,?,?)",
            (owner_id, target_id, username, get_now())
        )
        conn.commit()
    finally:
        conn.close()


def remove_enemy(owner_id: int, target_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM enemies WHERE owner_id=? AND target_id=?", (owner_id, target_id))
        conn.commit()
    finally:
        conn.close()


def get_enemies(owner_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM enemies WHERE owner_id=?", (owner_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_enemy(owner_id: int, target_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM enemies WHERE owner_id=? AND target_id=?", (owner_id, target_id)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def add_friend(owner_id: int, target_id: int, username: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO friends (owner_id, target_id, username, added_at) VALUES (?,?,?,?)",
            (owner_id, target_id, username, get_now())
        )
        conn.commit()
    finally:
        conn.close()


def remove_friend(owner_id: int, target_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM friends WHERE owner_id=? AND target_id=?", (owner_id, target_id))
        conn.commit()
    finally:
        conn.close()


def get_friends(owner_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM friends WHERE owner_id=?", (owner_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_friend(owner_id: int, target_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM friends WHERE owner_id=? AND target_id=?", (owner_id, target_id)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  پیام‌های حذف‌شده
# ═══════════════════════════════════════════════════════════════════════════════

def save_deleted_message(owner_id: int, chat_id: int, sender_id: int,
                          text: str, media_path: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO deleted_messages
               (owner_id, chat_id, sender_id, text, media_path, deleted_at)
               VALUES (?,?,?,?,?,?)""",
            (owner_id, chat_id, sender_id, text, media_path, get_now())
        )
        conn.commit()
    finally:
        conn.close()


def get_deleted_messages(owner_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM deleted_messages WHERE owner_id=? ORDER BY id DESC LIMIT ?",
            (owner_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  اسلات‌های پیام
# ═══════════════════════════════════════════════════════════════════════════════

def save_message_slot(owner_id: int, slot_num: int, content: str):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO message_slots (owner_id, slot_num, content, saved_at)
               VALUES (?,?,?,?)
               ON CONFLICT(owner_id, slot_num) DO UPDATE SET
                   content = excluded.content, saved_at = excluded.saved_at""",
            (owner_id, slot_num, content, get_now())
        )
        conn.commit()
    finally:
        conn.close()


def get_message_slot(owner_id: int, slot_num: int) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT content FROM message_slots WHERE owner_id=? AND slot_num=?",
            (owner_id, slot_num)
        ).fetchone()
        return row["content"] if row else None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  پیام‌های زمان‌بندی‌شده
# ═══════════════════════════════════════════════════════════════════════════════

def add_scheduled_message(owner_id: int, chat_id: int, text: str, send_at: str):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO scheduled_messages (owner_id, chat_id, text, send_at, created_at)
               VALUES (?,?,?,?,?)""",
            (owner_id, chat_id, text, send_at, get_now())
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_scheduled(owner_id: int) -> list[dict]:
    conn = get_connection()
    try:
        now = get_now()
        rows = conn.execute(
            """SELECT * FROM scheduled_messages
               WHERE owner_id=? AND sent=0 AND send_at <= ?""",
            (owner_id, now)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_scheduled_sent(msg_id: int):
    conn = get_connection()
    try:
        conn.execute("UPDATE scheduled_messages SET sent=1 WHERE id=?", (msg_id,))
        conn.commit()
    finally:
        conn.close()
