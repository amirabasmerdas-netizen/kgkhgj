"""
AMEL SELF55 - هسته اصلی ربات
مدیریت تمام کلاینت‌های Telethon برای کاربران نامحدود
"""

import asyncio
import logging
import random
import re
import os
import pytz
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

import database as db
import texts as tx
from config import API_ID, API_HASH, TIMEZONE, SPAM_DELAY, SPAM_MAX, MESSAGE_SLOTS

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)

# ── نگه‌داشتن کلاینت‌های فعال ──────────────────────────────────────────────
# کلید: user_id | مقدار: TelegramClient
active_clients: dict[int, TelegramClient] = {}


def get_now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════════════
#  راه‌اندازی یک کلاینت
# ═══════════════════════════════════════════════════════════════════════════════

async def start_client(user_id: int, session_string: str) -> bool:
    """راه‌اندازی کلاینت Telethon برای کاربر مشخص"""
    try:
        if user_id in active_clients:
            try:
                await active_clients[user_id].disconnect()
            except Exception:
                pass

        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH,
            connection_retries=5,
            auto_reconnect=True,
        )

        await client.connect()

        if not await client.is_user_authorized():
            logger.warning(f"⚠️ کاربر {user_id} مجاز نیست")
            return False

        me = await client.get_me()
        register_handlers(client, me.id)
        active_clients[user_id] = client
        logger.info(f"✅ کلاینت کاربر {user_id} ({me.first_name}) فعال شد")
        return True

    except Exception as e:
        logger.error(f"❌ خطا در راه‌اندازی کلاینت {user_id}: {e}")
        return False


async def stop_client(user_id: int):
    """قطع اتصال یک کلاینت"""
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except Exception:
            pass
        del active_clients[user_id]
        logger.info(f"🔴 کلاینت کاربر {user_id} متوقف شد")


async def start_all_clients():
    """راه‌اندازی کلاینت برای تمام کاربران فعال — بدون محدودیت"""
    users = db.get_all_active_users()
    logger.info(f"🚀 راه‌اندازی {len(users)} کلاینت...")
    tasks = [start_client(u["user_id"], u["session_string"]) for u in users if u["session_string"]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if r is True)
    logger.info(f"✅ {success} از {len(users)} کلاینت با موفقیت راه‌اندازی شدند")


# ═══════════════════════════════════════════════════════════════════════════════
#  هندلرهای اصلی
# ═══════════════════════════════════════════════════════════════════════════════

def register_handlers(client: TelegramClient, owner_id: int):
    """ثبت هندلرها برای یک کلاینت"""

    # ── هلپر: بررسی فعال بودن سلف ─────────────────────────────────────────
    def is_self_on() -> bool:
        s = db.get_settings(owner_id)
        return bool(s.get("self_active", 1))

    # ── هلپر: ارسال پیام و حذف خودکار ─────────────────────────────────────
    async def reply_and_delete(event, text: str, delay: int = 5):
        msg = await event.reply(text)
        await asyncio.sleep(delay)
        try:
            await msg.delete()
            await event.delete()
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    #  دستورات اصلی (فقط از اکانت خود کاربر)
    # ════════════════════════════════════════════════════════════════════════

    @client.on(events.NewMessage(outgoing=True))
    async def command_handler(event):
        if event.sender_id != owner_id:
            return

        cmd = (event.raw_text or "").strip()
        s = db.get_settings(owner_id)

        # ── فعال/غیرفعال سلف ────────────────────────────────────────────
        if cmd == "سلف روشن":
            db.update_setting(owner_id, "self_active", 1)
            await reply_and_delete(event, "✅ سلف بات روشن شد")
            return

        if cmd == "سلف خاموش":
            db.update_setting(owner_id, "self_active", 0)
            await reply_and_delete(event, "🔴 سلف بات خاموش شد")
            return

        # ── بعد از این همه چیز نیاز به سلف روشن دارد ──────────────────
        if not is_self_on():
            return

        # ── منشی ────────────────────────────────────────────────────────
        if cmd == "منشی روشن":
            db.update_setting(owner_id, "secretary_active", 1)
            await reply_and_delete(event, "✅ منشی فعال شد")
        elif cmd == "منشی خاموش":
            db.update_setting(owner_id, "secretary_active", 0)
            await reply_and_delete(event, "🔴 منشی غیرفعال شد")

        # ── ضد حذف ──────────────────────────────────────────────────────
        elif cmd == "ضد حذف روشن":
            db.update_setting(owner_id, "anti_delete", 1)
            await reply_and_delete(event, "✅ ضد حذف فعال شد")
        elif cmd == "ضد حذف خاموش":
            db.update_setting(owner_id, "anti_delete", 0)
            await reply_and_delete(event, "🔴 ضد حذف غیرفعال شد")

        # ── قفل پیوی ────────────────────────────────────────────────────
        elif cmd == "قفل پیوی روشن":
            db.update_setting(owner_id, "pv_lock", 1)
            await reply_and_delete(event, "✅ قفل پیوی فعال شد")
        elif cmd == "قفل پیوی خاموش":
            db.update_setting(owner_id, "pv_lock", 0)
            await reply_and_delete(event, "🔴 قفل پیوی غیرفعال شد")

        # ── ضد لینک ─────────────────────────────────────────────────────
        elif cmd == "ضد لینک روشن":
            db.update_setting(owner_id, "anti_link", 1)
            await reply_and_delete(event, "✅ ضد لینک فعال شد")
        elif cmd == "ضد لینک خاموش":
            db.update_setting(owner_id, "anti_link", 0)
            await reply_and_delete(event, "🔴 ضد لینک غیرفعال شد")

        # ── نمایش لیست دشمن ─────────────────────────────────────────────
        elif cmd == "نمایش لیست دشمن":
            enemies = db.get_enemies(owner_id)
            if not enemies:
                await reply_and_delete(event, "📋 لیست دشمنان خالی است")
            else:
                lines = [f"🔴 لیست دشمنان ({len(enemies)} نفر):"]
                for e in enemies:
                    lines.append(f"• {e['username'] or e['target_id']}")
                await reply_and_delete(event, "\n".join(lines), delay=10)

        # ── نمایش لیست دوست ─────────────────────────────────────────────
        elif cmd == "نمایش لیست دوست":
            friends = db.get_friends(owner_id)
            if not friends:
                await reply_and_delete(event, "📋 لیست دوستان خالی است")
            else:
                lines = [f"🟢 لیست دوستان ({len(friends)} نفر):"]
                for f in friends:
                    lines.append(f"• {f['username'] or f['target_id']}")
                await reply_and_delete(event, "\n".join(lines), delay=10)

        # ── تنظیم دشمن (ریپلای) ─────────────────────────────────────────
        elif cmd == "تنظیم دشمن":
            if event.is_reply:
                replied = await event.get_reply_message()
                uid = replied.sender_id
                uname = (await client.get_entity(uid)).username or str(uid)
                db.add_enemy(owner_id, uid, uname)
                await reply_and_delete(event, f"🔴 @{uname} به لیست دشمنان اضافه شد")
            else:
                await reply_and_delete(event, "⚠️ روی پیام شخص موردنظر ریپلای بزنید")

        # ── حذف دشمن (ریپلای) ──────────────────────────────────────────
        elif cmd == "حذف دشمن":
            if event.is_reply:
                replied = await event.get_reply_message()
                uid = replied.sender_id
                db.remove_enemy(owner_id, uid)
                await reply_and_delete(event, "✅ از لیست دشمنان حذف شد")
            else:
                await reply_and_delete(event, "⚠️ روی پیام شخص موردنظر ریپلای بزنید")

        # ── تنظیم دوست (ریپلای) ─────────────────────────────────────────
        elif cmd == "تنظیم دوست":
            if event.is_reply:
                replied = await event.get_reply_message()
                uid = replied.sender_id
                uname = (await client.get_entity(uid)).username or str(uid)
                db.add_friend(owner_id, uid, uname)
                await reply_and_delete(event, f"🟢 @{uname} به لیست دوستان اضافه شد")
            else:
                await reply_and_delete(event, "⚠️ روی پیام شخص موردنظر ریپلای بزنید")

        # ── حذف دوست (ریپلای) ──────────────────────────────────────────
        elif cmd == "حذف دوست":
            if event.is_reply:
                replied = await event.get_reply_message()
                uid = replied.sender_id
                db.remove_friend(owner_id, uid)
                await reply_and_delete(event, "✅ از لیست دوستان حذف شد")
            else:
                await reply_and_delete(event, "⚠️ روی پیام شخص موردنظر ریپلای بزنید")

        # ── ذخیره پیام در اسلات ─────────────────────────────────────────
        elif re.match(r'^ذخیره (\d+)$', cmd):
            slot = int(re.match(r'^ذخیره (\d+)$', cmd).group(1))
            if 1 <= slot <= MESSAGE_SLOTS:
                if event.is_reply:
                    replied = await event.get_reply_message()
                    db.save_message_slot(owner_id, slot, replied.raw_text or "")
                    await reply_and_delete(event, f"✅ پیام در اسلات {slot} ذخیره شد")
                else:
                    await reply_and_delete(event, "⚠️ روی پیام موردنظر ریپلای بزنید")
            else:
                await reply_and_delete(event, f"⚠️ شماره اسلات باید بین ۱ تا {MESSAGE_SLOTS} باشد")

        # ── ارسال پیام از اسلات ─────────────────────────────────────────
        elif re.match(r'^ارسال (\d+)$', cmd):
            slot = int(re.match(r'^ارسال (\d+)$', cmd).group(1))
            content = db.get_message_slot(owner_id, slot)
            if content:
                await event.delete()
                await client.send_message(event.chat_id, content)
            else:
                await reply_and_delete(event, f"⚠️ اسلات {slot} خالی است")

        # ── اسپم با تأخیر ────────────────────────────────────────────────
        elif re.match(r'^اسپم (\d+) (.+)$', cmd, re.DOTALL):
            m = re.match(r'^اسپم (\d+) (.+)$', cmd, re.DOTALL)
            count = min(int(m.group(1)), SPAM_MAX)
            text = m.group(2)
            await event.delete()
            for i in range(count):
                await client.send_message(event.chat_id, text)
                await asyncio.sleep(SPAM_DELAY)

    # ════════════════════════════════════════════════════════════════════════
    #  پیام‌های ورودی (از دیگران)
    # ════════════════════════════════════════════════════════════════════════

    @client.on(events.NewMessage(incoming=True))
    async def incoming_handler(event):
        if not is_self_on():
            return

        sender_id = event.sender_id
        s = db.get_settings(owner_id)

        # ── دوستان: کاملاً نادیده گرفته می‌شوند ──────────────────────────
        if db.is_friend(owner_id, sender_id):
            return

        # ── دشمنان: پاسخ خودکار از texts.py ─────────────────────────────
        if db.is_enemy(owner_id, sender_id):
            reply_text = random.choice(tx.ENEMY_REPLIES)
            await event.reply(reply_text)
            return

        # ── قفل پیوی ─────────────────────────────────────────────────────
        if s.get("pv_lock") and event.is_private:
            try:
                await client.send_message(sender_id, tx.PV_LOCK_MESSAGE)
                await event.delete()
                # حذف طرف مقابل (revoke)
                await client.delete_messages(event.chat_id, [event.id], revoke=True)
            except Exception:
                pass
            return

        # ── ضد لینک (فقط در پیوی) ────────────────────────────────────────
        if s.get("anti_link") and event.is_private:
            url_pattern = re.compile(
                r'(https?://|t\.me/|@\w+|www\.)\S+', re.IGNORECASE
            )
            if url_pattern.search(event.raw_text or ""):
                try:
                    await event.delete()
                    await event.reply(tx.ANTI_LINK_MESSAGE)
                except Exception:
                    pass
                return

        # ── منشی ─────────────────────────────────────────────────────────
        if s.get("secretary_active") and event.is_private:
            reply_text = random.choice(tx.SECRETARY_REPLIES)
            await event.reply(reply_text)

        # ── خوانده شدن خودکار ────────────────────────────────────────────
        if s.get("auto_seen") and event.is_private:
            try:
                await client.send_read_acknowledge(event.chat_id)
            except Exception:
                pass

    # ════════════════════════════════════════════════════════════════════════
    #  ضد حذف
    # ════════════════════════════════════════════════════════════════════════

    @client.on(events.MessageDeleted)
    async def anti_delete_handler(event):
        if not is_self_on():
            return
        s = db.get_settings(owner_id)
        if not s.get("anti_delete"):
            return
        # این رویداد اطلاعات کافی ندارد، تاریخچه کش‌شده استفاده می‌شود
        pass

    @client.on(events.NewMessage)
    async def cache_messages(event):
        """کش کردن پیام‌ها برای ضد حذف"""
        if not is_self_on():
            return
        s = db.get_settings(owner_id)
        if not s.get("anti_delete"):
            return
        if event.sender_id == owner_id:
            return
        # ذخیره پیام در دیتابیس قبل از حذف احتمالی
        media_path = ""
        if event.media:
            try:
                path = await client.download_media(event.media, file="saved_media/")
                media_path = path or ""
            except Exception:
                pass
        db.save_deleted_message(
            owner_id=owner_id,
            chat_id=event.chat_id,
            sender_id=event.sender_id or 0,
            text=event.raw_text or "",
            media_path=media_path
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  زمان‌بند پیام‌ها
# ═══════════════════════════════════════════════════════════════════════════════

async def run_scheduler():
    """بررسی و ارسال پیام‌های زمان‌بندی‌شده"""
    while True:
        try:
            for user_id, client in list(active_clients.items()):
                pending = db.get_pending_scheduled(user_id)
                for msg in pending:
                    try:
                        await client.send_message(int(msg["chat_id"]), msg["text"])
                        db.mark_scheduled_sent(msg["id"])
                    except Exception as e:
                        logger.error(f"خطا در ارسال پیام زمان‌بندی: {e}")
        except Exception as e:
            logger.error(f"خطا در زمان‌بند: {e}")
        await asyncio.sleep(30)  # هر ۳۰ ثانیه بررسی می‌شود


async def run_all():
    """راه‌اندازی کامل ربات"""
    os.makedirs("saved_media", exist_ok=True)
    db.init_db()
    await start_all_clients()
    await run_scheduler()
