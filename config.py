"""
AMEL SELF55 v2 — پیکربندی
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API تلگرام ────────────────────────────────────────────────────────────────
API_ID   = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

# ── مالک (برای استفاده رایگان بدون توکن) ─────────────────────────────────────
OWNER_TG_ID = int(os.environ.get("OWNER_TG_ID", 0))   # آی‌دی عددی تلگرام
OWNER_PHONE = os.environ.get("OWNER_PHONE", "")        # مثال: +989123456789

# ── سیستم توکن (اگه نمی‌خوای خالی بذار) ──────────────────────────────────────
BOT_TOKEN        = os.environ.get("BOT_TOKEN", "")
TOKENS_PER_SESSION = int(os.environ.get("TOKENS_PER_SESSION", 0))
SESSION_HOURS    = int(os.environ.get("SESSION_HOURS", 24))

# ── فلسک ─────────────────────────────────────────────────────────────────────
PORT       = int(os.environ.get("PORT", 5000))
SECRET_KEY = os.environ.get("SECRET_KEY", "amel_self55_change_me")

# ── پایگاه داده ───────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "amel_self55.db")

# ── هواشناسی (رایگان از openweathermap.org) ───────────────────────────────────
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

# ── اطلاعات ربات ──────────────────────────────────────────────────────────────
BOT_NAME    = "AMEL SELF55"
BOT_VERSION = "2.0"
TIMEZONE    = "Asia/Tehran"
