import asyncio, random, sqlite3, os, time, contextlib, string
from html import escape
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest

# ═══════════════════════════════════════════════════════════
BOT_TOKEN = "9088817673:AAF2gxq4eaty63NNiYtfU85n9AxdBtOrPiU"   # 👈 токен от @BotFather
ADMIN_ID = 8907438590            # 👈 твой Telegram ID

START_BONUS = 15
BONUS_MIN, BONUS_MAX = 5, 50
REF_REWARD = 10
NEWBIE_ACTIVATION = 20

PASS_SEASON_DAYS = 30
PASS_TIERS = 100
PASS_GOLDEN_CHANCE = 0.07
PASS_GOLDEN_VALUE = 5

CAP_HOURS = 12
GIFT_CAP_HOURS = 12
MAX_BIZ_LEVEL = 10
BONUS_COOLDOWN = 12 * 60 * 60
TOKEN_RATE = 3
GIFT_SELL_PART = 0.7
UP_MIN, UP_MAX = 1, 1000
ONLINE_WINDOW = 300
PLAY_WINDOW = 900
LOG_KEEP = 500
# ═══════════════════════════════════════════════════════════

if BOT_TOKEN == "ВСТАВЬ_ТОКЕН" or ":" not in BOT_TOKEN:
    raise SystemExit("\n❌ Вставь токен в строку BOT_TOKEN наверху файла.\n")

DB_PATH = "bot.db"
BOT_USERNAME = ""
ADMINS = {ADMIN_ID}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class St(StatesGroup):
    playing_ice = State()

def esc(s): return escape(str(s)) if s else ""

app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

@contextlib.contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            coins INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0,
            last_daily REAL DEFAULT 0, referrer_id INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
            gift_bank REAL DEFAULT 0, welcome INTEGER DEFAULT 0,
            free_cases INTEGER DEFAULT 0, boost_until REAL DEFAULT 0, boost_mult REAL DEFAULT 1,
            last_seen REAL DEFAULT 0, created_at REAL DEFAULT 0,
            blocked INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
            ref_paid INTEGER DEFAULT 0, activated INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS business (
            user_id INTEGER, biz_id INTEGER, level INTEGER DEFAULT 0,
            last_collect REAL DEFAULT 0, PRIMARY KEY (user_id, biz_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS gifts (
            user_id INTEGER, gift_id INTEGER, qty INTEGER DEFAULT 0,
            last_collect REAL DEFAULT 0, PRIMARY KEY (user_id, gift_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS pass (
            user_id INTEGER PRIMARY KEY, tokens INTEGER DEFAULT 0,
            golden INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pass_daily (
            user_id INTEGER, day INTEGER, action TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, day, action))''')
        c.execute('''CREATE TABLE IF NOT EXISTS pass_season (
            id INTEGER PRIMARY KEY, season INTEGER DEFAULT 1,
            started_at REAL, ends_at REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pass_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, text TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pass_hall (
            id INTEGER PRIMARY KEY AUTOINCREMENT, season INTEGER,
            place INTEGER, name TEXT, tokens INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
            user_id INTEGER, kind TEXT, text TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY, kind TEXT, currency TEXT,
            per INTEGER, extra INTEGER DEFAULT 0, total INTEGER,
            used INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS code_uses (
            code TEXT, user_id INTEGER, ts REAL, gain INTEGER,
            PRIMARY KEY (code, user_id))''')
        for col, ddl in [
            ("tokens","INTEGER DEFAULT 0"),("last_daily","REAL DEFAULT 0"),
            ("referrer_id","INTEGER DEFAULT 0"),("level","INTEGER DEFAULT 1"),
            ("xp","INTEGER DEFAULT 0"),("gift_bank","REAL DEFAULT 0"),
            ("welcome","INTEGER DEFAULT 0"),("free_cases","INTEGER DEFAULT 0"),
            ("boost_until","REAL DEFAULT 0"),("boost_mult","REAL DEFAULT 1"),
            ("last_seen","REAL DEFAULT 0"),("created_at","REAL DEFAULT 0"),
            ("blocked","INTEGER DEFAULT 0"),("banned","INTEGER DEFAULT 0"),
            ("ref_paid","INTEGER DEFAULT 0"),("activated","INTEGER DEFAULT 0"),
        ]:
            try: c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError: pass

def ensure_user(conn, uid, un=None, fn=None):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone(); now = time.time()
    if row is None:
        c.execute("INSERT INTO users (user_id,username,first_name,created_at,last_seen) VALUES(?,?,?,?,?)",
                  (uid, un, fn, now, now))
    elif un is not None or fn is not None:
        c.execute("UPDATE users SET username=?,first_name=?,last_seen=? WHERE user_id=?", (un, fn, now, uid))
    else:
        c.execute("UPDATE users SET last_seen=? WHERE user_id=?", (now, uid))
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return c.fetchone()

def needed_xp(level): return 200 * level

def _add_xp(conn, uid, amount):
    c = conn.cursor()
    c.execute("SELECT level,xp FROM users WHERE user_id=?", (uid,))
    r = c.fetchone(); level, xp, gained = r["level"], r["xp"] + amount, 0
    while level < 20 and xp >= needed_xp(level):
        xp -= needed_xp(level); level += 1; gained += 1
    c.execute("UPDATE users SET level=?,xp=? WHERE user_id=?", (level, xp, uid))
    return gained

def add_coins(conn, uid, amount):
    conn.execute("UPDATE users SET coins=MAX(0,coins+?) WHERE user_id=?", (amount, uid))
    return _add_xp(conn, uid, amount) if amount > 0 else 0

def add_tokens(conn, uid, amount):
    conn.execute("UPDATE users SET tokens=MAX(0,tokens+?) WHERE user_id=?", (amount, uid))

def get_balance(conn, uid):
    return conn.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()["coins"]

def fmt_hours(h):
    return f"{int(h*60)} мин" if h < 1 else f"{int(h)} ч {int((h%1)*60)} мин"

def bar(value, total, width=10):
    filled = min(width, int(value/total*width)) if total else width
    return "█"*filled + "░"*(width-filled)

def ago(ts):
    if not ts: return "никогда"
    d = max(0, int(time.time()-ts))
    if d < 60: return f"{d} сек назад"
    if d < 3600: return f"{d//60} мин назад"
    if d < 86400: return f"{d//3600} ч назад"
    return f"{d//86400} дн назад"

def user_label(conn, uid):
    r = conn.execute("SELECT username,first_name FROM users WHERE user_id=?", (uid,)).fetchone()
    if not r: return f"id{uid}"
    return f"@{esc(r['username'])}" if r["username"] else esc(r["first_name"] or "Игрок")

def act(conn, uid, kind, what):
    conn.execute("INSERT INTO activity(ts,user_id,kind,text) VALUES(?,?,?,?)",
                 (time.time(), uid, kind, f"{user_label(conn, uid)} {what}"))
    conn.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT ?)", (LOG_KEEP,))

def setting_get(conn, key, default="0"):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default

def setting_set(conn, key, value):
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))

# --- ФЕРМА ---
BUSINESSES = {
    1: {"name":"Лимонадный ларёк","emoji":"🍋","price":50,"income":2},
    2: {"name":"Кофейня","emoji":"☕","price":200,"income":7},
    3: {"name":"Пиццерия","emoji":"🍕","price":700,"income":22},
    4: {"name":"Фабрика","emoji":"🏭","price":2500,"income":70},
    5: {"name":"IT-стартап","emoji":"🚀","price":10000,"income":260},
}
def biz_rate(bid, lvl): return BUSINESSES[bid]["income"]*lvl
def biz_cost(bid, lvl): return int(BUSINESSES[bid]["price"]*(1.4**lvl))

def get_biz_rows(conn, uid):
    rows = conn.execute("SELECT biz_id,level,last_collect FROM business WHERE user_id=?", (uid,)).fetchall()
    owned = {r["biz_id"]: dict(r) for r in rows}
    return {b: owned.get(b, {"biz_id":b,"level":0,"last_collect":0.0}) for b in BUSINESSES}

def biz_pending(bid, lvl, last):
    if lvl <= 0 or last <= 0: return 0, 0.0
    elapsed = max(0.0, (time.time()-last)/3600)
    capped = min(elapsed, CAP_HOURS)
    return int(biz_rate(bid, lvl)*capped), capped

def boost_active(conn, uid):
    u = conn.execute("SELECT boost_until,boost_mult FROM users WHERE user_id=?", (uid,)).fetchone()
    return u["boost_mult"] if u["boost_until"] > time.time() else 1.0

def collect_one(conn, uid, bid, row):
    lvl, last = row["level"], row["last_collect"]
    if lvl <= 0: return 0
    base, _ = biz_pending(bid, lvl, last)
    now = time.time(); elapsed = max(0.0, (now-last)/3600); rate = biz_rate(bid, lvl)
    new_last = now if elapsed >= CAP_HOURS else last + (base/rate)*3600
    conn.execute("UPDATE business SET last_collect=? WHERE user_id=? AND biz_id=?", (new_last, uid, bid))
    payout = int(base * boost_active(conn, uid))
    if payout > 0: add_coins(conn, uid, payout)
    return payout

def collect_all_biz(conn, uid):
    return sum(collect_one(conn, uid, b, r) for b, r in get_biz_rows(conn, uid).items())

def total_biz_rate(conn, uid):
    return sum(biz_rate(b, r["level"]) for b, r in get_biz_rows(conn, uid).items())

# --- ПОДАРКИ ---
GIFTS = {
    1: {"emoji":"🍾","name":"Шампанское","price":50,"bonus":1.5,"period":2.0},
    2: {"emoji":"🎁","name":"Подарок","price":25,"bonus":0.9,"period":1.5},
    3: {"emoji":"❤️","name":"Сердечко","price":15,"bonus":0.5,"period":1.8},
    4: {"emoji":"🎟️","name":"Жетон пасса","price":0,"bonus":2,"period":1.0,"pass_only":True},
    5: {"emoji":"👑","name":"Корона пасса","price":0,"bonus":5,"period":1.0,"pass_only":True},
    6: {"emoji":"💎","name":"Кристалл пасса","price":0,"bonus":12,"period":1.0,"pass_only":True},
    7: {"emoji":"🌟","name":"Звезда пасса","price":0,"bonus":30,"period":1.0,"pass_only":True},
}
def gift_rate(gid, qty):
    g = GIFTS[gid]; return g["bonus"]/g["period"]*qty
def gift_sell_price(gid): return int(GIFTS[gid]["price"]*GIFT_SELL_PART)

def get_gift_rows(conn, uid):
    rows = conn.execute("SELECT gift_id,qty,last_collect FROM gifts WHERE user_id=?", (uid,)).fetchall()
    owned = {r["gift_id"]: dict(r) for r in rows}
    return {g: owned.get(g, {"gift_id":g,"qty":0,"last_collect":0.0}) for g in GIFTS}

def gift_pending(gid, qty, last):
    if qty <= 0 or last <= 0: return 0.0, 0.0
    elapsed = max(0.0, (time.time()-last)/3600)
    capped = min(elapsed, GIFT_CAP_HOURS)
    return gift_rate(gid, qty)*capped, capped

def bank_add(conn, uid, amount):
    if amount > 0:
        conn.execute("UPDATE users SET gift_bank=gift_bank+? WHERE user_id=?", (amount, uid))

def bank_payout(conn, uid):
    bank = conn.execute("SELECT gift_bank FROM users WHERE user_id=?", (uid,)).fetchone()["gift_bank"]
    payout = int(bank)
    if payout > 0:
        conn.execute("UPDATE users SET gift_bank=gift_bank-? WHERE user_id=?", (payout, uid))
        add_coins(conn, uid, payout)
    return payout

def settle_gift(conn, uid, gid, row):
    if row["qty"] <= 0: return 0.0
    earned, _ = gift_pending(gid, row["qty"], row["last_collect"])
    bank_add(conn, uid, earned)
    conn.execute("UPDATE gifts SET last_collect=? WHERE user_id=? AND gift_id=?", (time.time(), uid, gid))
    return earned

def total_gift_rate(conn, uid):
    return sum(gift_rate(g, r["qty"]) for g, r in get_gift_rows(conn, uid).items())

def collect_everything(conn, uid):
    biz = collect_all_biz(conn, uid)
    for gid, row in get_gift_rows(conn, uid).items():
        settle_gift(conn, uid, gid, row)
    return biz, bank_payout(conn, uid)

def give_gift(conn, uid, gid, qty):
    row = get_gift_rows(conn, uid)[gid]
    settle_gift(conn, uid, gid, row)
    now = time.time()
    if row["qty"] == 0:
        conn.execute("INSERT INTO gifts(user_id,gift_id,qty,last_collect) VALUES(?,?,?,?)", (uid, gid, qty, now))
    else:
        conn.execute("UPDATE gifts SET qty=qty+?,last_collect=? WHERE user_id=? AND gift_id=?", (qty, now, uid, gid))

# --- АПГРЕЙД ---
UPGRADE_TIERS = [(1.2,0.80),(1.4,0.68),(1.6,0.58),(1.8,0.50),(2.0,0.45),(3.0,0.28),(5.0,0.16),(10.0,0.07)]
def parse_mult(raw):
    s = raw.lower().replace(",",".").replace("x","").replace("х","").strip()
    try: val = float(s)
    except ValueError: return None
    for m, c in UPGRADE_TIERS:
        if abs(m-val) < 0.001: return m, c
    return None

# --- ЛЬДИНЫ ---
ICE_DIFFICULTIES = {
    "easy":{"name":"🟢 Легко","mult":0.5,"rate":0.80},
    "medium":{"name":"🟡 Средне","mult":1.0,"rate":0.60},
    "hard":{"name":"🔴 Сложно","mult":2.0,"rate":0.40},
    "extreme":{"name":"💀 Экстрим","mult":3.0,"rate":0.25},
    "madness":{"name":"🤯 Безумие","mult":5.0,"rate":0.10},
}

# --- ПАСС ---
PASS_ACTIONS = {
    "bonus":{"t":3,"cap":6}, "collect":{"t":2,"cap":30}, "case":{"t":2,"cap":60},
    "ice":{"t":3,"cap":40}, "up":{"t":2,"cap":60}, "buy":{"t":5,"cap":15},
    "gift":{"t":3,"cap":30}, "ref":{"t":10,"cap":100},
}
def tier_threshold(n): return n*n + 9*n
def unlocked_tier(tokens):
    t = 0
    for n in range(1, PASS_TIERS+1):
        if tokens >= tier_threshold(n): t = n
        else: break
    return t

def tier_reward(n):
    if n % 25 == 0:
        return [("gift", 4+(n//25-1), 1), ("stars", 150*(n//25)), ("tokens", 5)]
    if n % 20 == 0: return [("boost", 1.5, 24), ("stars", 60)]
    if n % 10 == 0: return [("gift", 1+(n//10)%3, 2), ("stars", 40+n)]
    if n % 5 == 0:  return [("tokens", 2), ("cases", 1), ("stars", 20)]
    if n % 3 == 0:  return [("stars", 15+n)]
    return [("stars", 8+n//2)]

def reward_text(r):
    parts = []
    for it in r:
        k = it[0]
        if k == "stars": parts.append(f"{it[1]}⭐")
        elif k == "tokens": parts.append(f"{it[1]}🪙")
        elif k == "cases": parts.append(f"{it[1]} кейс")
        elif k == "gift": parts.append(f"{GIFTS[it[1]]['emoji']}×{it[2]}")
        elif k == "boost": parts.append(f"буст x{it[1]} {it[2]}ч")
    return " + ".join(parts)

def pass_log(conn, text):
    conn.execute("INSERT INTO pass_events(ts,text) VALUES(?,?)", (time.time(), text))
    conn.execute("DELETE FROM pass_events WHERE id NOT IN (SELECT id FROM pass_events ORDER BY id DESC LIMIT 60)")

def check_season(conn):
    c = conn.cursor(); now = time.time()
    c.execute("SELECT * FROM pass_season WHERE id=1")
    s = c.fetchone()
    if s is None:
        c.execute("INSERT INTO pass_season(id,season,started_at,ends_at) VALUES(1,1,?,?)",
                  (now, now+PASS_SEASON_DAYS*86400))
        pass_log(conn, "🏁 Сезон 1 начался")
        return
    if now >= s["ends_at"]:
        top = c.execute("SELECT user_id,tokens FROM pass ORDER BY tokens DESC LIMIT 3").fetchall()
        for i, r in enumerate(top, 1):
            c.execute("INSERT INTO pass_hall(season,place,name,tokens) VALUES(?,?,?,?)",
                      (s["season"], i, user_label(conn, r["user_id"]), r["tokens"]))
        c.execute("DELETE FROM pass"); c.execute("DELETE FROM pass_daily")
        ns = s["season"]+1
        c.execute("UPDATE pass_season SET season=?,started_at=?,ends_at=? WHERE id=1",
                  (ns, now, now+PASS_SEASON_DAYS*86400))
        pass_log(conn, f"🏁 Сезон {s['season']} завершён. Сезон {ns} начался")

def pass_row(conn, uid):
    r = conn.execute("SELECT tokens,golden,claimed FROM pass WHERE user_id=?", (uid,)).fetchone()
    return dict(r) if r else {"tokens":0,"golden":0,"claimed":0}

def pass_add_raw(conn, uid, amount):
    conn.execute("""INSERT INTO pass(user_id,tokens,golden,claimed) VALUES(?,?,0,0)
                    ON CONFLICT(user_id) DO UPDATE SET tokens=MAX(0,tokens+?)""",
                 (uid, max(0, amount), amount))

def pass_award(conn, uid, action):
    check_season(conn)
    cfg = PASS_ACTIONS.get(action)
    if not cfg: return ""
    day = int(time.time()//86400)
    c = conn.cursor()
    c.execute("SELECT count FROM pass_daily WHERE user_id=? AND day=? AND action=?", (uid, day, action))
    r = c.fetchone(); cnt = r["count"] if r else 0
    if cnt >= cfg["cap"]: return ""
    c.execute("""INSERT INTO pass_daily(user_id,day,action,count) VALUES(?,?,?,1)
                 ON CONFLICT(user_id,day,action) DO UPDATE SET count=count+1""", (uid, day, action))
    golden = random.random() < PASS_GOLDEN_CHANCE
    gained = cfg["t"] + (PASS_GOLDEN_VALUE if golden else 0)
    p = pass_row(conn, uid); old = p["tokens"]; new = old + gained
    g = p["golden"] + (1 if golden else 0)
    conn.execute("""INSERT INTO pass(user_id,tokens,golden,claimed) VALUES(?,?,?,0)
                    ON CONFLICT(user_id) DO UPDATE SET tokens=?,golden=?""", (uid, new, g, new, g))
    old_t, new_t = unlocked_tier(old), unlocked_tier(new)
    note = f"\n🎟️ Пасс: +{cfg['t']} жетон" + ("а" if cfg["t"] % 10 == 1 and cfg["t"] != 11 else "ов")
    if golden:
        note += f"\n🌟 Золотой жетон: +{PASS_GOLDEN_VALUE}"
        pass_log(conn, f"🌟 {user_label(conn, uid)} выбил золотой жетон")
    if new_t > old_t:
        note += f"\n🎉 Открыта награда {new_t}! Забрать — /pass claim"
        if new_t % 10 == 0:
            pass_log(conn, f"⬆️ {user_label(conn, uid)} открыл награду {new_t}")
    return note

def apply_reward(conn, uid, r):
    acc = {"stars":0,"tokens":0,"cases":0,"gifts":[],"boost":None}
    for it in r:
        k = it[0]
        if k == "stars": add_coins(conn, uid, it[1]); acc["stars"] += it[1]
        elif k == "tokens": add_tokens(conn, uid, it[1]); acc["tokens"] += it[1]
        elif k == "cases":
            conn.execute("UPDATE users SET free_cases=free_cases+? WHERE user_id=?", (it[1], uid)); acc["cases"] += it[1]
        elif k == "gift": give_gift(conn, uid, it[1], it[2]); acc["gifts"].append(f"{GIFTS[it[1]]['emoji']}×{it[2]}")
        elif k == "boost":
            now = time.time()
            u = conn.execute("SELECT boost_until,boost_mult FROM users WHERE user_id=?", (uid,)).fetchone()
            until = max(now, u["boost_until"]) + it[2]*3600
            mult = max(it[1], u["boost_mult"] if u["boost_until"] > now else 1)
            conn.execute("UPDATE users SET boost_until=?,boost_mult=? WHERE user_id=?", (until, mult, uid))
            acc["boost"] = f"x{it[1]} на {it[2]}ч"
    return acc

# --- КОДЫ (промо + чеки) ---
CUR = {"stars":"stars","star":"stars","звезды":"stars","звёзды":"stars","звезда":"stars",
       "tokens":"tokens","token":"tokens","токены":"tokens","токен":"tokens",
       "pass":"pass","жетоны":"pass","жетон":"pass"}
CUR_LABEL = {"stars":"⭐️ звёзды","tokens":"🪙 токены","pass":"🎟️ жетоны"}
CUR_ICON = {"stars":"⭐️","tokens":"🪙","pass":"🎟️"}

def gen_code(n=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

def apply_currency(conn, uid, cur, amount):
    if cur == "stars": return add_coins(conn, uid, amount)
    if cur == "tokens": add_tokens(conn, uid, amount); return 0
    pass_add_raw(conn, uid, amount); return 0

async def broadcast_text(text):
    with db() as conn:
        users = [r["user_id"] for r in conn.execute("SELECT user_id FROM users WHERE blocked=0 AND banned=0").fetchall()]
    ok = fail = blocked = 0
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML"); ok += 1
        except TelegramForbiddenError:
            blocked += 1
            with db() as conn: conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try: await bot.send_message(uid, text, parse_mode="HTML"); ok += 1
            except Exception: fail += 1
        except Exception: fail += 1
        await asyncio.sleep(0.05)
    return ok, fail, blocked

# --- КНОПКИ ---
B_BONUS,B_PROF,B_TOP = "🎁 Бонус","👤 Профиль","🏆 Топ"
B_FARM,B_COLL,B_MARKET = "🏭 Ферма","💰 Собрать","🛍 Маркет"
B_UP,B_CASE,B_ICE = "⚡ Апгрейд","📦 Кейс","🧊 Льдины"
B_EXCH,B_REF,B_HELP = "💱 Обмен","👥 Реферал","❓ Помощь"
B_PASS,B_PTOPY,B_FEED = "🎟️ Пасс","🏅 Топ пасса","📡 События"
B_CODE = "🎁 Промокод"

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text=B_BONUS), KeyboardButton(text=B_PROF), KeyboardButton(text=B_TOP)],
    [KeyboardButton(text=B_FARM), KeyboardButton(text=B_COLL), KeyboardButton(text=B_MARKET)],
    [KeyboardButton(text=B_UP), KeyboardButton(text=B_CASE), KeyboardButton(text=B_ICE)],
    [KeyboardButton(text=B_EXCH), KeyboardButton(text=B_REF), KeyboardButton(text=B_HELP)],
    [KeyboardButton(text=B_PASS), KeyboardButton(text=B_PTOPY), KeyboardButton(text=B_FEED)],
    [KeyboardButton(text=B_CODE)],
], resize_keyboard=True, input_field_placeholder="Выбери действие или введи команду")

INSTRUCTIONS = (
    "📖 <b>ИНСТРУКЦИЯ</b>\n\n"
    "Копи звёзды ⭐ и покупай то, что приносит новые звёзды само.\n\n"
    "<b>ШАГ 1 · Получи первые звёзды</b>\n"
    "/bonus — бесплатные 5–50⭐ раз в 12 часов\n"
    "/case — кейс за 5⭐\n"
    "/code CODE — активировать промокод или чек\n"
    "/ref — друг по ссылке: +10⭐ тебе, +20⭐ другу\n\n"
    "<b>ШАГ 2 · Купи пассивный доход</b>\n"
    "/farm — список бизнесов\n"
    "/buy 1 — купить первый бизнес\n"
    "/market — подарки, тоже дают доход\n"
    "/gbuy 3 — купить подарок\n\n"
    "<b>ШАГ 3 · Собирай заработанное</b>\n"
    "/collect — забрать всё накопленное\n"
    "Доход копится 12 часов, потом останавливается.\n\n"
    "<b>ШАГ 4 · Умножай риск</b>\n"
    "/up — апгрейд: умножь звёзды до x10\n"
    "/ice — льдины: прыгай и копи приз\n\n"
    "<b>ПАСС</b>\n"
    "/pass — дорожка наград, /pass claim — забрать\n"
    "/pass limits — откуда жетоны\n\n"
    "<b>ЕЩЁ</b>\n"
    "/exchange — токены в звёзды, 1 = 3⭐\n"
    "/profile · /top · /feed · /help"
)

# ═══════════ ОСНОВНОЕ ═══════════

async def do_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: ref_id = int(args[1][4:])
        except ValueError: pass
    welcome = 0; bound = False
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        check_season(conn)
        if not u["welcome"]:
            welcome = START_BONUS
            add_coins(conn, uid, START_BONUS)
            conn.execute("UPDATE users SET welcome=1 WHERE user_id=?", (uid,))
        if ref_id:
            bound = bind_referrer(conn, uid, ref_id)
        bal = get_balance(conn, uid)
    hello = f"👋 <b>Привет, {esc(message.from_user.first_name)}!</b>\n\n"
    gift = ""
    if welcome: gift += f"🎁 Стартовый подарок: <b>+{welcome}⭐</b>\n"
    if bound: gift += f"👥 Ты по приглашению. Забери первый бонус — получишь ещё <b>+{NEWBIE_ACTIVATION}⭐</b>\n"
    if gift: gift += f"💳 Баланс: <b>{bal}⭐</b>\n"
    await message.answer(hello + gift + "\n" + INSTRUCTIONS, reply_markup=MAIN_KB, parse_mode="HTML")

async def do_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(INSTRUCTIONS, reply_markup=MAIN_KB, parse_mode="HTML")

async def do_profile(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        br = total_biz_rate(conn, uid); gr = total_gift_rate(conn, uid)
        refs = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=? AND activated=1", (uid,)).fetchone()["n"]
        gifts_n = conn.execute("SELECT COALESCE(SUM(qty),0) n FROM gifts WHERE user_id=?", (uid,)).fetchone()["n"]
        biz_n = conn.execute("SELECT COUNT(*) n FROM business WHERE user_id=? AND level>0", (uid,)).fetchone()["n"]
        p = pass_row(conn, uid); boost = boost_active(conn, uid)
    lvl, xp = u["level"], u["xp"]
    need = needed_xp(lvl) if lvl < 20 else 0
    xp_line = f"{bar(xp, need)}  {xp} / {need} XP" if need else "Максимальный уровень 🏅"
    boost_line = f"\n⚡ Буст фермы: x{boost}" if boost > 1 else ""
    await message.answer(
        f"👤 <b>ПРОФИЛЬ</b>\n\n"
        f"⭐️ Звёзды: <b>{u['coins']}</b>\n"
        f"🪙 Токены: <b>{u['tokens']}</b>\n"
        f"🎟️ Жетоны пасса: <b>{p['tokens']}</b>\n\n"
        f"📊 <b>Уровень {lvl} из 20</b>\n{xp_line}\n\n"
        f"<b>Пассивный доход</b>\n"
        f"<blockquote>🏭 Бизнесы ({biz_n} шт): {br}⭐/ч\n"
        f"🎁 Подарки ({gifts_n} шт): {gr:.2f}⭐/ч\n"
        f"📈 Всего: {br+gr:.2f}⭐/ч{boost_line}</blockquote>\n\n"
        f"🏦 Копилка дробей: {u['gift_bank']:.2f}⭐\n"
        f"📦 Бесплатные кейсы: {u['free_cases']}\n"
        f"👥 Активных друзей: {refs}",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_bonus(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        left = BONUS_COOLDOWN - (time.time() - (u["last_daily"] or 0))
        if left > 0:
            await message.answer(f"⏳ <b>Бонус ещё не готов</b>\n\nПриходи через <b>{fmt_hours(left/3600)}</b>",
                                 reply_markup=MAIN_KB, parse_mode="HTML")
            return
        reward = random.randint(BONUS_MIN, BONUS_MAX)
        gained = add_coins(conn, uid, reward)
        conn.execute("UPDATE users SET last_daily=? WHERE user_id=?", (time.time(), uid))
        bal = get_balance(conn, uid)
        ref_to_notify = activate_user(conn, uid)
        note = pass_award(conn, uid, "bonus")
        act(conn, uid, "bonus", f"забрал бонус +{reward}⭐")
        was_activated = u["activated"]
    if ref_to_notify:
        try:
            await bot.send_message(ref_to_notify,
                f"🎉 <b>Друг активировался!</b>\n\n{esc(message.from_user.first_name)} начал играть.\n⭐️ Тебе +{REF_REWARD}",
                parse_mode="HTML")
        except Exception: pass
    lvl_up = "\n📊 <b>Уровень повышен!</b>" if gained else ""
    act_bonus = f"\n🎁 За активацию: <b>+{NEWBIE_ACTIVATION}⭐</b>" if not was_activated else ""
    await message.answer(
        f"🎉 <b>БОНУС ПОЛУЧЕН</b>\n\n⭐️ Начислено: <b>+{reward}</b>{act_bonus}\n"
        f"💳 Баланс: <b>{bal}</b>{lvl_up}{note}\n\nСледующий бонус через 12 часов.",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_collect(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        biz, gifts = collect_everything(conn, uid)
        bal = get_balance(conn, uid)
        rate = total_biz_rate(conn, uid) + total_gift_rate(conn, uid)
        bank = conn.execute("SELECT gift_bank FROM users WHERE user_id=?", (uid,)).fetchone()["gift_bank"]
        note = ""
        if biz + gifts > 0:
            note = pass_award(conn, uid, "collect")
            act(conn, uid, "collect", f"собрал доход +{biz+gifts}⭐")
    if biz + gifts <= 0:
        msg = ("🏭 <b>Нечего собирать</b>\n\nКупи бизнес — /farm или подарок — /market" if rate <= 0
               else f"⏳ <b>Доход копится</b>\n\nСейчас {rate:.2f}⭐/ч. Загляни позже.")
        await message.answer(msg, reply_markup=MAIN_KB, parse_mode="HTML"); return
    await message.answer(
        f"💰 <b>ДОХОД СОБРАН</b>\n\n<blockquote>🏭 Бизнесы: +{biz}⭐\n🎁 Подарки: +{gifts}⭐</blockquote>\n\n"
        f"⭐️ Всего: <b>+{biz+gifts}</b>\n💳 Баланс: <b>{bal}</b>\n"
        f"🏦 Остаток в копилке: {bank:.2f}⭐\n📈 Дальше: {rate:.2f}⭐/ч{note}",
        reply_markup=MAIN_KB, parse_mode="HTML")

# --- ФЕРМА ---
async def do_farm(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        rows = get_biz_rows(conn, uid); bal = get_balance(conn, uid)
    pend_total = rate_total = 0; cards = []
    for bid, biz in BUSINESSES.items():
        r = rows[bid]; lvl = r["level"]; title = f"{biz['emoji']} <b>{biz['name']}</b>"
        if lvl == 0:
            cards.append(f"{title}\n<blockquote>Не куплен\nЦена: {biz_cost(bid,0)}⭐\n"
                         f"Доход: {biz['income']}⭐/ч\nКупить: /buy {bid}</blockquote>")
        else:
            pend, hours = biz_pending(bid, lvl, r["last_collect"])
            pend_total += pend; rate = biz_rate(bid, lvl); rate_total += rate
            ready = f"{pend}⭐" + (" — ПОЛНОЕ ⚠️" if hours >= CAP_HOURS else "")
            block = (f"{title}\n<blockquote>Уровень {lvl} из {MAX_BIZ_LEVEL}\nДоход: {rate}⭐/ч\n"
                     f"Готово: {ready}\n")
            block += (f"Улучшить до {lvl+1}: {biz_cost(bid,lvl)}⭐ → /buy {bid}"
                      if lvl < MAX_BIZ_LEVEL else "Максимальный уровень 🏅")
            cards.append(block + "</blockquote>")
    await message.answer(
        f"🏭 <b>ТВОЯ ФЕРМА</b>\n\n⭐️ Баланс: <b>{bal}</b>\n📈 Доход: <b>{rate_total}⭐/ч</b>\n"
        f"💵 К сбору: <b>{pend_total}⭐</b>\n\nБизнес капает сам. Копится max {CAP_HOURS}ч.\n"
        f"Собрать — /collect\n\n" + "\n\n".join(cards),
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_buy(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in BUSINESSES:
        await message.answer("❌ Формат: /buy N\nПример: /buy 1\nСписок — /farm", reply_markup=MAIN_KB); return
    bid = int(args[1]); biz = BUSINESSES[bid]
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        row = get_biz_rows(conn, uid)[bid]; lvl = row["level"]
        if lvl >= MAX_BIZ_LEVEL:
            await message.answer(f"🏅 {biz['emoji']} уже максимального уровня.", reply_markup=MAIN_KB); return
        settled = collect_one(conn, uid, bid, row)
        cost = biz_cost(bid, lvl); bal = get_balance(conn, uid)
        if bal < cost:
            extra = f"\nСобрано по пути: +{settled}⭐" if settled else ""
            await message.answer(f"❌ Не хватает звёзд.\nНужно {cost}⭐, у тебя {bal}⭐{extra}", reply_markup=MAIN_KB); return
        add_coins(conn, uid, -cost); now = time.time()
        if lvl == 0:
            conn.execute("INSERT INTO business(user_id,biz_id,level,last_collect) VALUES(?,?,1,?)", (uid, bid, now))
        else:
            conn.execute("UPDATE business SET level=?,last_collect=? WHERE user_id=? AND biz_id=?", (lvl+1, now, uid, bid))
        new_bal = get_balance(conn, uid); new_rate = biz_rate(bid, lvl+1)
        note = pass_award(conn, uid, "buy")
        act(conn, uid, "buy", f"купил {biz['emoji']} {biz['name']} ур.{lvl+1} за {cost}⭐")
    title = "КУПЛЕН" if lvl == 0 else f"УЛУЧШЕН ДО УРОВНЯ {lvl+1}"
    await message.answer(
        f"✅ <b>{biz['emoji']} {biz['name']} {title}</b>\n\n"
        f"<blockquote>Потрачено: {cost}⭐\nДоход: {new_rate}⭐/ч\nБаланс: {new_bal}⭐</blockquote>{note}",
        reply_markup=MAIN_KB, parse_mode="HTML")

# --- МАРКЕТ ---
async def do_market(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        rows = get_gift_rows(conn, uid); bal = get_balance(conn, uid); gr = total_gift_rate(conn, uid)
    cards = []; pend_total = 0.0
    for gid, g in GIFTS.items():
        if g.get("pass_only"): continue
        r = rows[gid]; qty = r["qty"]
        pend, hours = gift_pending(gid, qty, r["last_collect"]); pend_total += pend
        per_h = g["bonus"]/g["period"]
        block = (f"{g['emoji']} <b>{g['name']}</b>\n<blockquote>Цена: {g['price']}⭐\n"
                 f"Продажа: {gift_sell_price(gid)}⭐\nБонус: +{g['bonus']}⭐ каждые {g['period']}ч ({per_h:.2f}⭐/ч)\n")
        if qty > 0:
            ready = f"{pend:.2f}⭐" + (" — ПОЛНОЕ ⚠️" if hours >= GIFT_CAP_HOURS else "")
            block += f"У тебя: {qty} шт → {gift_rate(gid,qty):.2f}⭐/ч\nНакоплено: {ready}\n"
        block += f"Купить: /gbuy {gid}" + (f" · Продать: /gsell {gid}" if qty > 0 else "")
        cards.append(block + "</blockquote>")
    await message.answer(
        f"🛍 <b>МАРКЕТ ПОДАРКОВ</b>\n\n⭐️ Баланс: <b>{bal}</b>\n📈 Доход: <b>{gr:.2f}⭐/ч</b>\n"
        f"💵 К сбору: <b>{pend_total:.2f}⭐</b>\n\nПодарки как мини-бизнесы. Продажа {int(GIFT_SELL_PART*100)}%.\n\n"
        + "\n\n".join(cards), reply_markup=MAIN_KB, parse_mode="HTML")

async def do_gbuy(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in GIFTS or GIFTS[int(args[1])].get("pass_only"):
        await message.answer("❌ Формат: /gbuy N [сколько]\nПример: /gbuy 3\nСписок — /market", reply_markup=MAIN_KB); return
    gid = int(args[1]); g = GIFTS[gid]; qty = 1
    if len(args) > 2:
        if not args[2].isdigit() or not (1 <= int(args[2]) <= 100):
            await message.answer("❌ Количество 1–100", reply_markup=MAIN_KB); return
        qty = int(args[2])
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        row = get_gift_rows(conn, uid)[gid]; settle_gift(conn, uid, gid, row)
        cost = g["price"]*qty; bal = get_balance(conn, uid)
        if bal < cost:
            await message.answer(f"❌ Не хватает звёзд. Нужно {cost}⭐, у тебя {bal}⭐", reply_markup=MAIN_KB); return
        add_coins(conn, uid, -cost); give_gift(conn, uid, gid, qty)
        new_qty = row["qty"]+qty; new_bal = get_balance(conn, uid)
        note = pass_award(conn, uid, "gift")
        act(conn, uid, "gift", f"купил подарок {g['emoji']} ×{qty} за {cost}⭐")
    await message.answer(
        f"✅ <b>КУПЛЕНО {g['emoji']} × {qty}</b>\n\n"
        f"<blockquote>Потрачено: {cost}⭐\nВ наличии: {new_qty} шт\n"
        f"Доход: {gift_rate(gid,new_qty):.2f}⭐/ч\nБаланс: {new_bal}⭐</blockquote>{note}",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_gsell(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in GIFTS or GIFTS[int(args[1])].get("pass_only"):
        await message.answer("❌ Формат: /gsell N [сколько|all]\nСписок — /market", reply_markup=MAIN_KB); return
    gid = int(args[1]); g = GIFTS[gid]
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        row = get_gift_rows(conn, uid)[gid]
        if row["qty"] <= 0:
            await message.answer(f"❌ У тебя нет {g['emoji']}", reply_markup=MAIN_KB); return
        qty = 1
        if len(args) > 2:
            if args[2].lower() == "all": qty = row["qty"]
            elif args[2].isdigit() and int(args[2]) >= 1: qty = min(int(args[2]), row["qty"])
            else: await message.answer("❌ Число или all", reply_markup=MAIN_KB); return
        settle_gift(conn, uid, gid, row); earned_bank = bank_payout(conn, uid)
        income = gift_sell_price(gid)*qty; add_coins(conn, uid, income)
        left = row["qty"]-qty
        conn.execute("UPDATE gifts SET qty=?,last_collect=? WHERE user_id=? AND gift_id=?",
                     (left, time.time() if left > 0 else 0, uid, gid))
        bal = get_balance(conn, uid)
        act(conn, uid, "sell", f"продал {g['emoji']} ×{qty} за {income}⭐")
    extra = f"\nДоход собран: +{earned_bank}⭐" if earned_bank else ""
    await message.answer(
        f"💸 <b>ПРОДАНО {g['emoji']} × {qty}</b>\n\n"
        f"<blockquote>Получено: +{income}⭐{extra}\nОсталось: {left} шт\nБаланс: {bal}⭐</blockquote>",
        reply_markup=MAIN_KB, parse_mode="HTML")

# --- АПГРЕЙД ---
async def do_upgrade(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 3:
        with db() as conn:
            ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
            bal = get_balance(conn, uid)
        rows = [f"x{m} — {int(c*100)}%  {bar(c,1,10)}" for m, c in UPGRADE_TIERS]
        await message.answer(
            f"⚡ <b>АПГРЕЙД ЗВЁЗД</b>\n\n⭐️ Баланс: <b>{bal}</b>\n\n"
            f"Ставишь звёзды и выбираешь множитель. Успех — ставка × множитель. Провал — сгорает.\n\n"
            f"<b>Множители и шансы</b>\n<blockquote>" + "\n".join(rows) + "</blockquote>\n\n"
            f"Формат: /up [сумма] [множитель]\nПример: <code>/up 10 1.6</code>\nСтавка {UP_MIN}–{UP_MAX}⭐",
            reply_markup=MAIN_KB, parse_mode="HTML"); return
    if not args[1].isdigit() or not (UP_MIN <= int(args[1]) <= UP_MAX):
        await message.answer(f"❌ Сумма {UP_MIN}–{UP_MAX}", reply_markup=MAIN_KB); return
    amount = int(args[1]); tier = parse_mult(args[2])
    if tier is None:
        await message.answer("❌ Нет такого множителя. Доступно: " + ", ".join(f"x{m}" for m,_ in UPGRADE_TIERS),
                             reply_markup=MAIN_KB); return
    mult, chance = tier
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        if get_balance(conn, uid) < amount:
            await message.answer(f"❌ Не хватает звёзд. Нужно {amount}⭐", reply_markup=MAIN_KB); return
        add_coins(conn, uid, -amount)
    head = f"⚡ <b>АПГРЕЙД</b>\n\nСтавка {amount}⭐ → x{mult}\nШанс {int(chance*100)}%\n\n"
    anim = await message.answer(head + "🔄 Крутим...")
    for frame in ["⚙️ Обработка...", "✨ Почти...", "🎲 Результат..."]:
        await asyncio.sleep(0.55)
        try: await anim.edit_text(head + frame)
        except Exception: pass
    win = random.random() < chance; payout = int(amount*mult) if win else 0
    with db() as conn:
        gained = add_coins(conn, uid, payout) if win else 0
        bal = get_balance(conn, uid)
        note = pass_award(conn, uid, "up")
        act(conn, uid, "up", f"апгрейд x{mult}: " + (f"выиграл {payout}⭐" if win else f"потерял {amount}⭐"))
    if win:
        result = (f"✅ <b>УСПЕХ</b>\n\n<blockquote>Ставка: {amount}⭐ на x{mult}\n"
                  f"Получено: {payout}⭐\nПрибыль: +{payout-amount}⭐</blockquote>\n\n")
    else:
        result = (f"💥 <b>ПРОВАЛ</b>\n\n<blockquote>Ставка: {amount}⭐ на x{mult}\n"
                  f"Шанс был: {int(chance*100)}%\nСтавка сгорела</blockquote>\n\n")
    lvl_up = "📊 <b>Уровень повышен!</b>\n" if gained else ""
    await anim.edit_text(result + f"💳 Баланс: <b>{bal}⭐</b>\n{lvl_up}{note}\n\nПовторить: /up {amount} {mult}",
                         parse_mode="HTML")

# --- ОБМЕН ---
async def do_exchange(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 2:
        with db() as conn:
            u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        await message.answer(
            f"💱 <b>ОБМЕН ТОКЕНОВ</b>\n\n🪙 Токены: <b>{u['tokens']}</b>\n⭐️ Звёзды: <b>{u['coins']}</b>\n\n"
            f"<blockquote>Курс: 1 токен = {TOKEN_RATE}⭐\nДоступно: {u['tokens']*TOKEN_RATE}⭐</blockquote>\n\n"
            f"Формат: /exchange [кол-во]\nПример: <code>/exchange 2</code>\nВсё: <code>/exchange all</code>",
            reply_markup=MAIN_KB, parse_mode="HTML"); return
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        have = u["tokens"]
        if have <= 0:
            await message.answer("❌ Нет токенов. Получи в /case", reply_markup=MAIN_KB); return
        if args[1].lower() == "all": count = have
        elif args[1].isdigit() and int(args[1]) >= 1: count = int(args[1])
        else: await message.answer("❌ Число или all", reply_markup=MAIN_KB); return
        if count > have:
            await message.answer(f"❌ У тебя только {have} токенов", reply_markup=MAIN_KB); return
        stars = count*TOKEN_RATE; add_tokens(conn, uid, -count); gained = add_coins(conn, uid, stars)
        bal = get_balance(conn, uid); left = have-count
        act(conn, uid, "exchange", f"обменял {count}🪙 на {stars}⭐")
    lvl_up = "\n📊 <b>Уровень повышен!</b>" if gained else ""
    await message.answer(
        f"💱 <b>ОБМЕН ВЫПОЛНЕН</b>\n\n<blockquote>Отдано: {count}🪙\nПолучено: +{stars}⭐</blockquote>\n\n"
        f"🪙 Осталось: {left}\n💳 Баланс: <b>{bal}⭐</b>{lvl_up}",
        reply_markup=MAIN_KB, parse_mode="HTML")

# --- КЕЙС ---
async def do_case(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        if u["free_cases"] > 0:
            conn.execute("UPDATE users SET free_cases=free_cases-1 WHERE user_id=?", (uid,))
            used_free = True
        else:
            if get_balance(conn, uid) < 5:
                await message.answer("❌ Нужно 5⭐ для кейса.", reply_markup=MAIN_KB); return
            add_coins(conn, uid, -5); used_free = False
    anim = await message.answer("📦 Открываем кейс...")
    for frame in ["🎰 Крутим...", "✨ Ещё чуть-чуть...", "🎁 Открываем!"]:
        await asyncio.sleep(0.6)
        try: await anim.edit_text(frame)
        except Exception: pass
    items = [("⭐️ +18 звёзд",5.8,"coins",18),("⭐️ +11 звёзд",9.8,"coins",11),
             ("⭐️ +6 звёзд",11.3,"coins",6),("🪙 2 токена",34.7,"tokens",2),("😔 Пусто",38.4,"none",0)]
    roll, acc, prize = random.uniform(0,100), 0, items[-1]
    for it in items:
        acc += it[1]
        if roll <= acc: prize = it; break
    with db() as conn:
        if prize[2] == "coins": add_coins(conn, uid, prize[3])
        elif prize[2] == "tokens": add_tokens(conn, uid, prize[3])
        bal = get_balance(conn, uid)
        tok = conn.execute("SELECT tokens FROM users WHERE user_id=?", (uid,)).fetchone()["tokens"]
        note = pass_award(conn, uid, "case")
        act(conn, uid, "case", f"открыл кейс → {prize[0]}")
    extra = f"\n🪙 Токенов: {tok} → /exchange" if prize[2] == "tokens" else ""
    free = "\n📦 Использован бесплатный кейс" if used_free else ""
    await anim.edit_text(
        f"🎰 <b>КЕЙС ОТКРЫТ</b>\n\n<blockquote>Выпало: {prize[0]}</blockquote>\n\n"
        f"💳 Баланс: <b>{bal}⭐</b>{extra}{free}{note}\n\nЕщё раз — /case", parse_mode="HTML")

# --- ТОП / РЕФ ---
async def do_top(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        top = conn.execute("SELECT username,first_name,coins FROM users ORDER BY coins DESC LIMIT 10").fetchall()
        me = conn.execute("SELECT COUNT(*)+1 pos FROM users WHERE coins>?", (get_balance(conn, uid),)).fetchone()["pos"]
    if not top:
        await message.answer("Пока нет игроков.", reply_markup=MAIN_KB); return
    medals = ["🥇","🥈","🥉"]; lines = []
    for i, r in enumerate(top, 1):
        m = medals[i-1] if i <= 3 else f"{i}."
        name = f"@{esc(r['username'])}" if r["username"] else esc(r["first_name"] or "Игрок")
        lines.append(f"{m} {name} — {r['coins']}⭐")
    await message.answer(f"🏆 <b>ТОП ПО ЗВЁЗДАМ</b>\n\n<blockquote>" + "\n".join(lines) +
                         f"</blockquote>\n\n📍 Твоё место: <b>{me}</b>", reply_markup=MAIN_KB, parse_mode="HTML")

def bind_referrer(conn, uid, ref_id):
    if not ref_id or ref_id == uid: return False
    c = conn.cursor()
    if not c.execute("SELECT 1 FROM users WHERE user_id=?", (ref_id,)).fetchone(): return False
    c.execute("SELECT referrer_id FROM users WHERE user_id=?", (uid,))
    if c.fetchone()["referrer_id"] != 0: return False
    c.execute("SELECT referrer_id FROM users WHERE user_id=?", (ref_id,))
    if c.fetchone()["referrer_id"] == uid: return False
    c.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref_id, uid))
    return True

def activate_user(conn, uid):
    c = conn.cursor()
    c.execute("SELECT activated,referrer_id,ref_paid FROM users WHERE user_id=?", (uid,))
    u = c.fetchone()
    if u["activated"]: return None
    c.execute("UPDATE users SET activated=1 WHERE user_id=?", (uid,))
    add_coins(conn, uid, NEWBIE_ACTIVATION)
    if u["referrer_id"] and not u["ref_paid"]:
        c.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (uid,))
        add_coins(conn, u["referrer_id"], REF_REWARD)
        pass_award(conn, u["referrer_id"], "ref")
        act(conn, u["referrer_id"], "ref", f"пригласил {user_label(conn, uid)}")
        return u["referrer_id"]
    return None

async def do_ref(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        total = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?", (uid,)).fetchone()["n"]
        active = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=? AND activated=1", (uid,)).fetchone()["n"]
    await message.answer(
        f"👥 <b>ПРИГЛАСИ ДРУГА</b>\n\nОтправь другу ссылку:\n"
        f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>\n\n"
        f"<blockquote>Друг активировался → тебе +{REF_REWARD}⭐\n"
        f"Другу за активацию +{NEWBIE_ACTIVATION}⭐\n"
        f"Приглашено всего: {total}\nАктивных друзей: {active}</blockquote>\n\n"
        f"Друг считается, только когда заберёт первый бонус.\nПовторные переходы ничего не дают.",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_reftop(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        top = conn.execute('''SELECT username,first_name,COUNT(*) n FROM users
                              WHERE referrer_id!=0 AND activated=1
                              GROUP BY referrer_id ORDER BY n DESC LIMIT 10''').fetchall()
    if not top:
        await message.answer("Пока никто не пригласил активных друзей.", reply_markup=MAIN_KB); return
    medals = ["🥇","🥈","🥉"]; lines = []
    for i, r in enumerate(top, 1):
        m = medals[i-1] if i <= 3 else f"{i}."
        name = f"@{esc(r['username'])}" if r["username"] else esc(r["first_name"] or "Игрок")
        lines.append(f"{m} {name} — {r['n']} друзей")
    await message.answer("👥 <b>ТОП ПРИГЛАШЕНИЙ</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# --- ЛЬДИНЫ ---
async def do_ice(message: types.Message, state: FSMContext):
    args = message.text.split(); uid = message.from_user.id
    if len(args) < 2:
        await state.clear()
        with db() as conn:
            ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
            bal = get_balance(conn, uid)
        lines = [f"{v['name']} — x{v['mult']}, шанс {int(v['rate']*100)}%\n/ice {k}" for k, v in ICE_DIFFICULTIES.items()]
        await message.answer(
            f"🧊 <b>ЛЬДИНЫ</b>\n\n⭐️ Баланс: <b>{bal}</b>\n\n"
            f"Прыгай и копи приз. Забрать можно в любой момент. Упал — теряешь всё.\n\n"
            f"<b>Сложности</b>\n<blockquote>" + "\n\n".join(lines) + "</blockquote>\n\n"
            f"Формат: /ice [сложность] [ставка 1-10]\nПример: <code>/ice extreme 5</code>",
            reply_markup=MAIN_KB, parse_mode="HTML"); return
    await state.clear()
    diff = args[1].lower()
    if diff not in ICE_DIFFICULTIES:
        await message.answer("❌ Нет такой сложности. Доступно: " + ", ".join(ICE_DIFFICULTIES), reply_markup=MAIN_KB); return
    bet = 1
    if len(args) > 2:
        if not args[2].isdigit() or not (1 <= int(args[2]) <= 10):
            await message.answer("❌ Ставка 1–10", reply_markup=MAIN_KB); return
        bet = int(args[2])
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        if get_balance(conn, uid) < bet:
            await message.answer(f"❌ Нужно {bet}⭐", reply_markup=MAIN_KB); return
        add_coins(conn, uid, -bet)
    await state.update_data(difficulty=diff, bet=bet, reward=0, jumps=0)
    await state.set_state(St.playing_ice)
    d = ICE_DIFFICULTIES[diff]
    await message.answer(
        f"🧊 <b>ИГРА НАЧАЛАСЬ</b>\n\n<blockquote>{d['name']}\nСтавка: {bet}⭐\n"
        f"Шанс: {int(d['rate']*100)}%\nВ призе: 0⭐</blockquote>\n\n"
        f"/jump — прыгнуть\n/take — забрать\n/quit — сдаться",
        reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB); return
    data = await state.get_data(); d = ICE_DIFFICULTIES[data["difficulty"]]; bet = data["bet"]
    if random.random() < d["rate"]:
        gain = max(1, int(bet*d["mult"])); reward, jumps = data["reward"]+gain, data["jumps"]+1
        await state.update_data(reward=reward, jumps=jumps)
        await message.answer(
            f"✅ <b>УСПЕШНЫЙ ПРЫЖОК</b>\n\n<blockquote>Добавлено: +{gain}⭐\n"
            f"В призе: {reward}⭐\nПрыжков: {jumps}</blockquote>\n\n"
            f"/jump — ещё\n/take — забрать {reward}⭐\n/quit — сдаться",
            reply_markup=MAIN_KB, parse_mode="HTML")
    else:
        await state.clear()
        with db() as conn:
            act(conn, message.from_user.id, "ice", f"упал во льдинах, потерял {bet}⭐")
            note = pass_award(conn, message.from_user.id, "ice")
        await message.answer(
            f"💦 <b>ПРОВАЛ</b>\n\nЛьдина треснула.\n\n<blockquote>Потеряна ставка: {bet}⭐\n"
            f"Сгорел приз: {data['reward']}⭐</blockquote>{note}\n\nСнова — /ice",
            reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("take"))
async def cmd_take(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB); return
    data = await state.get_data(); await state.clear()
    reward, bet, jumps = data["reward"], data["bet"], data["jumps"]
    with db() as conn:
        if reward > 0: add_coins(conn, message.from_user.id, reward)
        bal = get_balance(conn, message.from_user.id)
        note = pass_award(conn, message.from_user.id, "ice")
        act(conn, message.from_user.id, "ice", f"забрал приз во льдинах +{reward}⭐")
    profit = reward-bet
    await message.answer(
        f"🏆 <b>ПРИЗ ЗАБРАН</b>\n\n<blockquote>Получено: {reward}⭐\nСтавка: {bet}⭐\n"
        f"Итог: {'+' if profit>=0 else ''}{profit}⭐\nПрыжков: {jumps}</blockquote>\n\n"
        f"💳 Баланс: <b>{bal}⭐</b>{note}\n\nИграть снова — /ice",
        reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("quit"))
async def cmd_quit(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре.", reply_markup=MAIN_KB); return
    data = await state.get_data(); await state.clear()
    await message.answer(f"🏳️ <b>СДАЛСЯ</b>\n\n<blockquote>Ставка {data.get('bet',0)}⭐ потеряна</blockquote>\n\nСнова — /ice",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# --- ПАСС ---
async def do_pass(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) > 1 and args[1].lower() == "claim":
        await pass_claim(message); return
    if len(args) > 1 and args[1].lower() == "limits":
        await pass_limits(message); return
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        check_season(conn)
        s = conn.execute("SELECT season,ends_at FROM pass_season WHERE id=1").fetchone()
        p = pass_row(conn, uid)
    tier = unlocked_tier(p["tokens"]); left = s["ends_at"]-time.time()
    nxt = tier+1 if tier < PASS_TIERS else None
    progress = ""
    if nxt:
        prev_th = tier_threshold(tier) if tier else 0
        need = tier_threshold(nxt)-prev_th
        have = p["tokens"]-prev_th
        progress = f"\nДо награды {nxt}: {tier_threshold(nxt)-p['tokens']} жетонов\n{bar(have,need)} {have} / {need}"
    near = []
    for n in range(max(1,tier-1), min(PASS_TIERS,tier+4)+1):
        if n < 1: continue
        status = "✅" if n <= p["claimed"] else ("🔓 забрать" if n <= tier else f"🔒 {tier_threshold(n)}")
        near.append(f"{n} · {reward_text(tier_reward(n))} — {status}")
    await message.answer(
        f"🎟️ <b>ЖЕТОННЫЙ ПАСС · Сезон {s['season']}</b>\n\n"
        f"До конца: {fmt_hours(left/3600)}\n\n"
        f"🎟️ Жетоны: <b>{p['tokens']}</b>\n🌟 Золотые: <b>{p['golden']}</b>\n"
        f"🏅 Открыто: <b>{tier} из {PASS_TIERS}</b>\n📦 Забрано: {p['claimed']}\n"
        f"🎁 Ждёт получения: <b>{max(0,tier-p['claimed'])}</b>{progress}\n\n"
        f"<b>Ближайшие награды</b>\n<blockquote>" + "\n".join(near) + "</blockquote>\n\n"
        f"<b>Эксклюзивы сезона</b>\n<blockquote>25 · 🎟️ Жетон пасса (2⭐/ч)\n"
        f"50 · 👑 Корона пасса (5⭐/ч)\n75 · 💎 Кристалл пасса (12⭐/ч)\n"
        f"100 · 🌟 Звезда пасса (30⭐/ч)</blockquote>\n\n"
        f"/pass claim — забрать · /passlist — дорожка · /pass limits — откуда жетоны",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def pass_claim(message: types.Message):
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        check_season(conn); p = pass_row(conn, uid); tier = unlocked_tier(p["tokens"])
        if tier <= p["claimed"]:
            await message.answer("📦 <b>Пока нечего забирать</b>\n\nКопи жетоны действиями в боте.",
                                 reply_markup=MAIN_KB, parse_mode="HTML"); return
        acc = {"stars":0,"tokens":0,"cases":0,"gifts":[],"boost":None}
        start = p["claimed"]+1
        for n in range(start, tier+1):
            a = apply_reward(conn, uid, tier_reward(n))
            acc["stars"] += a["stars"]; acc["tokens"] += a["tokens"]; acc["cases"] += a["cases"]
            acc["gifts"] += a["gifts"]
            if a["boost"]: acc["boost"] = a["boost"]
            if n % 25 == 0:
                pass_log(conn, f"🏅 {user_label(conn, uid)} забрал эксклюзив пасса (награда {n})")
        conn.execute("UPDATE pass SET claimed=? WHERE user_id=?", (tier, uid))
        bal = get_balance(conn, uid)
        act(conn, uid, "pass", f"забрал награды пасса {start}–{tier}")
    gifts_line = "\n🎁 Подарки: " + ", ".join(acc["gifts"]) if acc["gifts"] else ""
    boost_line = f"\n⚡ Буст: {acc['boost']}" if acc["boost"] else ""
    cases_line = f"\n📦 Кейсы: +{acc['cases']}" if acc["cases"] else ""
    tok_line = f"\n🪙 Токены: +{acc['tokens']}" if acc["tokens"] else ""
    await message.answer(
        f"🎁 <b>НАГРАДЫ ПОЛУЧЕНЫ</b>\n\nЗабрано наград: <b>{tier-start+1}</b> ({start}–{tier})\n\n"
        f"<blockquote>⭐️ Звёзды: +{acc['stars']}{tok_line}{cases_line}{gifts_line}{boost_line}</blockquote>\n\n"
        f"💳 Баланс: <b>{bal}⭐</b>\n🏅 Забрано: {tier} из {PASS_TIERS}",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def pass_limits(message: types.Message):
    uid = message.from_user.id; day = int(time.time()//86400)
    names = {"bonus":"🎁 Бонус","collect":"💰 Сбор дохода","case":"📦 Кейс","ice":"🧊 Льдины",
             "up":"⚡ Апгрейд","buy":"🏭 Покупка бизнеса","gift":"🎁 Покупка подарка","ref":"👥 Друг"}
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        rows = conn.execute("SELECT action,count FROM pass_daily WHERE user_id=? AND day=?", (uid, day)).fetchall()
        used = {r["action"]: r["count"] for r in rows}
        p = pass_row(conn, uid)
    lines = [f"{names[k]} +{v['t']} · сегодня {used.get(k,0)} из {v['cap']}" for k, v in PASS_ACTIONS.items()]
    await message.answer(
        f"🎟️ <b>ОТКУДА ЖЕТОНЫ</b>\n\n🎟️ Всего у тебя: <b>{p['tokens']}</b>\n\n"
        f"<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
        f"🌟 Золотой жетон — шанс {int(PASS_GOLDEN_CHANCE*100)}%, даёт +{PASS_GOLDEN_VALUE} сверху.\n"
        f"Лимиты обновляются в полночь.",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_passlist(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    pages = (PASS_TIERS+9)//10; page = max(1, min(pages, page))
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        p = pass_row(conn, uid)
    tier = unlocked_tier(p["tokens"]); lines = []
    for n in range((page-1)*10+1, min(PASS_TIERS, page*10)+1):
        status = "✅" if n <= p["claimed"] else ("🔓 забрать" if n <= tier else f"🔒 {tier_threshold(n)}")
        lines.append(f"{status} {n} · {reward_text(tier_reward(n))}")
    await message.answer(
        f"🎟️ <b>ДОРОЖКА ПАССА</b>\nСтраница {page} из {pages}\n\n<blockquote>" + "\n".join(lines) +
        f"</blockquote>\n\nУ тебя {p['tokens']} жетонов\n/passlist {page+1} — дальше · /pass claim — забрать",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_passtop(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        check_season(conn)
        s = conn.execute("SELECT season,ends_at FROM pass_season WHERE id=1").fetchone()
        top = conn.execute("SELECT user_id,tokens FROM pass ORDER BY tokens DESC LIMIT 10").fetchall()
        p = pass_row(conn, uid)
        me = conn.execute("SELECT COUNT(*)+1 pos FROM pass WHERE tokens>?", (p["tokens"],)).fetchone()["pos"]
    if not top:
        await message.answer("Пока никто не копил жетоны.", reply_markup=MAIN_KB); return
    medals = ["🥇","🥈","🥉"]; lines = []
    with db() as conn:
        for i, r in enumerate(top, 1):
            m = medals[i-1] if i <= 3 else f"{i}."
            lines.append(f"{m} {user_label(conn, r['user_id'])} — {r['tokens']} жетонов · награда {unlocked_tier(r['tokens'])}")
    await message.answer(
        f"🏅 <b>ТОП ПАССА · Сезон {s['season']}</b>\nДо конца: {fmt_hours((s['ends_at']-time.time())/3600)}\n\n"
        f"<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
        f"📍 Ты: {p['tokens']} жетонов · награда {unlocked_tier(p['tokens'])} · место {me}",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_passevents(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        rows = conn.execute("SELECT text FROM pass_events ORDER BY id DESC LIMIT 15").fetchall()
    if not rows:
        await message.answer("Событий пока нет.", reply_markup=MAIN_KB); return
    await message.answer("📡 <b>СОБЫТИЯ ПАССА</b>\n\n<blockquote>" + "\n".join(r["text"] for r in rows) + "</blockquote>",
                         reply_markup=MAIN_KB, parse_mode="HTML")

async def do_passhall(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        rows = conn.execute("SELECT season,place,name,tokens FROM pass_hall ORDER BY season DESC, place LIMIT 30").fetchall()
    if not rows:
        await message.answer("Зал славы пока пуст. Первый сезон ещё идёт.", reply_markup=MAIN_KB); return
    lines = []; cur = None
    for r in rows:
        if r["season"] != cur:
            cur = r["season"]; lines.append(f"\nСезон {cur}")
        m = ["🥇","🥈","🥉"][r["place"]-1]
        lines.append(f"{m} {r['name']} — {r['tokens']} жетонов")
    await message.answer("🏛️ <b>ЗАЛ СЛАВЫ</b>\n<blockquote>" + "\n".join(lines).strip() + "</blockquote>",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# --- ПРОМО / ЧЕКИ ---
async def do_code_help(message: types.Message):
    await message.answer(
        f"🎁 <b>ПРОМОКОДЫ И ЧЕКИ</b>\n\n"
        f"Введи код, чтобы получить награду:\n"
        f"<code>/code CODE</code>\n\n"
        f"<blockquote>Промокод — фиксированная награда,有限 число активаций.\n"
        f"Чек — общая сумма, делится между первыми N игроками.</blockquote>\n\n"
        f"Новые коды приходят в новостях. Успей забрать!",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_claim(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id; args = message.text.split()
    if len(args) < 2:
        await do_code_help(message); return
    code = args[1].upper()
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        row = conn.execute("SELECT * FROM codes WHERE code=?", (code,)).fetchone()
        if not row or not row["active"]:
            await message.answer("❌ <b>Код не найден или уже закрыт</b>", reply_markup=MAIN_KB, parse_mode="HTML"); return
        if row["used"] >= row["total"]:
            conn.execute("UPDATE codes SET active=0 WHERE code=?", (code,))
            await message.answer("⌛️ <b>Активации закончились</b>", reply_markup=MAIN_KB, parse_mode="HTML"); return
        if conn.execute("SELECT 1 FROM code_uses WHERE code=? AND user_id=?", (code, uid)).fetchone():
            await message.answer("⚠️ <b>Ты уже активировал этот код</b>", reply_markup=MAIN_KB, parse_mode="HTML"); return
        gain = row["per"]
        if row["kind"] == "check" and row["extra"] > 0:
            gain += 1
            conn.execute("UPDATE codes SET extra=extra-1 WHERE code=?", (code,))
        apply_currency(conn, uid, row["currency"], gain)
        new_used = row["used"]+1
        conn.execute("UPDATE codes SET used=?,active=? WHERE code=?", (new_used, 1 if new_used < row["total"] else 0, code))
        conn.execute("INSERT INTO code_uses(code,user_id,ts,gain) VALUES(?,?,?,?)", (code, uid, time.time(), gain))
        bal = get_balance(conn, uid)
        act(conn, uid, "code", f"активировал {row['kind']} {code} → +{gain}{CUR_ICON[row['currency']]}")
        left = row["total"]-new_used
    await message.answer(
        f"🎉 <b>КОД АКТИВИРОВАН</b>\n\n"
        f"<blockquote>{code}\nПолучено: +{gain}{CUR_ICON[row['currency']]}\n"
        f"Осталось активаций: {left}</blockquote>\n\n💳 Баланс: <b>{bal}⭐</b>",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════ АДМИН ═══════════

def resolve_target(conn, message, arg=None):
    rep = message.reply_to_message
    if rep and rep.from_user: return rep.from_user.id
    if not arg: return None
    a = arg.strip()
    if a.isdigit(): return int(a)
    r = conn.execute("SELECT user_id FROM users WHERE username=? COLLATE NOCASE", (a.lstrip("@"),)).fetchone()
    return r["user_id"] if r else None

class TrackMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message) and event.from_user:
            uid = event.from_user.id
            with db() as conn:
                conn.execute("UPDATE users SET last_seen=? WHERE user_id=?", (time.time(), uid))
                r = conn.execute("SELECT banned FROM users WHERE user_id=?", (uid,)).fetchone()
            if r and r["banned"] and uid not in ADMINS:
                return
        return await handler(event, data)

dp.message.outer_middleware(TrackMiddleware())

async def admin_panel(message: types.Message):
    now = time.time()
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        on = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-ONLINE_WINDOW,)).fetchone()["n"]
        play = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-PLAY_WINDOW,)).fetchone()["n"]
        day = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-86400,)).fetchone()["n"]
        new = conn.execute("SELECT COUNT(*) n FROM users WHERE created_at>?", (now-86400,)).fetchone()["n"]
        codes = conn.execute("SELECT COUNT(*) n FROM codes WHERE active=1").fetchone()["n"]
        watch = setting_get(conn, "watch")
    await message.answer(
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        f"<blockquote>🟢 Сейчас в боте: {on}\n🎮 Играют (15 мин): {play}\n"
        f"📅 Активных за 24ч: {day}\n🆕 Новых за 24ч: {new}\n"
        f"👥 Всего пользователей: {total}\n🎁 Активных кодов: {codes}</blockquote>\n\n"
        f"<b>Выдача валюты</b>\n"
        f"/give ID stars 100 · /give ID tokens 5 · /give ID pass 50\n"
        f"/take ID stars 100\n"
        f"Можно ответом: /give stars 100\n\n"
        f"<b>Промокоды и чеки</b>\n"
        f"/mkpromo CODE SUM LIMIT [type] — промокод\n"
        f"/mkcheck SUM COUNT [type] — чек\n"
        f"/codes — список активных\n"
        f"/delcode CODE — закрыть код\n\n"
        f"<b>Новости и рассылка</b>\n"
        f"/news текст — новость всем\n"
        f"/send текст — рассылка (фото/видео тоже)\n"
        f"/say ID текст — лично\n\n"
        f"<b>Информация</b>\n"
        f"/stats · /online · /user ID · /log 20\n"
        f"/watch on — live-события (сейчас: {watch})\n\n"
        f"<b>Модерация</b>\n"
        f"/ban ID · /unban ID",
        parse_mode="HTML")

async def admin_online(message: types.Message):
    now = time.time()
    with db() as conn:
        on = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-ONLINE_WINDOW,)).fetchone()["n"]
        play = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-PLAY_WINDOW,)).fetchone()["n"]
        hour = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-3600,)).fetchone()["n"]
        day = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-86400,)).fetchone()["n"]
        week = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-604800,)).fetchone()["n"]
        total = conn.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        last = conn.execute("SELECT user_id,last_seen FROM users ORDER BY last_seen DESC LIMIT 5").fetchall()
        lines = [f"{user_label(conn, r['user_id'])} — {ago(r['last_seen'])}" for r in last]
    await message.answer(
        f"🟢 <b>ОНЛАЙН</b>\n\n<blockquote>Сейчас (5 мин): {on}\nИграют (15 мин): {play}\n"
        f"За час: {hour}\nЗа сутки: {day}\nЗа неделю: {week}\nВсего в базе: {total}</blockquote>\n\n"
        f"<b>Последние заходившие</b>\n<blockquote>" + "\n".join(lines) + "</blockquote>", parse_mode="HTML")

async def admin_stats(message: types.Message):
    now = time.time()
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        blocked = conn.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"]
        banned = conn.execute("SELECT COUNT(*) n FROM users WHERE banned=1").fetchone()["n"]
        new_d = conn.execute("SELECT COUNT(*) n FROM users WHERE created_at>?", (now-86400,)).fetchone()["n"]
        new_w = conn.execute("SELECT COUNT(*) n FROM users WHERE created_at>?", (now-604800,)).fetchone()["n"]
        day = conn.execute("SELECT COUNT(*) n FROM users WHERE last_seen>?", (now-86400,)).fetchone()["n"]
        stars = conn.execute("SELECT COALESCE(SUM(coins),0) s FROM users").fetchone()["s"]
        tok = conn.execute("SELECT COALESCE(SUM(tokens),0) s FROM users").fetchone()["s"]
        pt = conn.execute("SELECT COALESCE(SUM(tokens),0) s FROM pass").fetchone()["s"]
        biz = conn.execute("SELECT COUNT(*) n FROM business WHERE level>0").fetchone()["n"]
        gf = conn.execute("SELECT COALESCE(SUM(qty),0) n FROM gifts").fetchone()["n"]
        acts = conn.execute("SELECT COUNT(*) n FROM activity WHERE ts>?", (now-86400,)).fetchone()["n"]
        kinds = conn.execute("SELECT kind,COUNT(*) n FROM activity WHERE ts>? GROUP BY kind ORDER BY n DESC LIMIT 6",
                             (now-86400,)).fetchall()
        codes = conn.execute("SELECT COUNT(*) n FROM codes WHERE active=1").fetchone()["n"]
    kl = "\n".join(f"{r['kind']}: {r['n']}" for r in kinds) or "пока пусто"
    await message.answer(
        f"📊 <b>СТАТИСТИКА</b>\n\n<b>Люди</b>\n<blockquote>Всего: {total}\nНовых за 24ч: {new_d}\n"
        f"Новых за 7д: {new_w}\nАктивных за 24ч: {day}\nЗаблокировали бота: {blocked}\nВ бане: {banned}</blockquote>\n\n"
        f"<b>Экономика</b>\n<blockquote>⭐️ Звёзд: {stars}\n🪙 Токенов: {tok}\n🎟️ Жетонов пасса: {pt}\n"
        f"🏭 Бизнесов: {biz}\n🎁 Подарков: {gf}\n🎁 Активных кодов: {codes}</blockquote>\n\n"
        f"<b>Действий за 24ч: {acts}</b>\n<blockquote>{kl}</blockquote>", parse_mode="HTML")

async def admin_give(message: types.Message, sign=1):
    args = message.text.split(); rep = message.reply_to_message
    if rep and rep.from_user:
        if len(args) < 3:
            await message.reply("Формат: /give stars 100 (ответом)"); return
        cur_raw, amt_raw, target = args[1], args[2], rep.from_user.id
    else:
        if len(args) < 4:
            await message.reply("Формат: /give ID stars 100\nТипы: stars, tokens, pass"); return
        cur_raw, amt_raw, target = args[2], args[3], None
    cur = CUR.get(cur_raw.lower())
    if not cur or not amt_raw.lstrip("-").isdigit():
        await message.reply("❌ Тип: stars / tokens / pass. Сумма — число."); return
    amount = abs(int(amt_raw))*sign
    if amount == 0 or abs(amount) > 10_000_000:
        await message.reply("❌ Сумма 1–10 000 000"); return
    with db() as conn:
        if target is None: target = resolve_target(conn, message, args[1])
        if not target:
            await message.reply("❌ Не нашёл пользователя"); return
        ensure_user(conn, target)
        apply_currency(conn, target, cur, amount)
        u = conn.execute("SELECT coins,tokens FROM users WHERE user_id=?", (target,)).fetchone()
        p = pass_row(conn, target); label = user_label(conn, target)
        act(conn, target, "admin", f"{'получил' if sign>0 else 'лишился'} {abs(amount)} {CUR_LABEL[cur]} от админа")
    word = "Выдано" if sign > 0 else "Списано"
    await message.answer(
        f"✅ <b>{word}</b>\n\n<blockquote>Игрок: {label}\n{CUR_LABEL[cur]}: {'+' if sign>0 else '−'}{abs(amount)}</blockquote>\n\n"
        f"Баланс: {u['coins']}⭐️ · {u['tokens']}🪙 · {p['tokens']}🎟️", parse_mode="HTML")
    try:
        await bot.send_message(target,
            f"{'🎁' if sign>0 else '⚠️'} <b>Изменение баланса</b>\n\n{CUR_LABEL[cur]}: {'+' if sign>0 else '−'}{abs(amount)}\nОт администратора.",
            parse_mode="HTML")
    except Exception: pass

async def admin_take(message: types.Message): await admin_give(message, sign=-1)

async def admin_user(message: types.Message):
    args = message.text.split()
    with db() as conn:
        target = resolve_target(conn, message, args[1] if len(args) > 1 else None)
        if not target:
            await message.reply("Формат: /user ID или @username"); return
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (target,)).fetchone()
        if not u:
            await message.reply("❌ Нет такого пользователя"); return
        biz = conn.execute("SELECT COUNT(*) n FROM business WHERE user_id=? AND level>0", (target,)).fetchone()["n"]
        gf = conn.execute("SELECT COALESCE(SUM(qty),0) n FROM gifts WHERE user_id=?", (target,)).fetchone()["n"]
        p = pass_row(conn, target)
        refs = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=? AND activated=1", (target,)).fetchone()["n"]
        label = user_label(conn, target)
    await message.answer(
        f"🔎 <b>{label}</b>\n\n<blockquote>ID: {target}\nБыл: {ago(u['last_seen'])}\n"
        f"Регистрация: {ago(u['created_at'])}\nБан: {'да' if u['banned'] else 'нет'} · Блок: {'да' if u['blocked'] else 'нет'}</blockquote>\n\n"
        f"<blockquote>⭐️ {u['coins']} · 🪙 {u['tokens']} · 🎟️ {p['tokens']}\n"
        f"Уровень {u['level']} · XP {u['xp']}\n🏭 Бизнесов: {biz} · 🎁 Подарков: {gf}\n"
        f"👥 Активных рефералов: {refs}\n🎟️ Наград пасса забрано: {p['claimed']}</blockquote>", parse_mode="HTML")

async def admin_ban(message: types.Message, flag=1):
    args = message.text.split()
    with db() as conn:
        target = resolve_target(conn, message, args[1] if len(args) > 1 else None)
        if not target:
            await message.reply("Формат: /ban ID"); return
        if target in ADMINS:
            await message.reply("❌ Себя нельзя"); return
        ensure_user(conn, target)
        conn.execute("UPDATE users SET banned=? WHERE user_id=?", (flag, target))
        label = user_label(conn, target)
    await message.answer(f"{'🚫 Забанен' if flag else '✅ Разбанен'}: {label}", parse_mode="HTML")

async def admin_unban(message: types.Message): await admin_ban(message, flag=0)

async def admin_log(message: types.Message):
    args = message.text.split()
    n = min(50, int(args[1])) if len(args) > 1 and args[1].isdigit() else 20
    with db() as conn:
        rows = conn.execute("SELECT ts,text FROM activity ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        await message.answer("Лог пустой."); return
    lines = [f"{time.strftime('%H:%M', time.localtime(r['ts']))} · {r['text']}" for r in rows]
    await message.answer(f"📋 <b>ПОСЛЕДНИЕ ДЕЙСТВИЯ ({n})</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>",
                         parse_mode="HTML")

async def public_feed(message: types.Message):
    with db() as conn:
        rows = conn.execute("SELECT text FROM activity ORDER BY id DESC LIMIT 12").fetchall()
    if not rows:
        await message.answer("Пока никто ничего не сделал.", reply_markup=MAIN_KB); return
    await message.answer("📡 <b>ЧТО ПРОИСХОДИТ В БОТЕ</b>\n\n<blockquote>" + "\n".join(r["text"] for r in rows) + "</blockquote>",
                         reply_markup=MAIN_KB, parse_mode="HTML")

async def admin_watch(message: types.Message):
    args = message.text.split()
    val = "1" if len(args) > 1 and args[1].lower() in ("on","1","вкл") else "0"
    with db() as conn: setting_set(conn, "watch", val)
    await message.answer(f"📡 Live-события: <b>{'включены' if val=='1' else 'выключены'}</b>", parse_mode="HTML")

async def watch_loop():
    with db() as conn:
        r = conn.execute("SELECT MAX(id) m FROM activity").fetchone(); last = r["m"] or 0
    while True:
        await asyncio.sleep(4)
        try:
            with db() as conn:
                if setting_get(conn, "watch") != "1":
                    r = conn.execute("SELECT MAX(id) m FROM activity").fetchone(); last = r["m"] or 0
                    continue
                rows = conn.execute("SELECT id,text FROM activity WHERE id>? ORDER BY id LIMIT 20", (last,)).fetchall()
            if rows:
                last = rows[-1]["id"]
                await bot.send_message(ADMIN_ID, "📡 <b>СОБЫТИЯ</b>\n\n<blockquote>" +
                                       "\n".join(r["text"] for r in rows) + "</blockquote>", parse_mode="HTML")
        except Exception: pass

async def admin_say(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Формат: /say ID текст"); return
    with db() as conn: target = resolve_target(conn, message, args[1])
    if not target:
        await message.reply("❌ Не нашёл"); return
    try:
        await bot.send_message(target, f"✉️ <b>Сообщение от администратора</b>\n\n{args[2]}", parse_mode="HTML")
        await message.reply("✅ Отправлено")
    except Exception as e:
        await message.reply(f"❌ Не доставлено: {e}")

async def admin_send(message: types.Message):
    ct = message.content_type
    if ct == "text":
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ Формат: /send текст"); return
        body = message.html_text.split(maxsplit=1)[1]; plain = parts[1]
    elif ct in ("photo","video","document","animation"):
        body = plain = None
    else:
        await message.reply("❌ Текст, фото, видео, документ, гифка."); return
    with db() as conn:
        users = [r["user_id"] for r in conn.execute("SELECT user_id FROM users WHERE blocked=0 AND banned=0").fetchall()]
    total = len(users)
    if not total:
        await message.reply("❌ Нет получателей."); return
    status = await message.reply(f"🚀 Рассылка: 0 / {total}")
    ok = fail = blocked = 0
    for i, uid in enumerate(users, 1):
        try:
            if ct == "text":
                try: await bot.send_message(uid, body, parse_mode="HTML")
                except TelegramBadRequest: await bot.send_message(uid, plain)
            else:
                await message.send_copy(chat_id=uid)
            ok += 1
        except TelegramForbiddenError:
            blocked += 1
            with db() as conn: conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after+1)
            try:
                if ct == "text": await bot.send_message(uid, plain)
                else: await message.send_copy(chat_id=uid)
                ok += 1
            except Exception: fail += 1
        except Exception: fail += 1
        if i % 25 == 0:
            try: await status.edit_text(f"🚀 Рассылка: {i} / {total}\n✅ {ok} · ❌ {fail}")
            except Exception: pass
        await asyncio.sleep(0.05)
    with db() as conn: act(conn, message.from_user.id, "admin", f"сделал рассылку на {total} человек")
    await status.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n<blockquote>Получателей: {total}\nДоставлено: {ok}\n"
        f"Заблокировали бота: {blocked}\nОшибок: {fail}</blockquote>", parse_mode="HTML")

async def admin_news(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Формат: /news текст"); return
    text = f"📰 <b>НОВОСТИ БОТА</b>\n\n{parts[1]}\n\nОткрыть бота — /start"
    status = await message.reply("🚀 Разношу новость...")
    ok, fail, blocked = await broadcast_text(text)
    with db() as conn: act(conn, message.from_user.id, "admin", f"разослал новость ({ok} доставлено)")
    await status.edit_text(f"✅ Новость разослана\n\nДоставлено: {ok}\nОшибок: {fail}\nБлок: {blocked}")

async def admin_mkpromo(message: types.Message):
    args = message.text.split()
    if len(args) < 4:
        await message.reply("Формат: /mkpromo CODE SUM LIMIT [stars|tokens|pass]\nПример: /mkpromo NEWYEAR 50 100"); return
    code = args[1].upper(); cur = CUR.get(args[4].lower()) if len(args) > 4 else "stars"
    if not cur:
        await message.reply("❌ Тип: stars / tokens / pass"); return
    if not args[2].isdigit() or not args[3].isdigit():
        await message.reply("❌ SUM и LIMIT — числа"); return
    per, total = int(args[2]), int(args[3])
    if per < 1 or total < 1 or per > 1_000_000 or total > 1_000_000:
        await message.reply("❌ SUM и LIMIT от 1 до 1 000 000"); return
    with db() as conn:
        if conn.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone():
            await message.reply("❌ Такой код уже есть"); return
        conn.execute("INSERT INTO codes(code,kind,currency,per,extra,total,used,active,created_at) VALUES(?,?,?,?,?, ?,0,1,?)",
                     (code, "promo", cur, per, 0, total, time.time()))
        act(conn, message.from_user.id, "admin", f"создал промокод {code}: {per}{CUR_ICON[cur]} × {total}")
    news = (f"🎁 <b>ВЫШЕЛ НОВЫЙ ПРОМОКОД!</b>\n\n"
            f"<blockquote>Код: <code>{code}</code>\nНаграда: +{per}{CUR_ICON[cur]}\n"
            f"Активаций всего: {total}</blockquote>\n\n"
            f"Успей забрать, пока не разобрали!\nАктивировать: <code>/code {code}</code>")
    status = await message.reply("✅ Промокод создан. Разношу новость...")
    ok, fail, blocked = await broadcast_text(news)
    await status.edit_text(f"✅ <b>Промокод {code} создан</b>\n\nНаграда: +{per}{CUR_ICON[cur]}\nАктиваций: {total}\n\n"
                           f"Новость доставлена: {ok}\nОшибок: {fail}\nБлок: {blocked}", parse_mode="HTML")

async def admin_mkcheck(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Формат: /mkcheck SUM COUNT [stars|tokens|pass]\nПример: /mkcheck 500 10"); return
    cur = CUR.get(args[3].lower()) if len(args) > 3 else "stars"
    if not cur:
        await message.reply("❌ Тип: stars / tokens / pass"); return
    if not args[1].isdigit() or not args[2].isdigit():
        await message.reply("❌ SUM и COUNT — числа"); return
    total_sum, count = int(args[1]), int(args[2])
    if total_sum < 1 or count < 1 or total_sum > 10_000_000 or count > 100_000:
        await message.reply("❌ SUM 1–10 000 000, COUNT 1–100 000"); return
    if total_sum < count:
        await message.reply("❌ Сумма должна быть не меньше числа активаций"); return
    per, extra = divmod(total_sum, count)
    code = gen_code()
    with db() as conn:
        while conn.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone():
            code = gen_code()
        conn.execute("INSERT INTO codes(code,kind,currency,per,extra,total,used,active,created_at) VALUES(?,?,?,?,?,?,0,1,?)",
                     (code, "check", cur, per, extra, count, time.time()))
        act(conn, message.from_user.id, "admin", f"создал чек {code}: {total_sum}{CUR_ICON[cur]} на {count} человек")
    news = (f"💸 <b>ВЫШЕЛ НОВЫЙ ЧЕК!</b>\n\n"
            f"<blockquote>Код: <code>{code}</code>\nОбщая сумма: {total_sum}{CUR_ICON[cur]}\n"
            f"На первых: {count} игроков\nКаждому примерно: {per}{CUR_ICON[cur]}</blockquote>\n\n"
            f"Кто успел — тот и забрал!\nАктивировать: <code>/code {code}</code>")
    status = await message.reply("✅ Чек создан. Разношу новость...")
    ok, fail, blocked = await broadcast_text(news)
    await status.edit_text(f"✅ <b>Чек {code} создан</b>\n\nСумма: {total_sum}{CUR_ICON[cur]}\n"
                           f"Активаций: {count}\nКаждому: ~{per}{CUR_ICON[cur]}\n\n"
                           f"Новость доставлена: {ok}\nОшибок: {fail}\nБлок: {blocked}", parse_mode="HTML")

async def admin_codes(message: types.Message):
    with db() as conn:
        rows = conn.execute("SELECT * FROM codes ORDER BY created_at DESC LIMIT 20").fetchall()
    if not rows:
        await message.answer("Кодов пока нет."); return
    lines = []
    for r in rows:
        status = "🟢" if r["active"] and r["used"] < r["total"] else "🔴"
        kind = "промо" if r["kind"] == "promo" else "чек"
        lines.append(f"{status} {r['code']} · {kind} · {r['per']}{CUR_ICON[r['currency']]} · {r['used']}/{r['total']}")
    await message.answer("🎁 <b>КОДЫ</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
                         "/mkpromo CODE SUM LIMIT · /mkcheck SUM COUNT · /delcode CODE", parse_mode="HTML")

async def admin_delcode(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Формат: /delcode CODE"); return
    code = args[1].upper()
    with db() as conn:
        r = conn.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone()
        if not r:
            await message.reply("❌ Нет такого кода"); return
        conn.execute("UPDATE codes SET active=0 WHERE code=?", (code,))
        act(conn, message.from_user.id, "admin", f"закрыл код {code}")
    await message.reply(f"🔴 Код {code} закрыт")

def _adm(msg): return msg.from_user and msg.from_user.id in ADMINS

# ═══════════ РЕГИСТРАЦИЯ ═══════════
dp.message.register(do_start, Command("start"))
dp.message.register(do_help, Command("help","commands"))
dp.message.register(do_profile, Command("profile"))
dp.message.register(do_bonus, Command("bonus"))
dp.message.register(do_collect, Command("collect"))
dp.message.register(do_farm, Command("farm","biz"))
dp.message.register(do_buy, Command("buy"))
dp.message.register(do_market, Command("market","shop"))
dp.message.register(do_gbuy, Command("gbuy"))
dp.message.register(do_gsell, Command("gsell"))
dp.message.register(do_upgrade, Command("up","upgrade"))
dp.message.register(do_exchange, Command("exchange","swap"))
dp.message.register(do_case, Command("case"))
dp.message.register(do_ice, Command("ice"))
dp.message.register(do_top, Command("top"))
dp.message.register(do_ref, Command("ref"))
dp.message.register(do_reftop, Command("reftop"))
dp.message.register(do_pass, Command("pass"))
dp.message.register(do_passlist, Command("passlist"))
dp.message.register(do_passtop, Command("passtop"))
dp.message.register(do_passevents, Command("passevents"))
dp.message.register(do_passhall, Command("passhall"))
dp.message.register(do_claim, Command("code","promo","check","get"))
dp.message.register(public_feed, Command("feed"))

dp.message.register(do_bonus, F.text == B_BONUS)
dp.message.register(do_profile, F.text == B_PROF)
dp.message.register(do_top, F.text == B_TOP)
dp.message.register(do_farm, F.text == B_FARM)
dp.message.register(do_collect, F.text == B_COLL)
dp.message.register(do_market, F.text == B_MARKET)
dp.message.register(do_upgrade, F.text == B_UP)
dp.message.register(do_case, F.text == B_CASE)
dp.message.register(do_ice, F.text == B_ICE)
dp.message.register(do_exchange, F.text == B_EXCH)
dp.message.register(do_ref, F.text == B_REF)
dp.message.register(do_help, F.text == B_HELP)
dp.message.register(do_pass, F.text == B_PASS)
dp.message.register(do_passtop, F.text == B_PTOPY)
dp.message.register(public_feed, F.text == B_FEED)
dp.message.register(do_code_help, F.text == B_CODE)

dp.message.register(admin_panel, Command("admin"), _adm)
dp.message.register(admin_online, Command("online"), _adm)
dp.message.register(admin_stats, Command("stats"), _adm)
dp.message.register(admin_give, Command("give"), _adm)
dp.message.register(admin_take, Command("take"), _adm)
dp.message.register(admin_user, Command("user"), _adm)
dp.message.register(admin_ban, Command("ban"), _adm)
dp.message.register(admin_unban, Command("unban"), _adm)
dp.message.register(admin_log, Command("log"), _adm)
dp.message.register(admin_watch, Command("watch"), _adm)
dp.message.register(admin_say, Command("say"), _adm)
dp.message.register(admin_send, Command("send"), _adm)
dp.message.register(admin_news, Command("news"), _adm)
dp.message.register(admin_mkpromo, Command("mkpromo"), _adm)
dp.message.register(admin_mkcheck, Command("mkcheck"), _adm)
dp.message.register(admin_codes, Command("codes"), _adm)
dp.message.register(admin_delcode, Command("delcode"), _adm)

@dp.message(F.text)
async def fallback(message: types.Message, state: FSMContext):
    await message.answer("🤔 <b>Не понял команду</b>\n\nНажми кнопку внизу или открой /help",
                         reply_markup=MAIN_KB, parse_mode="HTML")

async def main():
    global BOT_USERNAME
    init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    asyncio.create_task(watch_loop())
    print(f"🚀 Бот @{BOT_USERNAME} запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
