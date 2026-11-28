import asyncio, random, sqlite3, os, time, contextlib
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ═══════════════════════════════════════════════════════════
# 👇 ВСТАВЬ СВОЙ ТОКЕН МЕЖДУ КАВЫЧКАМИ (замени ВСТАВЬ_ТОКЕН)
BOT_TOKEN = "9088817673:AAHNHqhYHJH4g9N6y9BwDL4O5H936RF6n_g"

# 👇 ТВОЙ TELEGRAM ID (узнать: @userinfobot)
ADMIN_ID = 8907438590
# ═══════════════════════════════════════════════════════════

if BOT_TOKEN == "ВСТАВЬ_ТОКЕН" or ":" not in BOT_TOKEN:
    raise SystemExit(
        "\n❌ Токен не вставлен!\n"
        "Открой файл, найди строку BOT_TOKEN вверху и вставь токен от @BotFather.\n"
        'Пример: BOT_TOKEN = "8123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxx"\n'
    )

DB_PATH = "bot.db"
CAP_HOURS = 12              # сколько часов копится доход фермы
GIFT_CAP_HOURS = 12         # сколько часов копятся подарки
MAX_BIZ_LEVEL = 10
BONUS_COOLDOWN = 12 * 60 * 60
TOKEN_RATE = 3              # 1 токен = 3 звезды
GIFT_SELL_PART = 0.7        # продажа подарка = 70% цены
UP_MIN, UP_MAX = 1, 1000    # лимиты ставки в апгрейде
BOT_USERNAME = ""

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class St(StatesGroup):
    playing_ice = State()

# --- FLASK ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ---
@contextlib.contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            last_daily REAL DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            gift_bank REAL DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS business (
            user_id INTEGER, biz_id INTEGER,
            level INTEGER DEFAULT 0, last_collect REAL DEFAULT 0,
            PRIMARY KEY (user_id, biz_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS gifts (
            user_id INTEGER, gift_id INTEGER,
            qty INTEGER DEFAULT 0, last_collect REAL DEFAULT 0,
            PRIMARY KEY (user_id, gift_id)
        )''')
        for col, ddl in [
            ("tokens", "INTEGER DEFAULT 0"),
            ("last_daily", "REAL DEFAULT 0"),
            ("referrer_id", "INTEGER DEFAULT 0"),
            ("level", "INTEGER DEFAULT 1"),
            ("xp", "INTEGER DEFAULT 0"),
            ("gift_bank", "REAL DEFAULT 0"),
        ]:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass

def ensure_user(conn, uid, un=None, fn=None):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (uid, un, fn))
    elif un is not None or fn is not None:
        c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (un, fn, uid))
    c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    return c.fetchone()

def needed_xp(level):
    return 200 * level

def _add_xp(conn, uid, amount):
    c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone()
    level, xp, gained = r["level"], r["xp"] + amount, 0
    while level < 20 and xp >= needed_xp(level):
        xp -= needed_xp(level)
        level += 1
        gained += 1
    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ?", (level, xp, uid))
    return gained

def add_coins(conn, uid, amount):
    conn.execute("UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?", (amount, uid))
    return _add_xp(conn, uid, amount) if amount > 0 else 0

def add_tokens(conn, uid, amount):
    conn.execute("UPDATE users SET tokens = MAX(0, tokens + ?) WHERE user_id = ?", (amount, uid))

def get_balance(conn, uid):
    return conn.execute("SELECT coins FROM users WHERE user_id = ?", (uid,)).fetchone()["coins"]

def fmt_hours(h):
    return f"{int(h * 60)} мин" if h < 1 else f"{int(h)} ч {int((h % 1) * 60)} мин"

# --- ФЕРМА ---
BUSINESSES = {
    1: {"name": "🍋 Лимонадный ларёк", "price": 50,    "income": 2},
    2: {"name": "☕ Кофейня",           "price": 200,   "income": 7},
    3: {"name": "🍕 Пиццерия",          "price": 700,   "income": 22},
    4: {"name": "🏭 Фабрика",           "price": 2500,  "income": 70},
    5: {"name": "🚀 IT-стартап",        "price": 10000, "income": 260},
}

def biz_rate(bid, lvl): return BUSINESSES[bid]["income"] * lvl
def biz_cost(bid, lvl): return int(BUSINESSES[bid]["price"] * (1.4 ** lvl))

def get_biz_rows(conn, uid):
    rows = conn.execute("SELECT biz_id, level, last_collect FROM business WHERE user_id = ?", (uid,)).fetchall()
    owned = {r["biz_id"]: dict(r) for r in rows}
    return {b: owned.get(b, {"biz_id": b, "level": 0, "last_collect": 0.0}) for b in BUSINESSES}

def biz_pending(bid, lvl, last):
    if lvl <= 0 or last <= 0: return 0, 0.0
    elapsed = max(0.0, (time.time() - last) / 3600)
    capped = min(elapsed, CAP_HOURS)
    return int(biz_rate(bid, lvl) * capped), capped

def collect_one(conn, uid, bid, row):
    lvl, last = row["level"], row["last_collect"]
    if lvl <= 0: return 0
    amount, _ = biz_pending(bid, lvl, last)
    now = time.time()
    elapsed = max(0.0, (now - last) / 3600)
    rate = biz_rate(bid, lvl)
    new_last = now if elapsed >= CAP_HOURS else last + (amount / rate) * 3600
    conn.execute("UPDATE business SET last_collect = ? WHERE user_id = ? AND biz_id = ?", (new_last, uid, bid))
    if amount > 0: add_coins(conn, uid, amount)
    return amount

def collect_all_biz(conn, uid):
    return sum(collect_one(conn, uid, b, r) for b, r in get_biz_rows(conn, uid).items())

def total_biz_rate(conn, uid):
    return sum(biz_rate(b, r["level"]) for b, r in get_biz_rows(conn, uid).items())

# --- ПОДАРКИ ---
GIFTS = {
    1: {"emoji": "🍾", "name": "Шампанское", "price": 50, "bonus": 1.5, "period": 2.0},
    2: {"emoji": "🎁", "name": "Подарок",     "price": 25, "bonus": 0.9, "period": 1.5},
    3: {"emoji": "❤️", "name": "Сердечко",    "price": 15, "bonus": 0.5, "period": 1.8},
}

def gift_rate(gid, qty):
    g = GIFTS[gid]
    return g["bonus"] / g["period"] * qty      # звёзд в час

def gift_sell_price(gid):
    return int(GIFTS[gid]["price"] * GIFT_SELL_PART)

def get_gift_rows(conn, uid):
    rows = conn.execute("SELECT gift_id, qty, last_collect FROM gifts WHERE user_id = ?", (uid,)).fetchall()
    owned = {r["gift_id"]: dict(r) for r in rows}
    return {g: owned.get(g, {"gift_id": g, "qty": 0, "last_collect": 0.0}) for g in GIFTS}

def gift_pending(gid, qty, last):
    if qty <= 0 or last <= 0: return 0.0, 0.0
    elapsed = max(0.0, (time.time() - last) / 3600)
    capped = min(elapsed, GIFT_CAP_HOURS)
    return gift_rate(gid, qty) * capped, capped

def bank_add(conn, uid, amount):
    if amount > 0:
        conn.execute("UPDATE users SET gift_bank = gift_bank + ? WHERE user_id = ?", (amount, uid))

def bank_payout(conn, uid):
    bank = conn.execute("SELECT gift_bank FROM users WHERE user_id = ?", (uid,)).fetchone()["gift_bank"]
    payout = int(bank)
    if payout > 0:
        conn.execute("UPDATE users SET gift_bank = gift_bank - ? WHERE user_id = ?", (payout, uid))
        add_coins(conn, uid, payout)
    return payout

def settle_gift(conn, uid, gid, row):
    """Начисляет накопленное в копилку дробей и сдвигает таймер."""
    if row["qty"] <= 0: return 0.0
    earned, capped = gift_pending(gid, row["qty"], row["last_collect"])
    bank_add(conn, uid, earned)
    conn.execute("UPDATE gifts SET last_collect = ? WHERE user_id = ? AND gift_id = ?",
                 (time.time(), uid, gid))
    return earned

def total_gift_rate(conn, uid):
    return sum(gift_rate(g, r["qty"]) for g, r in get_gift_rows(conn, uid).items())

def collect_everything(conn, uid):
    biz = collect_all_biz(conn, uid)
    for gid, row in get_gift_rows(conn, uid).items():
        settle_gift(conn, uid, gid, row)
    gifts = bank_payout(conn, uid)
    return biz, gifts

# --- АПГРЕЙД ---
UPGRADE_TIERS = [
    (1.2, 0.80), (1.4, 0.68), (1.6, 0.58), (1.8, 0.50),
    (2.0, 0.45), (3.0, 0.28), (5.0, 0.16), (10.0, 0.07),
]

def parse_mult(raw):
    s = raw.lower().replace(",", ".").replace("x", "").replace("х", "").strip()
    try:
        val = float(s)
    except ValueError:
        return None
    for mult, chance in UPGRADE_TIERS:
        if abs(mult - val) < 0.001:
            return mult, chance
    return None

# --- ЛЬДИНЫ ---
ICE_DIFFICULTIES = {
    "easy":    {"name": "🟢 Легко",   "mult": 0.5, "rate": 0.80},
    "medium":  {"name": "🟡 Средне",  "mult": 1.0, "rate": 0.60},
    "hard":    {"name": "🔴 Сложно",  "mult": 2.0, "rate": 0.40},
    "extreme": {"name": "💀 Экстрим", "mult": 3.0, "rate": 0.25},
    "madness": {"name": "🤯 Безумие", "mult": 5.0, "rate": 0.10},
}

# --- КНОПКИ ---
B_BONUS, B_PROF, B_TOP = "🎁 Бонус", "👤 Профиль", "🏆 Топ"
B_FARM, B_COLL, B_MARKET = "🏭 Ферма", "💰 Собрать", "🛍 Маркет"
B_UP, B_CASE, B_ICE = "⚡ Апгрейд", "📦 Кейс", "🧊 Льдины"
B_EXCH, B_REF, B_HELP = "💱 Обмен", "👥 Реферал", "❓ Помощь"

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text=B_BONUS), KeyboardButton(text=B_PROF),   KeyboardButton(text=B_TOP)],
    [KeyboardButton(text=B_FARM),  KeyboardButton(text=B_COLL),   KeyboardButton(text=B_MARKET)],
    [KeyboardButton(text=B_UP),    KeyboardButton(text=B_CASE),   KeyboardButton(text=B_ICE)],
    [KeyboardButton(text=B_EXCH),  KeyboardButton(text=B_REF),    KeyboardButton(text=B_HELP)],
], resize_keyboard=True, input_field_placeholder="Выбери действие или введи команду")

INSTRUCTIONS = (
    "📖 <b>КАК ИГРАТЬ</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "<b>1️⃣ Зарабатывай звёзды</b>\n"
    "/bonus — бесплатные 5–20⭐ раз в 12ч\n"
    "/case — кейс за 5⭐ (можно выиграть 18⭐)\n"
    "/ref — пригласи друга, получи +5⭐\n\n"
    "<b>2️⃣ Строй пассивный доход</b>\n"
    "/farm — купить бизнес, он капает звёзды сам\n"
    "/buy N — купить или улучшить бизнес\n"
    "/market — подарки, они тоже дают доход\n"
    "/gbuy N — купить подарок\n"
    "/gsell N — продать подарок (70% цены)\n"
    "/collect — <b>собрать всё накопленное</b>\n"
    "⏱ Доход копится max 12ч, потом стоп — заходи чаще\n\n"
    "<b>3️⃣ Рискуй и умножай</b>\n"
    "/up — апгрейд: умножь звёзды до x10\n"
    "/ice — льдины: прыгай и копи приз\n\n"
    "<b>4️⃣ Прочее</b>\n"
    "/exchange — токены → звёзды (1 = 3⭐)\n"
    "/profile — уровень, баланс, доход\n"
    "/top — таблица лидеров\n"
    "/help — эта инструкция\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💡 <b>Совет:</b> начни с /bonus, потом купи\n"
    "самый дешёвый бизнес или ❤️ сердечко —\n"
    "и звёзды пойдут сами, даже когда ты офлайн."
)

# ═══════════════ ОСНОВНОЕ ═══════════════

async def do_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: ref_id = int(args[1][4:])
        except ValueError: pass

    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        if ref_id and ref_id != message.from_user.id:
            c = conn.cursor()
            c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (message.from_user.id,))
            if c.fetchone()["referrer_id"] == 0 and c.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (ref_id,)).fetchone():
                c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref_id, message.from_user.id))
                add_coins(conn, ref_id, 5)
                add_coins(conn, message.from_user.id, 5)
                try:
                    await bot.send_message(ref_id,
                        f"🎉 <b>Новый реферал!</b>\n{message.from_user.first_name} пришёл по твоей ссылке.\n⭐️ +5 на баланс!",
                        parse_mode="HTML")
                except Exception:
                    pass

    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n"
        f"Это бот-копилка: собирай звёзды, строй ферму и умножай баланс.\n\n" + INSTRUCTIONS,
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(INSTRUCTIONS, reply_markup=MAIN_KB, parse_mode="HTML")

async def do_profile(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        u = ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        br = total_biz_rate(conn, message.from_user.id)
        gr = total_gift_rate(conn, message.from_user.id)
        refs = conn.execute("SELECT COUNT(*) AS n FROM users WHERE referrer_id = ?",
                            (message.from_user.id,)).fetchone()["n"]
        gifts_n = conn.execute("SELECT COALESCE(SUM(qty),0) AS n FROM gifts WHERE user_id = ?",
                               (message.from_user.id,)).fetchone()["n"]
    lvl, xp = u["level"], u["xp"]
    need = needed_xp(lvl) if lvl < 20 else 0
    filled = min(10, int(xp / need * 10)) if need else 10
    bar = "█" * filled + "░" * (10 - filled)
    await message.answer(
        f"👤 <b>ПРОФИЛЬ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 <b>Уровень:</b> {lvl}/20\n"
        f"[{bar}] {xp}/{need if need else 'MAX'}\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ <b>Звёзды:</b> {u['coins']}\n"
        f"🪙 <b>Токены:</b> {u['tokens']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏭 Бизнес: {br}⭐/ч\n"
        f"🎁 Подарки: {gr:.2f}⭐/ч ({gifts_n} шт)\n"
        f"📈 <b>Всего: {br + gr:.2f}⭐/ч</b>\n"
        f"🏦 Копилка дробей: {u['gift_bank']:.2f}\n"
        f"👥 Рефералов: {refs}\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_bonus(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        u = ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        left = BONUS_COOLDOWN - (time.time() - (u["last_daily"] or 0))
        if left > 0:
            await message.answer(f"⏳ Бонус через {fmt_hours(left / 3600)}", reply_markup=MAIN_KB)
            return
        reward = random.randint(5, 20)
        gained = add_coins(conn, message.from_user.id, reward)
        conn.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (time.time(), message.from_user.id))
        bal = get_balance(conn, message.from_user.id)
    txt = f"🎉 <b>БОНУС ПОЛУЧЕН</b>\n⭐️ +{reward}\n💰 Баланс: {bal}"
    if gained: txt += "\n\n📊 <b>Новый уровень!</b>"
    await message.answer(txt, reply_markup=MAIN_KB, parse_mode="HTML")

async def do_collect(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        biz, gifts = collect_everything(conn, message.from_user.id)
        bal = get_balance(conn, message.from_user.id)
        rate = total_biz_rate(conn, message.from_user.id) + total_gift_rate(conn, message.from_user.id)
        bank = conn.execute("SELECT gift_bank FROM users WHERE user_id = ?",
                            (message.from_user.id,)).fetchone()["gift_bank"]
    if biz + gifts <= 0:
        msg = "🏭 У тебя нет источников дохода. Загляни в /farm и /market" if rate <= 0 else "⏳ Пока пусто, доход ещё копится."
        await message.answer(msg, reply_markup=MAIN_KB)
        return
    await message.answer(
        f"💰 <b>ДОХОД СОБРАН</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏭 Бизнес: +{biz}⭐\n"
        f"🎁 Подарки: +{gifts}⭐\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ Итого: <b>+{biz + gifts}</b>\n"
        f"💳 Баланс: {bal}\n"
        f"🏦 Остаток в копилке: {bank:.2f}\n"
        f"📈 Дальше: {rate:.2f}⭐/ч\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ ФЕРМА ═══════════════

async def do_farm(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        rows = get_biz_rows(conn, message.from_user.id)
        bal = get_balance(conn, message.from_user.id)
    pend_total = rate_total = 0
    lines = []
    for bid, biz in BUSINESSES.items():
        r = rows[bid]; lvl = r["level"]
        if lvl == 0:
            lines.append(f"<b>{bid}. {biz['name']}</b> — не куплен\n"
                         f"   💵 {biz_cost(bid, 0)}⭐ | 📈 {biz['income']}⭐/ч\n"
                         f"   👉 /buy {bid}\n")
        else:
            pend, hours = biz_pending(bid, lvl, r["last_collect"])
            pend_total += pend
            rate = biz_rate(bid, lvl); rate_total += rate
            full = " ⚠️ ПОЛНОЕ" if hours >= CAP_HOURS else ""
            block = (f"<b>{bid}. {biz['name']}</b> — ур. {lvl}/{MAX_BIZ_LEVEL}\n"
                     f"   📈 {rate}⭐/ч | 💵 {pend}⭐ готово{full}\n")
            block += (f"   ⬆️ Ур. {lvl+1}: {biz_cost(bid, lvl)}⭐ → /buy {bid}\n"
                      if lvl < MAX_BIZ_LEVEL else "   🔝 Максимальный уровень\n")
            lines.append(block)
    await message.answer(
        f"🏭 <b>ТВОЯ ФЕРМА</b>\n━━━━━━━━━━━━━━\n"
        f"⭐️ Баланс: <b>{bal}</b>\n"
        f"📈 Доход: <b>{rate_total}⭐/ч</b>\n"
        f"💵 К сбору: <b>{pend_total}⭐</b> → /collect\n"
        f"⏱ Копится max {CAP_HOURS}ч\n━━━━━━━━━━━━━━\n\n" + "\n".join(lines),
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_buy(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in BUSINESSES:
        await message.answer("❌ Формат: /buy N\nНапример: /buy 1\nСписок — /farm", reply_markup=MAIN_KB)
        return
    bid = int(args[1]); biz = BUSINESSES[bid]
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        row = get_biz_rows(conn, message.from_user.id)[bid]
        lvl = row["level"]
        if lvl >= MAX_BIZ_LEVEL:
            await message.answer(f"🔝 {biz['name']} уже максимального уровня.", reply_markup=MAIN_KB)
            return
        settled = collect_one(conn, message.from_user.id, bid, row)
        cost = biz_cost(bid, lvl)
        bal = get_balance(conn, message.from_user.id)
        if bal < cost:
            extra = f"\n(собрано по пути: +{settled}⭐)" if settled else ""
            await message.answer(f"❌ Не хватает звёзд.\nНужно {cost}⭐, у тебя {bal}⭐{extra}", reply_markup=MAIN_KB)
            return
        add_coins(conn, message.from_user.id, -cost)
        now = time.time()
        if lvl == 0:
            conn.execute("INSERT INTO business (user_id, biz_id, level, last_collect) VALUES (?, ?, 1, ?)",
                         (message.from_user.id, bid, now))
        else:
            conn.execute("UPDATE business SET level = ?, last_collect = ? WHERE user_id = ? AND biz_id = ?",
                         (lvl + 1, now, message.from_user.id, bid))
        new_bal = get_balance(conn, message.from_user.id)
        new_rate = biz_rate(bid, lvl + 1)
    action = "КУПЛЕН" if lvl == 0 else f"УЛУЧШЕН ДО УР. {lvl+1}"
    await message.answer(
        f"✅ <b>{biz['name']} {action}</b>\n━━━━━━━━━━━━━━\n"
        f"💸 Потрачено: {cost}⭐\n📈 Доход: {new_rate}⭐/ч\n💳 Баланс: {new_bal}⭐\n"
        f"━━━━━━━━━━━━━━\nСобрать: /collect",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ МАРКЕТ ПОДАРКОВ ═══════════════

async def do_market(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        rows = get_gift_rows(conn, message.from_user.id)
        bal = get_balance(conn, message.from_user.id)
        gr = total_gift_rate(conn, message.from_user.id)
    lines = []
    pend_total = 0.0
    for gid, g in GIFTS.items():
        r = rows[gid]; qty = r["qty"]
        pend, hours = gift_pending(gid, qty, r["last_collect"])
        pend_total += pend
        per_h = g["bonus"] / g["period"]
        block = (f"<b>{gid}. {g['emoji']} {g['name']}</b>\n"
                 f"   💵 Цена: {g['price']}⭐ | Продажа: {gift_sell_price(gid)}⭐\n"
                 f"   🎁 +{g['bonus']}⭐ каждые {g['period']}ч ({per_h:.2f}⭐/ч)\n")
        if qty > 0:
            full = " ⚠️ ПОЛНОЕ" if hours >= GIFT_CAP_HOURS else ""
            block += (f"   📦 У тебя: <b>{qty} шт</b> → {gift_rate(gid, qty):.2f}⭐/ч\n"
                      f"   💰 Накоплено: {pend:.2f}⭐{full}\n")
        block += f"   👉 /gbuy {gid} | /gsell {gid}\n"
        lines.append(block)
    await message.answer(
        f"🛍 <b>МАРКЕТ ПОДАРКОВ</b>\n━━━━━━━━━━━━━━\n"
        f"⭐️ Баланс: <b>{bal}</b>\n"
        f"📈 Доход подарков: <b>{gr:.2f}⭐/ч</b>\n"
        f"💵 К сбору: <b>{pend_total:.2f}⭐</b> → /collect\n"
        f"━━━━━━━━━━━━━━\n"
        f"Подарки дают звёзды сами, как бизнес.\n"
        f"Можно покупать несколько — доход складывается.\n"
        f"Продажа возвращает {int(GIFT_SELL_PART*100)}% цены.\n━━━━━━━━━━━━━━\n\n" + "\n".join(lines),
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_gbuy(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in GIFTS:
        await message.answer("❌ Формат: /gbuy N [количество]\nНапример: /gbuy 3 2\nСписок — /market", reply_markup=MAIN_KB)
        return
    gid = int(args[1]); g = GIFTS[gid]
    qty = 1
    if len(args) > 2:
        if not args[2].isdigit() or not (1 <= int(args[2]) <= 100):
            await message.answer("❌ Количество — от 1 до 100", reply_markup=MAIN_KB)
            return
        qty = int(args[2])
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        row = get_gift_rows(conn, message.from_user.id)[gid]
        settle_gift(conn, message.from_user.id, gid, row)   # фиксируем доход до покупки
        cost = g["price"] * qty
        bal = get_balance(conn, message.from_user.id)
        if bal < cost:
            await message.answer(f"❌ Не хватает звёзд.\nНужно {cost}⭐, у тебя {bal}⭐", reply_markup=MAIN_KB)
            return
        add_coins(conn, message.from_user.id, -cost)
        now = time.time()
        if row["qty"] == 0:
            conn.execute("INSERT INTO gifts (user_id, gift_id, qty, last_collect) VALUES (?, ?, ?, ?)",
                         (message.from_user.id, gid, qty, now))
        else:
            conn.execute("UPDATE gifts SET qty = qty + ?, last_collect = ? WHERE user_id = ? AND gift_id = ?",
                         (qty, now, message.from_user.id, gid))
        new_qty = row["qty"] + qty
        new_bal = get_balance(conn, message.from_user.id)
    await message.answer(
        f"✅ <b>КУПЛЕНО {g['emoji']} × {qty}</b>\n━━━━━━━━━━━━━━\n"
        f"💸 Потрачено: {cost}⭐\n"
        f"📦 Всего в наличии: {new_qty} шт\n"
        f"📈 Доход: {gift_rate(gid, new_qty):.2f}⭐/ч\n"
        f"💳 Баланс: {new_bal}⭐\n━━━━━━━━━━━━━━\nСобрать: /collect",
        reply_markup=MAIN_KB, parse_mode="HTML")

async def do_gsell(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in GIFTS:
        await message.answer("❌ Формат: /gsell N [количество]\nНапример: /gsell 3\nСписок — /market", reply_markup=MAIN_KB)
        return
    gid = int(args[1]); g = GIFTS[gid]
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        row = get_gift_rows(conn, message.from_user.id)[gid]
        if row["qty"] <= 0:
            await message.answer(f"❌ У тебя нет {g['emoji']}", reply_markup=MAIN_KB)
            return
        qty = 1
        if len(args) > 2:
            if args[2].lower() == "all":
                qty = row["qty"]
            elif args[2].isdigit() and int(args[2]) >= 1:
                qty = min(int(args[2]), row["qty"])
            else:
                await message.answer("❌ Количество — число или all", reply_markup=MAIN_KB)
                return
        settle_gift(conn, message.from_user.id, gid, row)
        earned_bank = bank_payout(conn, message.from_user.id)
        income = gift_sell_price(gid) * qty
        add_coins(conn, message.from_user.id, income)
        left = row["qty"] - qty
        conn.execute("UPDATE gifts SET qty = ?, last_collect = ? WHERE user_id = ? AND gift_id = ?",
                     (left, time.time() if left > 0 else 0, message.from_user.id, gid))
        bal = get_balance(conn, message.from_user.id)
    extra = f"\n🎁 Плюс собрано дохода: +{earned_bank}⭐" if earned_bank else ""
    await message.answer(
        f"💸 <b>ПРОДАНО {g['emoji']} × {qty}</b>\n━━━━━━━━━━━━━━\n"
        f"⭐️ Получено: +{income}⭐{extra}\n"
        f"📦 Осталось: {left} шт\n"
        f"💳 Баланс: {bal}⭐\n━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ АПГРЕЙД ═══════════════

async def do_upgrade(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()

    if len(args) < 3:
        with db() as conn:
            ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
            bal = get_balance(conn, message.from_user.id)
        lines = []
        for mult, chance in UPGRADE_TIERS:
            bar = "🟩" * int(chance * 10) + "⬜" * (10 - int(chance * 10))
            lines.append(f"<b>x{mult}</b> — {int(chance*100)}%\n   {bar}")
        await message.answer(
            f"⚡ <b>АПГРЕЙД ЗВЁЗД</b>\n━━━━━━━━━━━━━━\n"
            f"⭐️ Баланс: <b>{bal}</b>\n\n"
            f"Ставишь звёзды и выбираешь множитель.\n"
            f"Успех → получаешь ставку × множитель.\n"
            f"Провал → ставка сгорает.\n\n"
            f"<b>Шансы:</b>\n" + "\n".join(lines) +
            f"\n\n━━━━━━━━━━━━━━\n"
            f"<b>Формат:</b> /up [сумма] [множитель]\n"
            f"<b>Пример:</b> <code>/up 10 1.6</code>\n"
            f"Поставить 10⭐ на x1.6 → выигрыш 16⭐\n"
            f"Ставка от {UP_MIN} до {UP_MAX}⭐",
            reply_markup=MAIN_KB, parse_mode="HTML")
        return

    if not args[1].isdigit() or not (UP_MIN <= int(args[1]) <= UP_MAX):
        await message.answer(f"❌ Сумма — целое от {UP_MIN} до {UP_MAX}", reply_markup=MAIN_KB)
        return
    amount = int(args[1])
    tier = parse_mult(args[2])
    if tier is None:
        avail = ", ".join(f"x{m}" for m, _ in UPGRADE_TIERS)
        await message.answer(f"❌ Нет такого множителя.\nДоступно: {avail}", reply_markup=MAIN_KB)
        return
    mult, chance = tier

    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        if get_balance(conn, message.from_user.id) < amount:
            await message.answer(f"❌ Не хватает звёзд. Нужно {amount}⭐", reply_markup=MAIN_KB)
            return
        add_coins(conn, message.from_user.id, -amount)

    anim = await message.answer(
        f"⚡ <b>АПГРЕЙД</b>\n━━━━━━━━━━━━━━\n"
        f"Ставка: {amount}⭐ → x{mult}\nШанс: {int(chance*100)}%\n\n🔄 Крутим...")
    for frame in ["⚙️ Обработка...", "✨ Почти...", "🎲 Результат..."]:
        await asyncio.sleep(0.55)
        try:
            await anim.edit_text(
                f"⚡ <b>АПГРЕЙД</b>\n━━━━━━━━━━━━━━\n"
                f"Ставка: {amount}⭐ → x{mult}\nШанс: {int(chance*100)}%\n\n{frame}")
        except Exception:
            pass

    win = random.random() < chance
    payout = int(amount * mult) if win else 0
    with db() as conn:
        gained = add_coins(conn, message.from_user.id, payout) if win else 0
        bal = get_balance(conn, message.from_user.id)

    if win:
        profit = payout - amount
        head = "✅ <b>УСПЕХ!</b>"
        body = (f"⭐️ Получено: <b>{payout}⭐</b>\n"
                f"📈 Чистая прибыль: <b>+{profit}⭐</b>")
    else:
        head = "💥 <b>ПРОВАЛ</b>"
        body = f"💸 Ставка <b>{amount}⭐</b> сгорела."
    lvl_up = "\n📊 <b>Новый уровень!</b>" if gained else ""

    await anim.edit_text(
        f"{head}\n━━━━━━━━━━━━━━\n"
        f"Ставка: {amount}⭐ | x{mult} ({int(chance*100)}%)\n"
        f"{body}\n💳 Баланс: {bal}⭐{lvl_up}\n━━━━━━━━━━━━━━\n"
        f"Ещё раз: /up {amount} {mult}\nВсе множители: /up",
        parse_mode="HTML")

# ═══════════════ ОБМЕН ТОКЕНОВ ═══════════════

async def do_exchange(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    uid = message.from_user.id

    if len(args) < 2:
        with db() as conn:
            u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        await message.answer(
            f"💱 <b>ОБМЕН ТОКЕНОВ</b>\n━━━━━━━━━━━━━━\n"
            f"🪙 Токены: <b>{u['tokens']}</b>\n"
            f"⭐️ Звёзды: <b>{u['coins']}</b>\n\n"
            f"Курс: <b>1 токен = {TOKEN_RATE}⭐</b>\n"
            f"Обмен доступен: <b>{u['tokens'] * TOKEN_RATE}⭐</b>\n━━━━━━━━━━━━━━\n"
            f"<b>Формат:</b> /exchange [кол-во]\n"
            f"<b>Пример:</b> <code>/exchange 2</code> → +6⭐\n"
            f"Обменять всё: <code>/exchange all</code>\n\n"
            f"💡 Токены падают из кейса /case",
            reply_markup=MAIN_KB, parse_mode="HTML")
        return

    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        have = u["tokens"]
        if have <= 0:
            await message.answer("❌ У тебя нет токенов. Получи их в /case", reply_markup=MAIN_KB)
            return
        if args[1].lower() == "all":
            count = have
        elif args[1].isdigit() and int(args[1]) >= 1:
            count = int(args[1])
        else:
            await message.answer("❌ Укажи число или all", reply_markup=MAIN_KB)
            return
        if count > have:
            await message.answer(f"❌ У тебя только {have} токенов", reply_markup=MAIN_KB)
            return
        stars = count * TOKEN_RATE
        add_tokens(conn, uid, -count)
        gained = add_coins(conn, uid, stars)
        bal = get_balance(conn, uid)
        left = have - count
    lvl_up = "\n📊 <b>Новый уровень!</b>" if gained else ""
    await message.answer(
        f"💱 <b>ОБМЕН ВЫПОЛНЕН</b>\n━━━━━━━━━━━━━━\n"
        f"🪙 Отдано: {count} токенов\n"
        f"⭐️ Получено: <b>+{stars}⭐</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🪙 Осталось токенов: {left}\n"
        f"💳 Баланс: {bal}⭐{lvl_up}",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ КЕЙС ═══════════════

async def do_case(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        if get_balance(conn, uid) < 5:
            await message.answer("❌ Нужно 5⭐ для кейса.", reply_markup=MAIN_KB)
            return
        add_coins(conn, uid, -5)

    anim = await message.answer("📦 Открываем кейс...")
    for frame in ["🎰 Крутим...", "✨ Ещё чуть-чуть...", "🎁 Открываем!"]:
        await asyncio.sleep(0.6)
        try: await anim.edit_text(frame)
        except Exception: pass

    items = [
        ("⭐️ +18 Звёзд", 5.8,  "coins",  18),
        ("⭐️ +11 Звёзд", 9.8,  "coins",  11),
        ("⭐️ +6 Звёзд",  11.3, "coins",  6),
        ("🪙 2 Токена",   34.7, "tokens", 2),
        ("😔 Пусто",      38.4, "none",   0),
    ]
    roll, acc, prize = random.uniform(0, 100), 0, items[-1]
    for it in items:
        acc += it[1]
        if roll <= acc:
            prize = it
            break
    with db() as conn:
        if prize[2] == "coins": add_coins(conn, uid, prize[3])
        elif prize[2] == "tokens": add_tokens(conn, uid, prize[3])
        bal = get_balance(conn, uid)
        tok = conn.execute("SELECT tokens FROM users WHERE user_id = ?", (uid,)).fetchone()["tokens"]
    extra = f"\n🪙 Токенов: {tok} → /exchange" if prize[2] == "tokens" else ""
    await anim.edit_text(
        f"🎰 <b>РЕЗУЛЬТАТ</b>\n━━━━━━━━━━━━━━\n"
        f"Выпало: <b>{prize[0]}</b>\n💳 Баланс: {bal}⭐{extra}\n"
        f"━━━━━━━━━━━━━━\nЕщё раз: /case",
        parse_mode="HTML")

# ═══════════════ ТОП / РЕФ ═══════════════

async def do_top(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        top = conn.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 10").fetchall()
    if not top:
        await message.answer("Пока нет игроков.", reply_markup=MAIN_KB)
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, r in enumerate(top, 1):
        m = medals[i-1] if i <= 3 else f"{i}."
        name = f"@{r['username']}" if r["username"] else (r["first_name"] or "Игрок")
        lines.append(f"{m} {name} — <b>{r['coins']}⭐</b>")
    await message.answer("🏆 <b>ТОП ПО ЗВЁЗДАМ</b>\n━━━━━━━━━━━━━━\n" + "\n".join(lines),
                         reply_markup=MAIN_KB, parse_mode="HTML")

async def do_ref(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        n = conn.execute("SELECT COUNT(*) AS n FROM users WHERE referrer_id = ?",
                         (message.from_user.id,)).fetchone()["n"]
    await message.answer(
        f"👥 <b>ПРИГЛАСИ ДРУГА</b>\n━━━━━━━━━━━━━━\n"
        f"<code>https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}</code>\n\n"
        f"⭐️ Тебе +5, другу +5\n👤 Приглашено: {n}\n━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ ЛЬДИНЫ ═══════════════

async def do_ice(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2:
        await state.clear()
        with db() as conn:
            ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
            bal = get_balance(conn, message.from_user.id)
        lines = [f"/ice {k} — {v['name']} (x{v['mult']}, {int(v['rate']*100)}%)"
                 for k, v in ICE_DIFFICULTIES.items()]
        await message.answer(
            f"🧊 <b>ЛЬДИНЫ</b>\n━━━━━━━━━━━━━━\n⭐️ Баланс: {bal}\n\n" + "\n".join(lines) +
            f"\n\n<b>Формат:</b> /ice [сложность] [ставка 1-10]\n<b>Пример:</b> <code>/ice extreme 5</code>",
            reply_markup=MAIN_KB, parse_mode="HTML")
        return

    await state.clear()
    diff = args[1].lower()
    if diff not in ICE_DIFFICULTIES:
        await message.answer(f"❌ Нет такой сложности. Доступно: {', '.join(ICE_DIFFICULTIES)}", reply_markup=MAIN_KB)
        return
    bet = 1
    if len(args) > 2:
        if not args[2].isdigit() or not (1 <= int(args[2]) <= 10):
            await message.answer("❌ Ставка — целое от 1 до 10", reply_markup=MAIN_KB)
            return
        bet = int(args[2])
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        if get_balance(conn, message.from_user.id) < bet:
            await message.answer(f"❌ Нужно {bet}⭐", reply_markup=MAIN_KB)
            return
        add_coins(conn, message.from_user.id, -bet)
    await state.update_data(difficulty=diff, bet=bet, reward=0, jumps=0)
    await state.set_state(St.playing_ice)
    d = ICE_DIFFICULTIES[diff]
    await message.answer(
        f"🧊 <b>ИГРА НАЧАЛАСЬ</b>\n━━━━━━━━━━━━━━\n"
        f"{d['name']} | ставка {bet}⭐ | шанс {int(d['rate']*100)}%\n"
        f"🎁 В призе: 0⭐\n━━━━━━━━━━━━━━\n/jump — прыгнуть\n/take — забрать приз\n/quit — сдаться",
        reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    d = ICE_DIFFICULTIES[data["difficulty"]]; bet = data["bet"]
    if random.random() < d["rate"]:
        gain = max(1, int(bet * d["mult"]))
        reward, jumps = data["reward"] + gain, data["jumps"] + 1
        await state.update_data(reward=reward, jumps=jumps)
        await message.answer(
            f"✅ <b>УСПЕХ</b>\n━━━━━━━━━━━━━━\n"
            f"💎 +{gain}⭐\n🎁 В призе: <b>{reward}⭐</b>\n🦘 Прыжков: {jumps}\n"
            f"━━━━━━━━━━━━━━\n/jump — ещё\n/take — забрать {reward}⭐\n/quit — сдаться",
            reply_markup=MAIN_KB, parse_mode="HTML")
    else:
        await state.clear()
        await message.answer(
            f"💦 <b>ПРОВАЛ</b>\n━━━━━━━━━━━━━━\nЛьдина треснула, ты в воде.\n"
            f"💸 Потеряно: {bet}⭐ (приз {data['reward']}⭐ сгорел)\n━━━━━━━━━━━━━━\nЕщё раз: /ice",
            reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("take"))
async def cmd_take(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    await state.clear()
    reward, bet, jumps = data["reward"], data["bet"], data["jumps"]
    with db() as conn:
        if reward > 0: add_coins(conn, message.from_user.id, reward)
        bal = get_balance(conn, message.from_user.id)
    profit = reward - bet
    await message.answer(
        f"🏆 <b>ПРИЗ ЗАБРАН</b>\n━━━━━━━━━━━━━━\n"
        f"🎁 Получено: {reward}⭐\n💰 Ставка: {bet}⭐\n"
        f"📈 Итог: {'+' if profit >= 0 else ''}{profit}⭐\n"
        f"🦘 Прыжков: {jumps}\n💳 Баланс: {bal}⭐\n━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML")

@dp.message(Command("quit"))
async def cmd_quit(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре.", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    await state.clear()
    await message.answer(f"🏳️ <b>СДАЛСЯ</b>\n💸 Ставка {data.get('bet', 0)}⭐ потеряна.",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# ═══════════════ РЕГИСТРАЦИЯ ═══════════════

dp.message.register(do_start,   Command("start"))
dp.message.register(do_help,    Command("help", "commands"))
dp.message.register(do_profile, Command("profile"))
dp.message.register(do_bonus,   Command("bonus"))
dp.message.register(do_collect, Command("collect"))
dp.message.register(do_farm,    Command("farm", "biz"))
dp.message.register(do_buy,     Command("buy"))
dp.message.register(do_market,  Command("market", "shop"))
dp.message.register(do_gbuy,    Command("gbuy"))
dp.message.register(do_gsell,   Command("gsell"))
dp.message.register(do_upgrade, Command("up", "upgrade"))
dp.message.register(do_exchange, Command("exchange", "swap"))
dp.message.register(do_case,    Command("case"))
dp.message.register(do_ice,     Command("ice"))
dp.message.register(do_top,     Command("top"))
dp.message.register(do_ref,     Command("ref"))

dp.message.register(do_bonus,   F.text == B_BONUS)
dp.message.register(do_profile, F.text == B_PROF)
dp.message.register(do_top,     F.text == B_TOP)
dp.message.register(do_farm,    F.text == B_FARM)
dp.message.register(do_collect, F.text == B_COLL)
dp.message.register(do_market,  F.text == B_MARKET)
dp.message.register(do_upgrade, F.text == B_UP)
dp.message.register(do_case,    F.text == B_CASE)
dp.message.register(do_ice,     F.text == B_ICE)
dp.message.register(do_exchange, F.text == B_EXCH)
dp.message.register(do_ref,     F.text == B_REF)
dp.message.register(do_help,    F.text == B_HELP)

# --- АДМИН ---
@dp.message(Command("send"), F.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message):
    ct = message.content_type
    if ct == "text":
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ /send текст")
            return
        body = parts[1]
    elif ct in ("photo", "video", "document"):
        body = message.caption or ""
    else:
        await message.reply("❌ Текст, фото, видео или документ.")
        return
    with db() as conn:
        users = [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]
    status = await message.reply(f"🚀 Рассылка: {len(users)} получателей...")
    ok = fail = 0
    for uid in users:
        try:
            if ct == "text":
                await bot.send_message(uid, body, parse_mode="HTML")
            elif ct == "photo":
                await bot.send_photo(uid, message.photo[-1].file_id, caption=body, parse_mode="HTML")
            elif ct == "video":
                await bot.send_video(uid, message.video.file_id, caption=body, parse_mode="HTML")
            else:
                await bot.send_document(uid, message.document.file_id, caption=body, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Готово\n📩 Доставлено: {ok}\n❌ Ошибок: {fail}")

@dp.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        stars = conn.execute("SELECT COALESCE(SUM(coins),0) AS s FROM users").fetchone()["s"]
        tok = conn.execute("SELECT COALESCE(SUM(tokens),0) AS s FROM users").fetchone()["s"]
        biz = conn.execute("SELECT COUNT(*) AS n FROM business WHERE level > 0").fetchone()["n"]
        gf = conn.execute("SELECT COALESCE(SUM(qty),0) AS n FROM gifts").fetchone()["n"]
        day = conn.execute("SELECT COUNT(*) AS n FROM users WHERE last_daily > ?",
                           (time.time() - 86400,)).fetchone()["n"]
    await message.answer(
        f"📊 <b>СТАТИСТИКА</b>\n👥 Всего: {n}\n🔥 Активных за 24ч: {day}\n"
        f"⭐️ Звёзд у игроков: {stars}\n🪙 Токенов: {tok}\n"
        f"🏭 Бизнесов: {biz}\n🎁 Подарков: {gf}", parse_mode="HTML")

@dp.message(F.text)
async def fallback(message: types.Message, state: FSMContext):
    await message.answer("🤔 Не понял команду.\n\nНажми ❓ Помощь или введи /help",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# --- ЗАПУСК ---
async def main():
    global BOT_USERNAME
    init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    print(f"🚀 Бот @{BOT_USERNAME} запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
