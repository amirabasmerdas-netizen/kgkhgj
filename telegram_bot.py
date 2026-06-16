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
            print(f"🧹 Webhook حذف شد (تلاش {attempt+1})")
            _time.sleep(5)
            break
        except Exception as e:
            print(f"⚠️ delete_webhook (تلاش {attempt+1}): {e}")
            _time.sleep(3)

    # ─── تابع کمکی برای نمایش پیام عضویت اجباری ─────────────────────────────
    def send_join_required(message, missing_channels):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in missing_channels:
            ch_clean = ch.lstrip("@")
            markup.add(types.InlineKeyboardButton(
                f"📢 عضویت در {ch}",
                url=f"https://t.me/{ch_clean}"
            ))
        markup.add(types.InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_join"))
        
        channels_list = "\n".join([f"• {ch}" for ch in missing_channels])
        _bot.reply_to(
            message,
            "⚠️ <b>برای استفاده از ربات باید در چنل‌های زیر عضو شوید:</b>\n\n"
            f"{channels_list}\n\n"
            "👇 روی هر چنل کلیک کنید و Join بزنید، سپس دکمه «بررسی عضویت» را بزنید:",
            reply_markup=markup
        )

    # ─── /start ─────────────────────────────────────────────────────────────
    @_bot.message_handler(commands=["start"])
    def cmd_start(message):
        tg_id = message.from_user.id
        parts = message.text.strip().split()
        ref_code = parts[1] if len(parts) > 1 else None

        # پردازش رفرال (قبل از هر چیزی)
        if ref_code and ref_code.startswith("ref_"):
            try:
                referrer_id = int(ref_code[4:])
                if db.process_referral(referrer_id, tg_id):
                    referrer_tg = db.get_telegram_id_by_owner(referrer_id)
                    if referrer_tg:
                        try:
                            _bot.send_message(
                                referrer_tg,
                                f"🎉 یک نفر با لینک رفرال شما عضو شد!\n"
                                f"<b>+{config.REFERRAL_TOKENS} توکن</b> دریافت کردید 🪙",
                            )
                        except Exception:
                            pass
            except (ValueError, Exception):
                pass

        # ─── بررسی عضویت اجباری (اولین قدم) ───────────────────────────────
        is_member, missing = db.check_user_membership(_bot, tg_id)
        if not is_member:
            send_join_required(message, missing)
            return

        site_url = getattr(config, "SITE_URL", "")
        account = db.get_account_by_tg_id(tg_id)

        if not account:
            markup = types.InlineKeyboardMarkup()
            if site_url:
                markup.add(types.InlineKeyboardButton("🌐 ورود به پنل AMEL SELF55", url=site_url))
            _bot.reply_to(
                message,
                "👋 <b>سلام!</b>\n\n"
                "برای استفاده از ربات توکن:\n"
                "1️⃣ در پنل <b>AMEL SELF55</b> ثبت‌نام کنید\n"
                "2️⃣ حساب تلگرام خود را وصل کنید\n"
                "3️⃣ دوباره /start بزنید\n\n"
                "📌 هر ۲ توکن = ۲ ساعت سلف‌بات روشن",
                reply_markup=markup if site_url else None,
            )
            return

        stats = db.get_token_stats(account["id"])
        
        # انتخاب کیبورد بر اساس اینکه کاربر مالک است یا نه
        if tg_id == OWNER_TG_ID:
            markup = _owner_keyboard()
        else:
            markup = _main_keyboard()
            
        site_markup = types.InlineKeyboardMarkup()
        if site_url:
            site_markup.add(types.InlineKeyboardButton("🌐 باز کردن پنل مدیریت", url=site_url))

        _bot.reply_to(
            message,
            f"👋 سلام <b>{account['username']}</b>!\n\n"
            f"🪙 موجودی: <b>{stats['balance']}</b> توکن\n"
            f"📊 کل دریافتی: <b>{stats['total_earned']}</b> توکن\n\n"
            f"⚡ هر <b>۲ توکن</b> = <b>۲ ساعت</b> سلف‌بات روشن",
            reply_markup=markup,
        )
        if site_url:
            _bot.send_message(message.chat.id, "🔗 از دکمه زیر به پنل دسترسی داشته باشید:", reply_markup=site_markup)

    # ─── هندلر بررسی عضویت (دکمه اینلاین) ────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data == "check_join")
    def callback_check_join(call):
        is_member, missing = db.check_user_membership(_bot, call.from_user.id)
        if is_member:
            _bot.answer_callback_query(call.id, "عضویت شما تأیید شد! ✅")
            try:
                _bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            cmd_start(call.message)
        else:
            _bot.answer_callback_query(
                call.id,
                f"هنوز در {len(missing)} چنل عضو نشده‌اید! ❌",
                show_alert=True
            )

    # ─── موجودی ─────────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("💰 موجودی", "/balance"))
    @_bot.message_handler(commands=["balance"])
    def cmd_balance(message):
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_join_required(message, missing)
            return

        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد. ابتدا در پنل وصل شوید.")
            return
        stats = db.get_token_stats(account["id"])
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(
            message,
            f"🪙 <b>موجودی توکن</b>\n\n"
            f"💰 موجودی فعلی: <b>{stats['balance']}</b>\n"
            f"📊 کل دریافتی: <b>{stats['total_earned']}</b>\n"
            f"👥 رفرال‌ها: <b>{ref_count}</b> نفر\n\n"
            f"⚡ هر ۲ توکن = ۲ ساعت سلف روشن",
        )

    # ─── هدیه روزانه ────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🎁 هدیه روزانه", "/daily"))
    @_bot.message_handler(commands=["daily"])
    def cmd_daily(message):
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_join_required(message, missing)
            return

        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد.")
            return
        success, msg = db.claim_daily_token(account["id"])
        if success:
            stats = db.get_token_stats(account["id"])
            _bot.reply_to(message, f"{msg}\n\n💰 موجودی جدید: <b>{stats['balance']}</b> توکن")
        else:
            _bot.reply_to(message, msg)

    # ─── رفرال ──────────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🔗 رفرال", "/referral"))
    @_bot.message_handler(commands=["referral"])
    def cmd_referral(message):
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_join_required(message, missing)
            return

        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            _bot.reply_to(message, "⚠️ حساب پیدا نشد.")
            return
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{account['id']}"
        ref_count = db.get_referral_count(account["id"])
        _bot.reply_to(
            message,
            f"🔗 <b>لینک رفرال شما:</b>\n"
            f"<code>{link}</code>\n\n"
            f"👥 تعداد رفرال‌ها: <b>{ref_count}</b> نفر\n"
            f"🎁 هر رفرال = <b>{config.REFERRAL_TOKENS}</b> توکن\n\n"
            f"لینک را کپی کرده و برای دوستانتان بفرستید!",
        )

    # ─── خرید توکن ──────────────────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text in ("🛒 خرید توکن", "/buy"))
    @_bot.message_handler(commands=["buy"])
    def cmd_buy(message):
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_join_required(message, missing)
            return

        account = db.get_account_by_tg_id(message.from_user.id)
        username_txt = account["username"] if account else str(message.from_user.id)

        markup = types.InlineKeyboardMarkup()
        if config.OWNER_USERNAME:
            markup.add(
                types.InlineKeyboardButton("📩 پیوی مالک", url=f"https://t.me/{config.OWNER_USERNAME}")
            )

        _bot.reply_to(
            message,
            f"🛒 <b>خرید توکن</b>\n\n"
            f"برای خرید توکن به مالک پیام بدید.\n"
            f"👤 یوزرنیم پنل شما: <b>{username_txt}</b>\n\n"
            f"💰 قیمت‌ها توسط مالک تعیین می‌شود.",
            reply_markup=markup if config.OWNER_USERNAME else None,
        )

    # ─── 🆕 دستور /addchannel (فقط مالک) ──────────────────────────────────
    @_bot.message_handler(commands=["addchannel"])
    def cmd_add_channel(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        parts = message.text.strip().split()
        if len(parts) < 2:
            _bot.reply_to(
                message,
                "📝 <b>فرمت:</b>\n"
                "<code>/addchannel @ChannelUsername</code>\n\n"
                "مثال: <code>/addchannel @MyChannel</code>"
            )
            return
        channel = parts[1]
        if db.add_forced_channel(channel):
            _bot.reply_to(message, f"✅ چنل <b>{channel}</b> به لیست عضویت اجباری اضافه شد.")
        else:
            _bot.reply_to(message, f"⚠️ چنل <b>{channel}</b> از قبل در لیست وجود دارد یا خطا رخ داد.")

    # ─── 🆕 دستور /removechannel (فقط مالک) ───────────────────────────────
    @_bot.message_handler(commands=["removechannel"])
    def cmd_remove_channel(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        parts = message.text.strip().split()
        if len(parts) < 2:
            _bot.reply_to(
                message,
                "📝 <b>فرمت:</b>\n"
                "<code>/removechannel @ChannelUsername</code>\n\n"
                "مثال: <code>/removechannel @MyChannel</code>"
            )
            return
        channel = parts[1]
        if db.remove_forced_channel(channel):
            _bot.reply_to(message, f"✅ چنل <b>{channel}</b> از لیست عضویت اجباری حذف شد.")
        else:
            _bot.reply_to(message, f"⚠️ چنل <b>{channel}</b> در لیست نبود.")

    # ─── 🆕 دستور /channels (فقط مالک - نمایش لیست چنل‌های اجباری) ────────
    @_bot.message_handler(func=lambda m: m.text in ("📢 چنل‌های اجباری", "/channels"))
    @_bot.message_handler(commands=["channels"])
    def cmd_list_channels(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        channels = db.get_forced_channels()
        if not channels:
            _bot.reply_to(
                message,
                "📋 <b>لیست چنل‌های اجباری خالی است.</b>\n\n"
                "برای افزودن چنل جدید از دستور زیر استفاده کنید:\n"
                "<code>/addchannel @ChannelUsername</code>"
            )
            return
        lines = ["📋 <b>چنل‌های عضویت اجباری:</b>\n"]
        for i, ch in enumerate(channels, 1):
            lines.append(f"{i}. <code>{ch}</code>")
        lines.append("\nبرای حذف هر چنل:")
        lines.append("<code>/removechannel @ChannelUsername</code>")
        _bot.reply_to(message, "\n".join(lines))

    # ─── دستور /give (فقط مالک) ─────────────────────────────────────────────
    @_bot.message_handler(commands=["give"])
    def cmd_give(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        parts = message.text.strip().split()
        if len(parts) < 3:
            _bot.reply_to(message, "📝 فرمت: /give [آیدی یا یوزرنیم پنل] [مقدار]\nمثال: /give 5 100")
            return
        target = parts[1].lstrip("@")
        try:
            amount = int(parts[2])
        except ValueError:
            _bot.reply_to(message, "❌ مقدار باید عدد باشد.")
            return
        if amount <= 0:
            _bot.reply_to(message, "❌ مقدار باید بزرگ‌تر از صفر باشد.")
            return

        account = None
        if target.isdigit():
            account = db.get_account(int(target))
        if not account:
            account = db.get_account_by_username(target)

        if not account:
            _bot.reply_to(message, f"❌ کاربر '{target}' پیدا نشد.")
            return

        db.add_tokens(account["id"], amount)
        new_balance = db.get_token_balance(account["id"])
        _bot.reply_to(
            message,
            f"✅ <b>{amount}</b> توکن به <b>{account['username']}</b> داده شد.\n"
            f"💰 موجودی جدید: <b>{new_balance}</b>",
        )
        tg_id = db.get_telegram_id_by_owner(account["id"])
        if tg_id:
            try:
                _bot.send_message(
                    tg_id,
                    f"🎁 <b>{amount}</b> توکن از طرف مالک دریافت کردید!\n"
                    f"💰 موجودی جدید: <b>{new_balance}</b> توکن",
                )
            except Exception:
                pass

    # ─── دستور /users (فقط مالک - لیست کاربران) ────────────────────────────
    @_bot.message_handler(commands=["users"])
    def cmd_users(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        accounts = db.get_all_accounts()
        if not accounts:
            _bot.reply_to(message, "هیچ کاربری ثبت نشده.")
            return
        lines = [f"👥 <b>کاربران ({len(accounts)} نفر):</b>\n"]
        for acc in accounts[:20]:
            bal = db.get_token_balance(acc["id"])
            lines.append(f"• <b>{acc['username']}</b> — ID:{acc['id']} — 🪙{bal}")
        _bot.reply_to(message, "\n".join(lines))

    # ─── پیام‌های متنی ناشناخته ──────────────────────────────────────────────
    @_bot.message_handler(func=lambda m: True)
    def cmd_unknown(message):
        account = db.get_account_by_tg_id(message.from_user.id)
        if not account:
            return
        
        is_member, missing = db.check_user_membership(_bot, message.from_user.id)
        if not is_member:
            send_join_required(message, missing)
            return

        # انتخاب کیبورد بر اساس مالک بودن
        if message.from_user.id == OWNER_TG_ID:
            markup = _owner_keyboard()
        else:
            markup = _main_keyboard()
        _bot.reply_to(message, "از دکمه‌های زیر استفاده کنید:", reply_markup=markup)

    def _polling_loop():
        import time as _t
        while True:
            try:
                _bot.infinity_polling(
                    timeout=30,
                    long_polling_timeout=25,
                    restart_on_change=False,
                    skip_pending=True,
                )
            except Exception as e:
                err_str = str(e)
                if "409" in err_str or "Conflict" in err_str:
                    print("⚠️ تعارض polling (409) — ۱۰ ثانیه صبر...")
                    _t.sleep(10)
                    try:
                        _bot.delete_webhook(drop_pending_updates=True)
                        _t.sleep(2)
                    except Exception:
                        pass
                else:
                    print(f"⚠️ خطای polling: {e} — ۵ ثانیه صبر...")
                    _t.sleep(5)

    t = threading.Thread(target=_polling_loop, daemon=True)
    t.start()
    print(f"✅ ربات توکن @{BOT_USERNAME} استارت شد.")


# ─── کیبوردها ──────────────────────────────────────────────────────────────────
def _main_keyboard():
    """کیبورد مخصوص کاربران عادی"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 موجودی", "🎁 هدیه روزانه")
    markup.add("🔗 رفرال", "🛒 خرید توکن")
    return markup


def _owner_keyboard():
    """کیبورد مخصوص مالک (با دکمه مدیریت چنل‌های اجباری)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 موجودی", "🎁 هدیه روزانه")
    markup.add("🔗 رفرال", "🛒 خرید توکن")
    markup.add("📢 چنل‌های اجباری")
    return markup
