"""
AMEL SELF55 - ربات
هسته اصلی سلف‌بات تلگرام با استفاده از Telethon
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pytz
from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument,
    User, PeerUser
)
from telethon.errors import FloodWaitError

import database as db
from config import (
    API_ID, API_HASH, SESSION_NAME, TIMEZONE,
    SPAM_DELAY, MAX_MESSAGE_SLOTS, BOT_NAME
)
from texts import get_enemy_reply, SECRETARY_DEFAULT, SYSTEM_MSGS, get_random_reaction

# ── لاگ‌گذاری ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

tz = pytz.timezone(TIMEZONE)

# ── کلاینت تلگرام ─────────────────────────────────────────────────────────────
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ── متغیرهای حالت ─────────────────────────────────────────────────────────────
spam_running: bool = False
_me = None  # اطلاعات اکانت ما


# ════════════════════════════════════════════════════════════════════════════════
#  توابع کمکی
# ════════════════════════════════════════════════════════════════════════════════

def now_str() -> str:
    """زمان فعلی به فرمت فارسی"""
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


def is_self_active() -> bool:
    return db.get_setting("self_active", "true") == "true"


def is_secretary_active() -> bool:
    return db.get_setting("secretary_active", "false") == "true"


def is_anti_delete_active() -> bool:
    return db.get_setting("anti_delete_active", "false") == "true"


def is_pv_lock_active() -> bool:
    return db.get_setting("pv_lock_active", "false") == "true"


def is_anti_link_active() -> bool:
    return db.get_setting("anti_link_active", "false") == "true"


def is_auto_seen_active() -> bool:
    return db.get_setting("auto_seen_active", "false") == "true"


def is_auto_reaction_active() -> bool:
    return db.get_setting("auto_reaction_active", "false") == "true"


def contains_link(text: str) -> bool:
    """بررسی وجود لینک در متن"""
    pattern = r"(https?://|t\.me/|@\w+|www\.)\S+"
    return bool(re.search(pattern, text or ""))


async def get_me():
    global _me
    if _me is None:
        _me = await client.get_me()
    return _me


async def get_reply_sender(event):
    """دریافت اطلاعات فرستنده پیام ریپلای‌شده"""
    if not event.reply_to_msg_id:
        return None
    try:
        replied = await event.get_reply_message()
        if replied and replied.sender_id:
            sender = await client.get_entity(replied.sender_id)
            return sender
    except Exception as e:
        logger.warning(f"خطا در دریافت فرستنده: {e}")
    return None


async def save_media(message) -> str:
    """ذخیره مدیا از پیام و بازگشت مسیر فایل"""
    if not message.media:
        return ""
    try:
        media_dir = Path("saved_media")
        media_dir.mkdir(exist_ok=True)
        path = await client.download_media(message, file=str(media_dir))
        return str(path) if path else ""
    except Exception as e:
        logger.warning(f"خطا در ذخیره مدیا: {e}")
        return ""


async def send_temp(event, text: str, delay: int = 5):
    """ارسال پیام موقت که بعد از چند ثانیه حذف می‌شود"""
    try:
        msg = await event.reply(text)
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════════
#  دیکشنری پیام‌های ورودی برای ضد حذف (قبل از حذف ذخیره می‌کنیم)
# ════════════════════════════════════════════════════════════════════════════════
_message_cache: dict[int, dict] = {}  # message_id -> {chat_id, sender_id, name, text, media}


# ════════════════════════════════════════════════════════════════════════════════
#  هندلرها
# ════════════════════════════════════════════════════════════════════════════════

@client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    """هندلر اصلی دستورات — فقط پیام‌های خودِ کاربر"""
    global spam_running

    text = event.raw_text.strip()
    me = await get_me()

    # ── بررسی فعال بودن سلف (فقط دستور روشن کردن استثناء است) ───────────────
    if text != "سلف روشن" and not is_self_active():
        return

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات کنترل سلف
    # ════════════════════════════════════════════════════════════════════════

    if text == "سلف روشن":
        db.set_setting("self_active", "true")
        await send_temp(event, f"✅ {BOT_NAME} روشن شد!\n🕐 {now_str()}")

    elif text == "سلف خاموش":
        db.set_setting("self_active", "false")
        await send_temp(event, f"🔴 {BOT_NAME} خاموش شد.\n🕐 {now_str()}")

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات منشی
    # ════════════════════════════════════════════════════════════════════════

    elif text == "منشی روشن":
        db.set_setting("secretary_active", "true")
        await send_temp(event, SYSTEM_MSGS["secretary_on"])

    elif text == "منشی خاموش":
        db.set_setting("secretary_active", "false")
        await send_temp(event, SYSTEM_MSGS["secretary_off"])

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات ضد حذف
    # ════════════════════════════════════════════════════════════════════════

    elif text == "ضد حذف روشن":
        db.set_setting("anti_delete_active", "true")
        await send_temp(event, SYSTEM_MSGS["anti_delete_on"])

    elif text == "ضد حذف خاموش":
        db.set_setting("anti_delete_active", "false")
        await send_temp(event, SYSTEM_MSGS["anti_delete_off"])

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات قفل پیوی
    # ════════════════════════════════════════════════════════════════════════

    elif text == "قفل پیوی روشن":
        db.set_setting("pv_lock_active", "true")
        await send_temp(event, SYSTEM_MSGS["pv_lock_on"])

    elif text == "قفل پیوی خاموش":
        db.set_setting("pv_lock_active", "false")
        await send_temp(event, SYSTEM_MSGS["pv_lock_off"])

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات ضد لینک
    # ════════════════════════════════════════════════════════════════════════

    elif text == "ضد لینک روشن":
        db.set_setting("anti_link_active", "true")
        await send_temp(event, SYSTEM_MSGS["anti_link_on"])

    elif text == "ضد لینک خاموش":
        db.set_setting("anti_link_active", "false")
        await send_temp(event, SYSTEM_MSGS["anti_link_off"])

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات دوست
    # ════════════════════════════════════════════════════════════════════════

    elif text == "تنظیم دوست":
        sender = await get_reply_sender(event)
        if not sender:
            await send_temp(event, SYSTEM_MSGS["not_found"])
            return
        name = getattr(sender, "first_name", "") or ""
        username = getattr(sender, "username", "") or ""
        db.add_friend(sender.id, username, name)
        await send_temp(event, f"{SYSTEM_MSGS['friend_added']}\n👤 {name} (@{username})")

    elif text == "حذف دوست":
        sender = await get_reply_sender(event)
        if not sender:
            await send_temp(event, SYSTEM_MSGS["not_found"])
            return
        db.remove_friend(sender.id)
        name = getattr(sender, "first_name", "") or str(sender.id)
        await send_temp(event, f"{SYSTEM_MSGS['friend_removed']}\n👤 {name}")

    elif text == "نمایش لیست دوست":
        friends = db.get_all_friends()
        if not friends:
            await send_temp(event, "📋 لیست دوستان خالی است.", delay=8)
            return
        lines = [f"💚 لیست دوستان ({len(friends)} نفر):\n"]
        for i, f in enumerate(friends, 1):
            uname = f"@{f['username']}" if f["username"] else "—"
            lines.append(f"{i}. {f['name']} | {uname} | آی‌دی: {f['user_id']}")
        await send_temp(event, "\n".join(lines), delay=15)

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات دشمن
    # ════════════════════════════════════════════════════════════════════════

    elif text == "تنظیم دشمن":
        sender = await get_reply_sender(event)
        if not sender:
            await send_temp(event, SYSTEM_MSGS["not_found"])
            return
        name = getattr(sender, "first_name", "") or ""
        username = getattr(sender, "username", "") or ""
        db.add_enemy(sender.id, username, name)
        await send_temp(event, f"{SYSTEM_MSGS['enemy_added']}\n👤 {name} (@{username})")

    elif text == "حذف دشمن":
        sender = await get_reply_sender(event)
        if not sender:
            await send_temp(event, SYSTEM_MSGS["not_found"])
            return
        db.remove_enemy(sender.id)
        name = getattr(sender, "first_name", "") or str(sender.id)
        await send_temp(event, f"{SYSTEM_MSGS['enemy_removed']}\n👤 {name}")

    elif text == "نمایش لیست دشمن":
        enemies = db.get_all_enemies()
        if not enemies:
            await send_temp(event, "📋 لیست دشمنان خالی است.", delay=8)
            return
        lines = [f"🔴 لیست دشمنان ({len(enemies)} نفر):\n"]
        for i, e in enumerate(enemies, 1):
            uname = f"@{e['username']}" if e["username"] else "—"
            lines.append(f"{i}. {e['name']} | {uname} | آی‌دی: {e['user_id']}")
        await send_temp(event, "\n".join(lines), delay=15)

    # ════════════════════════════════════════════════════════════════════════
    #  ذخیره پیام در اسلات: ذخیره N (روی پیام ریپلای کن)
    # ════════════════════════════════════════════════════════════════════════

    elif text.startswith("ذخیره "):
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            slot = int(parts[1])
            if 1 <= slot <= MAX_MESSAGE_SLOTS:
                if event.reply_to_msg_id:
                    replied = await event.get_reply_message()
                    content = replied.raw_text if replied else ""
                    db.save_message_slot(slot, content)
                    await send_temp(event, f"{SYSTEM_MSGS['slot_saved']} (اسلات {slot})")
                else:
                    await send_temp(event, "❌ روی پیامی که می‌خوای ذخیره کنی ریپلای کن.")

    elif text.startswith("ارسال "):
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            slot = int(parts[1])
            content = db.get_message_slot(slot)
            if content:
                await event.delete()
                await client.send_message(event.chat_id, content)
            else:
                await send_temp(event, SYSTEM_MSGS["slot_empty"])

    # ════════════════════════════════════════════════════════════════════════
    #  اسپم: اسپم N متن
    # ════════════════════════════════════════════════════════════════════════

    elif text.startswith("اسپم "):
        parts = text.split(" ", 2)
        if len(parts) >= 3:
            try:
                count = int(parts[1])
                msg_text = parts[2]
                spam_running = True
                await event.delete()
                for i in range(count):
                    if not spam_running:
                        break
                    await client.send_message(event.chat_id, msg_text)
                    await asyncio.sleep(SPAM_DELAY)
            except ValueError:
                await send_temp(event, "❌ فرمت درست: اسپم [تعداد] [متن]")

    elif text == "توقف اسپم":
        spam_running = False
        await send_temp(event, SYSTEM_MSGS["spam_stopped"])

    # ════════════════════════════════════════════════════════════════════════
    #  وضعیت سیستم
    # ════════════════════════════════════════════════════════════════════════

    elif text == "وضعیت":
        settings = db.get_all_settings()
        status_icon = lambda s: "✅" if s == "true" else "🔴"
        status_text = (
            f"📊 وضعیت {BOT_NAME}\n"
            f"🕐 {now_str()}\n\n"
            f"{status_icon(settings.get('self_active','false'))} سلف‌بات\n"
            f"{status_icon(settings.get('secretary_active','false'))} منشی\n"
            f"{status_icon(settings.get('anti_delete_active','false'))} ضد حذف\n"
            f"{status_icon(settings.get('pv_lock_active','false'))} قفل پیوی\n"
            f"{status_icon(settings.get('anti_link_active','false'))} ضد لینک\n"
            f"{status_icon(settings.get('auto_seen_active','false'))} دیدن خودکار\n"
            f"{status_icon(settings.get('auto_reaction_active','false'))} واکنش خودکار\n\n"
            f"👥 دوستان: {len(db.get_all_friends())} نفر\n"
            f"⚔️ دشمنان: {len(db.get_all_enemies())} نفر"
        )
        await send_temp(event, status_text, delay=20)

    # ════════════════════════════════════════════════════════════════════════
    #  مشاهده آخرین حذف‌شده‌ها
    # ════════════════════════════════════════════════════════════════════════

    elif text == "حذف‌شده‌ها":
        deleted = db.get_recent_deleted(event.chat_id, limit=5)
        if not deleted:
            await send_temp(event, "🗑️ پیام حذف‌شده‌ای یافت نشد.")
            return
        lines = ["🗑️ آخرین پیام‌های حذف‌شده:\n"]
        for d in deleted:
            lines.append(
                f"👤 {d['sender_name']} | 🕐 {d['deleted_at']}\n"
                f"💬 {d['text'][:100] or '[مدیا]'}\n"
            )
        await send_temp(event, "\n".join(lines), delay=20)

    # ════════════════════════════════════════════════════════════════════════
    #  دیدن خودکار
    # ════════════════════════════════════════════════════════════════════════

    elif text == "دیدن خودکار روشن":
        db.set_setting("auto_seen_active", "true")
        await send_temp(event, "✅ دیدن خودکار فعال شد.")

    elif text == "دیدن خودکار خاموش":
        db.set_setting("auto_seen_active", "false")
        await send_temp(event, "🔴 دیدن خودکار غیرفعال شد.")

    # ════════════════════════════════════════════════════════════════════════
    #  واکنش خودکار
    # ════════════════════════════════════════════════════════════════════════

    elif text == "واکنش خودکار روشن":
        db.set_setting("auto_reaction_active", "true")
        await send_temp(event, "✅ واکنش خودکار فعال شد.")

    elif text == "واکنش خودکار خاموش":
        db.set_setting("auto_reaction_active", "false")
        await send_temp(event, "🔴 واکنش خودکار غیرفعال شد.")

    # ════════════════════════════════════════════════════════════════════════
    #  راهنما
    # ════════════════════════════════════════════════════════════════════════

    elif text == "راهنما":
        help_text = (
            f"📖 راهنمای {BOT_NAME}\n\n"
            "🔵 کنترل سلف:\n"
            "سلف روشن / سلف خاموش\n\n"
            "👥 دوستان و دشمنان:\n"
            "تنظیم دوست / حذف دوست\n"
            "تنظیم دشمن / حذف دشمن\n"
            "نمایش لیست دوست / نمایش لیست دشمن\n\n"
            "🤖 اتوماسیون:\n"
            "منشی روشن / خاموش\n"
            "ضد حذف روشن / خاموش\n"
            "قفل پیوی روشن / خاموش\n"
            "ضد لینک روشن / خاموش\n"
            "دیدن خودکار روشن / خاموش\n"
            "واکنش خودکار روشن / خاموش\n\n"
            "💾 مدیریت پیام:\n"
            "ذخیره [1-10] (روی پیام ریپلای)\n"
            "ارسال [1-10]\n\n"
            "🚀 اسپم:\n"
            "اسپم [تعداد] [متن]\n"
            "توقف اسپم\n\n"
            "📊 وضعیت / حذف‌شده‌ها / راهنما"
        )
        await send_temp(event, help_text, delay=30)


# ════════════════════════════════════════════════════════════════════════════════
#  هندلر پیام‌های دریافتی (از دیگران)
# ════════════════════════════════════════════════════════════════════════════════

@client.on(events.NewMessage(incoming=True))
async def incoming_handler(event):
    """هندلر پیام‌های ورودی"""
    if not is_self_active():
        return

    me = await get_me()
    sender_id = event.sender_id
    if sender_id is None or sender_id == me.id:
        return

    # ── کش پیام برای ضد حذف ──────────────────────────────────────────────────
    if is_anti_delete_active():
        try:
            sender = await event.get_sender()
            sender_name = getattr(sender, "first_name", "") or str(sender_id)
            media_path = await save_media(event.message) if event.message.media else ""
            _message_cache[event.message.id] = {
                "chat_id": event.chat_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "text": event.raw_text or "",
                "media_path": media_path,
            }
        except Exception as e:
            logger.warning(f"خطا در کش پیام: {e}")

    # ── دیدن خودکار ───────────────────────────────────────────────────────────
    if is_auto_seen_active():
        try:
            await client.send_read_acknowledge(event.chat_id, event.message)
        except Exception:
            pass

    # ── بررسی دوست (همه چیز رد می‌شه) ───────────────────────────────────────
    if db.is_friend(sender_id):
        return

    is_private = isinstance(event.peer_id, PeerUser)

    # ── واکنش خودکار ──────────────────────────────────────────────────────────
    if is_auto_reaction_active() and is_private:
        try:
            reaction = db.get_setting("default_reaction", "👍")
            await client(
                __import__("telethon.tl.functions.messages", fromlist=["SendReactionRequest"])
                .SendReactionRequest(
                    peer=event.chat_id,
                    msg_id=event.message.id,
                    reaction=[__import__("telethon.tl.types", fromlist=["ReactionEmoji"])
                               .ReactionEmoji(emoticon=reaction)]
                )
            )
        except Exception:
            pass

    # ── ضد لینک (فقط در پیوی) ─────────────────────────────────────────────────
    if is_anti_link_active() and is_private:
        if contains_link(event.raw_text):
            try:
                await event.delete()
                notify = await client.send_message(
                    event.chat_id,
                    "🚫 ارسال لینک در این چت مجاز نیست."
                )
                await asyncio.sleep(5)
                await notify.delete()
            except Exception as e:
                logger.warning(f"خطا در ضد لینک: {e}")
            return

    # ── پاسخ به دشمن ──────────────────────────────────────────────────────────
    if db.is_enemy(sender_id):
        try:
            reply_text = get_enemy_reply()
            await event.reply(reply_text)
        except FloodWaitError as e:
            logger.warning(f"FloodWait: {e.seconds} ثانیه")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.warning(f"خطا در پاسخ به دشمن: {e}")
        return

    # ── قفل پیوی ──────────────────────────────────────────────────────────────
    if is_pv_lock_active() and is_private:
        try:
            await event.delete()
        except Exception:
            pass
        return

    # ── منشی ──────────────────────────────────────────────────────────────────
    if is_secretary_active() and is_private:
        try:
            sec_msg = db.get_setting("secretary_message", SECRETARY_DEFAULT)
            await event.reply(sec_msg)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.warning(f"خطا در منشی: {e}")


# ════════════════════════════════════════════════════════════════════════════════
#  هندلر حذف پیام (ضد حذف)
# ════════════════════════════════════════════════════════════════════════════════

@client.on(events.MessageDeleted())
async def deleted_handler(event):
    """ضد حذف — ذخیره پیام‌های حذف‌شده"""
    if not is_self_active() or not is_anti_delete_active():
        return

    for msg_id in event.deleted_ids:
        cached = _message_cache.pop(msg_id, None)
        if cached:
            db.save_deleted_message(
                chat_id=cached["chat_id"],
                message_id=msg_id,
                sender_id=cached["sender_id"],
                sender_name=cached["sender_name"],
                text=cached["text"],
                media_path=cached.get("media_path", ""),
            )


# ════════════════════════════════════════════════════════════════════════════════
#  راه‌اندازی
# ════════════════════════════════════════════════════════════════════════════════

async def start_bot():
    """شروع ربات"""
    db.init_db()
    logger.info(f"🚀 {BOT_NAME} در حال راه‌اندازی...")

    if not API_ID or not API_HASH:
        logger.error("❌ API_ID یا API_HASH تنظیم نشده است!")
        return

    await client.start(phone=lambda: input("📱 شماره تلفن: "))
    me = await client.get_me()
    logger.info(f"✅ وارد شد: {me.first_name} | @{me.username or 'بدون یوزرنیم'}")
    logger.info(f"🤖 {BOT_NAME} فعال شد!")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(start_bot())
