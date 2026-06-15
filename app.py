"""
AMEL SELF55 - پنل وب Flask
ثبت‌نام نامحدود کاربران + مدیریت سلف بات
"""

import asyncio
import logging
import os
import threading
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError,
    SessionPasswordNeededError, PasswordHashInvalidError,
    FloodWaitError
)

import database as db
import bot as bot_module
from config import API_ID, API_HASH, SECRET_KEY, PORT, HOST, VERSION, BOT_NAME

# ── لاگ ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── حلقه async مشترک ─────────────────────────────────────────────────────────
loop = asyncio.new_event_loop()

# ── ذخیره موقت کلاینت‌های در حال لاگین ──────────────────────────────────────
# کلید: phone | مقدار: TelegramClient (قبل از تکمیل لاگین)
pending_clients: dict[str, dict] = {}


def run_async(coro):
    """اجرای coroutine در حلقه async مشترک"""
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=60)


# ═══════════════════════════════════════════════════════════════════════════════
#  مسیرها
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("panel.html",
                           version=VERSION,
                           bot_name=BOT_NAME,
                           users_count=db.get_users_count())


@app.route("/keepalive")
def keepalive():
    """مسیر keep-alive برای UptimeRobot و Render"""
    return jsonify({
        "status": "alive",
        "bot": BOT_NAME,
        "version": VERSION,
        "active_clients": len(bot_module.active_clients),
        "users_count": db.get_users_count()
    })


@app.route("/api/status")
def api_status():
    """وضعیت کلی سیستم"""
    return jsonify({
        "status": "online",
        "active_clients": len(bot_module.active_clients),
        "total_users": db.get_users_count(),
        "max_users": "نامحدود"
    })


# ── لاگین: مرحله ۱ — ارسال شماره تلفن ──────────────────────────────────────

@app.route("/api/login/send_code", methods=["POST"])
def login_send_code():
    """
    مرحله اول لاگین — ارسال کد تأیید
    هیچ محدودیتی برای تعداد کاربران وجود ندارد
    """
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"success": False, "message": "شماره تلفن وارد نشده"}), 400

    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        run_async(client.connect())
        result = run_async(client.send_code_request(phone))

        pending_clients[phone] = {
            "client": client,
            "phone_code_hash": result.phone_code_hash,
        }

        logger.info(f"📲 کد ورود برای {phone} ارسال شد")
        return jsonify({"success": True, "message": "کد تأیید ارسال شد"})

    except FloodWaitError as e:
        return jsonify({"success": False, "message": f"تلگرام محدود کرده. {e.seconds} ثانیه صبر کنید"}), 429
    except Exception as e:
        logger.error(f"❌ خطا در ارسال کد: {e}")
        return jsonify({"success": False, "message": f"خطا: {str(e)}"}), 500


# ── لاگین: مرحله ۲ — تأیید کد ───────────────────────────────────────────────

@app.route("/api/login/verify_code", methods=["POST"])
def login_verify_code():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    code = (data.get("code") or "").strip()

    if not phone or not code:
        return jsonify({"success": False, "message": "شماره یا کد وارد نشده"}), 400

    if phone not in pending_clients:
        return jsonify({"success": False, "message": "ابتدا کد ارسال کنید"}), 400

    client = pending_clients[phone]["client"]
    phone_code_hash = pending_clients[phone]["phone_code_hash"]

    try:
        run_async(client.sign_in(phone, code, phone_code_hash=phone_code_hash))
        return _finish_login(phone, client)

    except SessionPasswordNeededError:
        return jsonify({"success": False, "need_2fa": True, "message": "رمز دو مرحله‌ای وارد کنید"})

    except PhoneCodeInvalidError:
        return jsonify({"success": False, "message": "کد اشتباه است"}), 400

    except PhoneCodeExpiredError:
        pending_clients.pop(phone, None)
        return jsonify({"success": False, "message": "کد منقضی شده. دوباره درخواست کنید"}), 400

    except Exception as e:
        logger.error(f"❌ خطا در تأیید کد: {e}")
        return jsonify({"success": False, "message": f"خطا: {str(e)}"}), 500


# ── لاگین: مرحله ۳ — رمز دو مرحله‌ای ──────────────────────────────────────

@app.route("/api/login/verify_2fa", methods=["POST"])
def login_verify_2fa():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""

    if not phone or not password:
        return jsonify({"success": False, "message": "شماره یا رمز وارد نشده"}), 400

    if phone not in pending_clients:
        return jsonify({"success": False, "message": "ابتدا کد ارسال کنید"}), 400

    client = pending_clients[phone]["client"]

    try:
        run_async(client.sign_in(password=password))
        return _finish_login(phone, client)

    except PasswordHashInvalidError:
        return jsonify({"success": False, "message": "رمز دو مرحله‌ای اشتباه است"}), 400

    except Exception as e:
        logger.error(f"❌ خطا در ۲FA: {e}")
        return jsonify({"success": False, "message": f"خطا: {str(e)}"}), 500


def _finish_login(phone: str, client: TelegramClient):
    """تکمیل فرآیند لاگین و ذخیره سشن — بدون محدودیت کاربر"""
    try:
        me = run_async(client.get_me())
        session_string = client.session.save()

        # ثبت در دیتابیس (نامحدود)
        db.register_user(me.id, phone, session_string)

        # راه‌اندازی کلاینت فعال
        run_async(bot_module.start_client(me.id, session_string))

        pending_clients.pop(phone, None)

        logger.info(f"✅ کاربر {me.id} ({me.first_name}) با موفقیت وارد شد")
        return jsonify({
            "success": True,
            "message": f"✅ {me.first_name} با موفقیت وارد شد",
            "user_id": me.id,
            "name": me.first_name,
            "total_users": db.get_users_count()
        })

    except Exception as e:
        logger.error(f"❌ خطا در تکمیل لاگین: {e}")
        return jsonify({"success": False, "message": f"خطا: {str(e)}"}), 500


# ── تنظیمات کاربر ─────────────────────────────────────────────────────────────

@app.route("/api/settings/<int:user_id>", methods=["GET"])
def get_settings(user_id: int):
    settings = db.get_settings(user_id)
    return jsonify(settings)


@app.route("/api/settings/<int:user_id>", methods=["POST"])
def update_settings(user_id: int):
    data = request.json or {}
    allowed_keys = [
        "self_active", "secretary_active", "anti_delete",
        "pv_lock", "anti_link", "auto_seen", "auto_reaction"
    ]
    for key in allowed_keys:
        if key in data:
            db.update_setting(user_id, key, int(data[key]))
    return jsonify({"success": True, "message": "تنظیمات ذخیره شد"})


# ── آمار ──────────────────────────────────────────────────────────────────────

@app.route("/api/users")
def list_users():
    users = db.get_all_active_users()
    result = []
    for u in users:
        result.append({
            "user_id": u["user_id"],
            "phone": u["phone"],
            "created_at": u["created_at"],
            "last_seen": u["last_seen"],
            "is_online": u["user_id"] in bot_module.active_clients,
            "settings": db.get_settings(u["user_id"])
        })
    return jsonify({
        "total": len(result),
        "max": "نامحدود",
        "users": result
    })


@app.route("/api/users/<int:user_id>/logout", methods=["POST"])
def logout_user(user_id: int):
    run_async(bot_module.stop_client(user_id))
    db.deactivate_user(user_id)
    return jsonify({"success": True, "message": "کاربر خارج شد"})


# ═══════════════════════════════════════════════════════════════════════════════
#  اجرا
# ═══════════════════════════════════════════════════════════════════════════════

def start_bot_loop():
    """اجرای حلقه async در thread جداگانه"""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_module.run_all())


if __name__ == "__main__":
    # راه‌اندازی دیتابیس
    db.init_db()

    # راه‌اندازی ربات در thread جداگانه
    bot_thread = threading.Thread(target=start_bot_loop, daemon=True)
    bot_thread.start()

    logger.info(f"🚀 {BOT_NAME} v{VERSION} در حال اجرا روی پورت {PORT}")
    logger.info("👥 ظرفیت کاربران: نامحدود")

    # Flask
    app.run(host=HOST, port=PORT, debug=False)
