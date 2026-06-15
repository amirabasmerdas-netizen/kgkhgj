"""
AMEL SELF55 - پیکربندی
تنظیمات و متغیرهای محیطی پروژه
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── اطلاعات API تلگرام ──────────────────────────────────────────────────────
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "")

# ── تنظیمات فلسک ─────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 5000))
SECRET_KEY = os.environ.get("SECRET_KEY", "amel_self55_secret_key_change_me")
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

# ── مسیر پایگاه داده ─────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "amel_self55.db")

# ── نام سشن ───────────────────────────────────────────────────────────────────
SESSION_NAME = "amel_session"

# ── منطقه زمانی ───────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Tehran"

# ── تاخیر اسپم (ثانیه) ───────────────────────────────────────────────────────
SPAM_DELAY = float(os.environ.get("SPAM_DELAY", 1.5))

# ── حداکثر اسلات ذخیره پیام ──────────────────────────────────────────────────
MAX_MESSAGE_SLOTS = 10

# ── نسخه ربات ────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
BOT_NAME = "AMEL SELF55"
