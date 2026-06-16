import threading
import telebot
from telebot import types
import database as db
import config

_bot = None
BOT_USERNAME = None
OWNER_TG_ID = 8296865861  # آیدی عددی مالک

def get_bot():
    return _bot

def start_token_bot():
    global _bot, BOT_USERNAME

    if not config.BOT_TOKEN:
        print("⚠️ BOT_TOKEN تنظیم نشده — ربات توکن غیرفعال است")
        return

    _bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML", threaded=False)

    try:
        me = _bot.get_me()
        BOT_USERNAME = me.username
        print(f"🤖 ربات توکن: @{BOT_USERNAME}")
    except Exception as e:
        print(f"❌ خطا در اتصال ربات توکن: {e}")
        _bot = None
        return

    import time as _time
    for attempt in range(3):
        try:
            _bot.delete_webhook(drop_pending_updates=True)
            _time.sleep(3)
            break
        except:
            _time.sleep(3)

    # ─── تابع نمایش اجباری عضویت (اولین چیزی که کاربر می‌بیند) ─────────────
    def send_forced_channels_menu(message, missing_channels):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in missing_channels:
            ch_clean = ch.lstrip("@")
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در {ch}", url=f"https://t.me/{ch_clean}"))
        markup.add(types.InlineKeyboardButton("✅ بررسی عضویت من", callback_data="check_join"))
        
        channels_list = "\n".join([f"🔸 {ch}" for ch in missing_channels])
        _bot.reply_to(
            message,
            "⛔️ <b>ورود به ربات منوط به عضویت در کانال‌های زیر است:</b>\n\n"
            f"{channels_list}\n\n"
            "👇 روی هر کانال کلیک کنید و Join بزنید، سپس دکمه «بررسی عضویت من» را بزنید:",
            reply_markup=markup
        )

    # ─── /start (بررسی عضویت در خط اول) ─────────────────────────────────────
    @_bot.message_handler(commands=["start"])
    def cmd_start(message):
        tg_id = message.from_user.id
        
        # ۱. پردازش رفرال
        parts = message.text.strip().split()
        ref_code = parts[1] if len(parts) > 1 else None
        if ref_code and ref_code.startswith("ref_"):
            try:
                referrer_id = int(ref_code[4:])
                if db.process_referral(referrer_id, tg_id):
                    referrer_tg = db.get_telegram_id_by_owner(referrer_id)
                    if referrer_tg:
                        try:
                            _bot.send_message(referrer_tg, f"🎉 یک نفر با لینک شما عضو شد!\n<b>+{config.REFERRAL_TOKENS} توکن</b> دریافت کردید 🪙")
                        except: pass
            except: pass

        # ۲. بررسی فوری عضویت در کانال‌ها
        is_member, missing = db.check_user_membership(_bot, tg_id)
        if not is_member:
            send_forced_channels_menu(message, missing)
            return  # ⛔️ توقف اجرا! منوی اصلی نشان داده نمی‌شود.

        # ۳. اگر عضو بود، ادامه بده...
        site_url = getattr(config, "SITE_URL", "")
        account = db.get_account_by_tg_id(tg_id)

        if not account:
            markup = types.InlineKeyboardMarkup()
            if site_url:
                markup.add(types.InlineKeyboardButton("🌐 ورود به پنل وب", url=site_url))
            _bot.reply_to(message, "👋 <b>سلام!</b>\n\nبرای استفاده از ربات:\n1️⃣ در پنل وب ثبت‌نام کنید\n2️⃣ حساب تلگرام را وصل کنید\n3️⃣ دوباره /start بزنید", reply_markup=markup if site_url else None)
            return

        stats = db.get_token_stats(account["id"])
        
        # انتخاب کیبورد بر اساس مالک بودن
        if tg_id == OWNER_TG_ID:
            markup = _owner_keyboard()
        else:
            markup = _user_keyboard()

        _bot.reply_to(
            message,
            f"👋 سلام <b>{account['username']}</b>!\n\n"
            f"🪙 موجودی: <b>{stats['balance']}</b>\n"
            f"📊 کل دریافتی: <b>{stats['total_earned']}</b>\n\n"
            f"⚡ هر <b>۲ توکن</b> = <b>۲ ساعت</b> سلف‌بات",
            reply_markup=markup
        )

    # ─── هندلر دکمه بررسی عضویت ─────────────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data == "check_join")
    def callback_check_join(call):
        is_member, missing = db.check_user_membership(_bot, call.from_user.id)
        if is_member:
            _bot.answer_callback_query(call.id, "عضویت تأیید شد! ✅")
            try: _bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            cmd_start(call.message) # بازگشت به منوی اصلی
        else:
            _bot.answer_callback_query(call.id, f"هنوز در {len(missing)} کانال عضو نشده‌اید! ❌", show_alert=True)

    # ─── توابع کمکی برای بررسی عضویت در همه دکمه‌ها ─────────────────────────
    def require_membership(message):
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_forced_channels_menu(message, missing)
            return False
        return True

    # ─── دکمه‌های منوی اصلی (کاملاً دکمه‌ای) ───────────────────────────────
    @_bot.message_handler(func=lambda m: m.text == "💰 موجودی")
    def cmd_balance(message):
        if not require_membership(message): return
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account: return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")
        stats = db.get_token_stats(account["id"])
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(message, f"🪙 <b>موجودی توکن</b>\n\n💰 فعلی: <b>{stats['balance']}</b>\n📊 کل: <b>{stats['total_earned']}</b>\n👥 رفرال: <b>{ref_count}</b> نفر", reply_markup=_user_keyboard())

    @_bot.message_handler(func=lambda m: m.text == "🎁 هدیه روزانه")
    def cmd_daily(message):
        if not require_membership(message): return
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account: return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
        success, msg = db.claim_daily_token(account["id"])
        if success:
            stats = db.get_token_stats(account["id"])
            _bot.reply_to(message, f"{msg}\n\n💰 موجودی جدید: <b>{stats['balance']}</b>", reply_markup=_user_keyboard())
        else:
            _bot.reply_to(message, msg, reply_markup=_user_keyboard())

    @_bot.message_handler(func=lambda m: m.text == "🔗 رفرال")
    def cmd_referral(message):
        if not require_membership(message): return
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account: return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{account['id']}"
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(message, f"🔗 <b>لینک رفرال شما:</b>\n<code>{link}</code>\n\n👥 تعداد: <b>{ref_count}</b>\n🎁 پاداش: <b>{config.REFERRAL_TOKENS}</b> توکن", reply_markup=_user_keyboard())

    @_bot.message_handler(func=lambda m: m.text == "🛒 خرید توکن")
    def cmd_buy(message):
        if not require_membership(message): return
        account = db.get_account_by_tg_id(message.from_user.id)
        username_txt = account["username"] if account else str(message.from_user.id)
        markup = types.InlineKeyboardMarkup()
        if config.OWNER_USERNAME:
            markup.add(types.InlineKeyboardButton("📩 پیام به مالک", url=f"https://t.me/{config.OWNER_USERNAME}"))
        _bot.reply_to(message, f"🛒 <b>خرید توکن</b>\n\n👤 یوزرنیم پنل شما: <b>{username_txt}</b>\n\nبرای خرید به مالک پیام دهید.", reply_markup=markup)

    # ─── دستورات اختصاصی مالک (فقط با آیدی 8296865861 کار می‌کند) ─────────
    @_bot.message_handler(func=lambda m: m.text == "📢 مدیریت چنل‌ها")
    def cmd_admin_channels(message):
        if message.from_user.id != OWNER_TG_ID: return
        channels = db.get_forced_channels()
        if not channels:
            text = "📋 لیست چنل‌ها خالی است.\n\nبرای افزودن از فرمت زیر در چت تایپ کنید:\n<code>/addchannel @ChannelID</code>"
        else:
            text = "📋 <b>چنل‌های اجباری فعلی:</b>\n" + "\n".join([f"🔸 {ch}" for ch in channels]) + "\n\nبرای حذف:\n<code>/removechannel @ChannelID</code>"
        _bot.reply_to(message, text, reply_markup=_owner_keyboard())

    @_bot.message_handler(commands=["addchannel"])
    def cmd_add_channel(message):
        if message.from_user.id != OWNER_TG_ID: return
        parts = message.text.strip().split()
        if len(parts) < 2: return _bot.reply_to(message, "فرمت: <code>/addchannel @ChannelID</code>")
        if db.add_forced_channel(parts[1]):
            _bot.reply_to(message, f"✅ چنل <b>{parts[1]}</b> اضافه شد.", reply_markup=_owner_keyboard())
        else:
            _bot.reply_to(message, "⚠️ خطا یا تکراری است.", reply_markup=_owner_keyboard())

    @_bot.message_handler(commands=["removechannel"])
    def cmd_remove_channel(message):
        if message.from_user.id != OWNER_TG_ID: return
        parts = message.text.strip().split()
        if len(parts) < 2: return _bot.reply_to(message, "فرمت: <code>/removechannel @ChannelID</code>")
        if db.remove_forced_channel(parts[1]):
            _bot.reply_to(message, f"✅ چنل <b>{parts[1]}</b> حذف شد.", reply_markup=_owner_keyboard())
        else:
            _bot.reply_to(message, "⚠️ چنل در لیست نبود.", reply_markup=_owner_keyboard())

    @_bot.message_handler(commands=["give"])
    def cmd_give(message):
        if message.from_user.id != OWNER_TG_ID: return
        parts = message.text.strip().split()
        if len(parts) < 3: return _bot.reply_to(message, "فرمت: <code>/give username amount</code>")
        target = parts[1].lstrip("@")
        try: amount = int(parts[2])
        except: return _bot.reply_to(message, "❌ مقدار باید عدد باشد.")
        
        account = db.get_account_by_username(target)
        if not account: return _bot.reply_to(message, f"❌ کاربر '{target}' یافت نشد.")
        
        db.add_tokens(account["id"], amount)
        new_balance = db.get_token_balance(account["id"])
        _bot.reply_to(message, f"✅ <b>{amount}</b> توکن به <b>{account['username']}</b> داده شد.\n💰 موجودی جدید: <b>{new_balance}</b>", reply_markup=_owner_keyboard())

    # ─── پیام‌های ناشناخته ──────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: True)
    def cmd_unknown(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account: return
        
        if not require_membership(message): return

        if message.from_user.id == OWNER_TG_ID:
            _bot.reply_to(message, "لطفاً از دکمه‌های زیر استفاده کنید:", reply_markup=_owner_keyboard())
        else:
            _bot.reply_to(message, "لطفاً از دکمه‌های زیر استفاده کنید:", reply_markup=_user_keyboard())

    # ─── حلقه Polling ──────────────────────────────────────────────────────
    def _polling_loop():
        import time as _t
        while True:
            try:
                _bot.infinity_polling(timeout=30, long_polling_timeout=25, restart_on_change=False, skip_pending=True)
            except Exception as e:
                if "409" in str(e):
                    _t.sleep(10)
                    try: _bot.delete_webhook(drop_pending_updates=True)
                    except: pass
                else:
                    _t.sleep(5)

    t = threading.Thread(target=_polling_loop, daemon=True)
    t.start()
    print(f"✅ ربات توکن @{BOT_USERNAME} استارت شد.")


# ─── ساخت کیبوردها ──────────────────────────────────────────────────────────
def _user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 موجودی", "🎁 هدیه روزانه")
    markup.add("🔗 رفرال", "🛒 خرید توکن")
    return markup

def _owner_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 موجودی", "🎁 هدیه روزانه")
    markup.add("🔗 رفرال", "🛒 خرید توکن")
    markup.add("📢 مدیریت چنل‌ها")  # فقط مالک این دکمه را می‌بیند
    return markup
