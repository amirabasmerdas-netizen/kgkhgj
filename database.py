import sqlite3
import hashlib
import datetime
from config import DATABASE_PATH

def get_conn():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, telegram_user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    
    # جدول جدید برای چنل‌های اجباری
    c.execute("""CREATE TABLE IF NOT EXISTS forced_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    
    try: c.execute("ALTER TABLE accounts ADD COLUMN telegram_user_id INTEGER")
    except: pass

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        owner_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (owner_id, key))""")
    c.execute("""CREATE TABLE IF NOT EXISTS enemies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        username TEXT, name TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE (owner_id, user_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS friends (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        username TEXT, name TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE (owner_id, user_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS tokens (
        owner_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_daily TEXT DEFAULT NULL, total_earned INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_owner_id INTEGER NOT NULL,
        referred_tg_id INTEGER NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    
    conn.commit()
    conn.close()

# --- توابع مدیریت حساب ---
def create_account(username: str, password: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO accounts (username, password_hash) VALUES (?, ?)", (username.strip(), _hash_pw(password)))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        _init_tokens_by_id(new_id)
        return new_id
    except:
        conn.close()
        return None

def _init_tokens_by_id(owner_id: int):
    from config import WELCOME_TOKENS
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO tokens (owner_id, balance, total_earned) VALUES (?, ?, ?)", (owner_id, WELCOME_TOKENS, WELCOME_TOKENS))
        conn.commit()
    except: pass
    finally: conn.close()

def verify_account(username: str, password: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM accounts WHERE username = ? AND password_hash = ?", (username.strip(), _hash_pw(password)))
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None

def get_account_by_tg_id(tg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username FROM accounts WHERE telegram_user_id = ?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_account_by_username(username: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username FROM accounts WHERE username = ?", (username.strip(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_account(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username FROM accounts WHERE id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_telegram_user_id(owner_id: int, tg_user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE accounts SET telegram_user_id = ? WHERE id = ?", (tg_user_id, owner_id))
    conn.commit()
    conn.close()

def get_telegram_id_by_owner(owner_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_user_id FROM accounts WHERE id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["telegram_user_id"] if row else None

def get_all_accounts():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username FROM accounts ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def account_exists():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM accounts")
    row = c.fetchone()
    conn.close()
    return row["cnt"] > 0

# --- تنظیمات ---
def init_user_settings(owner_id: int):
    conn = get_conn()
    try:
        c = conn.cursor()
        defaults = {"logged_in": "0", "self_bot_active": "0", "secretary_active": "0", "anti_delete_active": "0", "anti_link_active": "0", "auto_seen_active": "0", "auto_reaction_active": "0", "private_lock_active": "0", "enemy_reply_active": "0", "auto_save_media": "0", "clock_name_active": "0", "clock_bio_active": "0", "selected_font": "0", "secretary_message": "در حال حاضر در دسترس نیستم.", "auto_reaction_emoji": "❤️"}
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (owner_id, key, value) VALUES (?, ?, ?)", (owner_id, k, v))
        conn.commit()
    except: pass
    finally: conn.close()
    _init_tokens_by_id(owner_id)

def get_setting(owner_id: int, key: str, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE owner_id = ? AND key = ?", (owner_id, key))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(owner_id: int, key: str, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (owner_id, key, value) VALUES (?, ?, ?)", (owner_id, key, str(value)))
    conn.commit()
    conn.close()

def get_all_logged_in_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT owner_id FROM settings WHERE key = 'logged_in' AND value = '1'")
    rows = [r["owner_id"] for r in c.fetchall()]
    conn.close()
    return rows

# --- سیستم توکن ---
def get_token_balance(owner_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["balance"] if row else 0

def add_tokens(owner_id: int, amount: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ? WHERE owner_id = ?", (amount, amount, owner_id))
    conn.commit()
    conn.close()

def deduct_tokens(owner_id: int, amount: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    if not row or row["balance"] < amount:
        conn.close()
        return False
    c.execute("UPDATE tokens SET balance = balance - ? WHERE owner_id = ?", (amount, owner_id))
    conn.commit()
    conn.close()
    return True

def claim_daily_token(owner_id: int):
    from config import DAILY_TOKEN_GIFT
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT last_daily FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    today = datetime.date.today().isoformat()
    if row and row["last_daily"] == today:
        conn.close()
        return False, "⏰ امروز قبلاً هدیه روزانه دریافت کردید."
    c.execute("UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ?, last_daily = ? WHERE owner_id = ?", (DAILY_TOKEN_GIFT, DAILY_TOKEN_GIFT, today, owner_id))
    conn.commit()
    conn.close()
    return True, f"🎁 {DAILY_TOKEN_GIFT} توکن دریافت کردید!"

def process_referral(referrer_owner_id: int, referred_tg_id: int) -> bool:
    from config import REFERRAL_TOKENS
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT 1 FROM referrals WHERE referred_tg_id = ?", (referred_tg_id,))
        if c.fetchone(): return False
        c.execute("INSERT INTO referrals (referrer_owner_id, referred_tg_id) VALUES (?, ?)", (referrer_owner_id, referred_tg_id))
        c.execute("UPDATE tokens SET balance = balance + ?, total_earned = total_earned + ? WHERE owner_id = ?", (REFERRAL_TOKENS, REFERRAL_TOKENS, referrer_owner_id))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def get_referral_count(owner_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    return row["cnt"] if row else 0

def get_token_stats(owner_id: int) -> dict:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance, last_daily, total_earned FROM tokens WHERE owner_id = ?", (owner_id,))
    row = c.fetchone()
    conn.close()
    if not row: return {"balance": 0, "total_earned": 0}
    return {"balance": row["balance"], "last_daily": row["last_daily"], "total_earned": row["total_earned"]}

# ==========================================
# --- توابع جدید مدیریت چنل‌های اجباری ---
# ==========================================
def get_forced_channels():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT username FROM forced_channels ORDER BY added_at DESC")
    rows = [r["username"] for r in c.fetchall()]
    conn.close()
    return rows

def add_forced_channel(username: str) -> bool:
    if not username.startswith("@"): username = "@" + username
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO forced_channels (username) VALUES (?)", (username,))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def remove_forced_channel(username: str) -> bool:
    if not username.startswith("@"): username = "@" + username
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM forced_channels WHERE username = ?", (username,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def check_user_membership(bot, user_id: int) -> tuple:
    """بررسی می‌کند آیا کاربر در همه چنل‌های اجباری عضو است."""
    channels = get_forced_channels()
    if not channels:
        return True, []
    
    missing = []
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                missing.append(ch)
        except Exception:
            missing.append(ch)
    
    return len(missing) == 0, missing
