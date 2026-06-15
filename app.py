"""
AMEL SELF55 - پنل وب
رابط کاربری فارسی برای مدیریت سلف‌بات از طریق مرورگر
"""

import asyncio
import logging
import os
import threading
from datetime import datetime

import pytz
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PasswordHashInvalidError
)

import database as db
from config import (
    API_ID, API_HASH, SESSION_NAME, PORT,
    SECRET_KEY, TIMEZONE, BOT_NAME
)
from texts import SECRETARY_DEFAULT

# ── راه‌اندازی Flask ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── لاگ‌گذاری ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tz = pytz.timezone(TIMEZONE)

# ── loop و thread ربات ────────────────────────────────────────────────────────
_bot_loop: asyncio.AbstractEventLoop | None = None
_bot_client: TelegramClient | None = None
_login_client: TelegramClient | None = None
_phone_code_hash: str | None = None


def get_tehran_time() -> str:
    return datetime.now(tz).strftime("%Y/%m/%d — %H:%M:%S")


# ════════════════════════════════════════════════════════════════════════════════
#  مسیر Keep-Alive (برای UptimeRobot)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/keepalive")
@app.route("/ping")
def keepalive():
    return jsonify({"status": "alive", "bot": BOT_NAME, "time": get_tehran_time()})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════════════════════
#  صفحه اصلی / پنل
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    settings = db.get_all_settings()
    friends = db.get_all_friends()
    enemies = db.get_all_enemies()
    slots = db.get_all_slots()
    return render_template(
        "panel.html",
        settings=settings,
        friends=friends,
        enemies=enemies,
        slots=slots,
        time=get_tehran_time(),
        bot_name=BOT_NAME,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  ورود — مرحله ۱: شماره تلفن
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    global _login_client, _phone_code_hash, _bot_loop

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        if not phone:
            flash("❌ شماره تلفن را وارد کنید.", "error")
            return render_template("login.html", step="phone")

        # ایجاد loop جداگانه برای عملیات async
        loop = asyncio.new_event_loop()
        _bot_loop = loop

        async def send_code():
            global _login_client, _phone_code_hash
            _login_client = TelegramClient(SESSION_NAME, API_ID, API_HASH, loop=loop)
            await _login_client.connect()
            result = await _login_client.send_code_request(phone)
            _phone_code_hash = result.phone_code_hash
            return True

        try:
            loop.run_until_complete(send_code())
            session["phone"] = phone
            flash("✅ کد تأیید ارسال شد.", "success")
            return redirect(url_for("verify_code"))
        except Exception as e:
            logger.error(f"خطا در ارسال کد: {e}")
            flash(f"❌ خطا: {e}", "error")

    return render_template("login.html", step="phone", bot_name=BOT_NAME)


# ════════════════════════════════════════════════════════════════════════════════
#  ورود — مرحله ۲: تأیید کد
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/verify", methods=["GET", "POST"])
def verify_code():
    global _login_client, _phone_code_hash

    if not session.get("phone"):
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        phone = session["phone"]

        async def sign_in():
            global _login_client
            await _login_client.sign_in(phone, code, phone_code_hash=_phone_code_hash)

        try:
            _bot_loop.run_until_complete(sign_in())
            session["logged_in"] = True
            flash("✅ با موفقیت وارد شدید!", "success")
            _start_bot_thread()
            return redirect(url_for("index"))
        except SessionPasswordNeededError:
            flash("🔒 رمز دو مرحله‌ای لازم است.", "info")
            return redirect(url_for("two_fa"))
        except PhoneCodeInvalidError:
            flash("❌ کد وارد‌شده اشتباه است.", "error")
        except Exception as e:
            flash(f"❌ خطا: {e}", "error")

    return render_template("login.html", step="code", bot_name=BOT_NAME)


# ════════════════════════════════════════════════════════════════════════════════
#  ورود — مرحله ۳: رمز دو مرحله‌ای
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/2fa", methods=["GET", "POST"])
def two_fa():
    global _login_client

    if request.method == "POST":
        password = request.form.get("password", "").strip()

        async def check_password():
            await _login_client.sign_in(password=password)

        try:
            _bot_loop.run_until_complete(check_password())
            session["logged_in"] = True
            flash("✅ با موفقیت وارد شدید!", "success")
            _start_bot_thread()
            return redirect(url_for("index"))
        except PasswordHashInvalidError:
            flash("❌ رمز عبور اشتباه است.", "error")
        except Exception as e:
            flash(f"❌ خطا: {e}", "error")

    return render_template("login.html", step="2fa", bot_name=BOT_NAME)


# ════════════════════════════════════════════════════════════════════════════════
#  خروج
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/logout")
def logout():
    session.clear()
    flash("✅ خارج شدید.", "info")
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════════════════════════
#  API: تغییر تنظیمات
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    key = request.json.get("key")
    current = db.get_setting(key, "false")
    new_val = "false" if current == "true" else "true"
    db.set_setting(key, new_val)
    return jsonify({"key": key, "value": new_val})


@app.route("/api/setting", methods=["POST"])
def api_setting():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    key = data.get("key")
    value = data.get("value", "")
    db.set_setting(key, value)
    return jsonify({"key": key, "value": value})


@app.route("/api/status")
def api_status():
    settings = db.get_all_settings()
    return jsonify({
        "settings": settings,
        "friends_count": len(db.get_all_friends()),
        "enemies_count": len(db.get_all_enemies()),
        "time": get_tehran_time(),
    })


@app.route("/api/friends")
def api_friends():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(db.get_all_friends())


@app.route("/api/enemies")
def api_enemies():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(db.get_all_enemies())


@app.route("/api/remove_friend", methods=["POST"])
def api_remove_friend():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    user_id = request.json.get("user_id")
    db.remove_friend(int(user_id))
    return jsonify({"success": True})


@app.route("/api/remove_enemy", methods=["POST"])
def api_remove_enemy():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    user_id = request.json.get("user_id")
    db.remove_enemy(int(user_id))
    return jsonify({"success": True})


@app.route("/api/deleted_messages")
def api_deleted():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    chat_id = request.args.get("chat_id", 0, type=int)
    msgs = db.get_recent_deleted(chat_id, limit=10)
    return jsonify(msgs)


# ════════════════════════════════════════════════════════════════════════════════
#  راه‌اندازی ربات در thread جداگانه
# ════════════════════════════════════════════════════════════════════════════════

def _start_bot_thread():
    """شروع ربات در یک thread جداگانه"""
    def run():
        from bot import start_bot
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_bot())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    logger.info("🤖 thread ربات شروع شد.")


# ════════════════════════════════════════════════════════════════════════════════
#  اجرا
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=PORT, debug=False)
