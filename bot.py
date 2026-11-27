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
BOT_TOKEN = "9088817673:AAED7ZOkUmIFSLXT-Hb0vhAbqmF_80DrYQU"

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
CAP_HOURS = 12          # сколько часов копится доход фермы
MAX_BIZ_LEVEL = 10
BONUS_COOLDOWN = 12 * 60 * 60
BOT_USERNAME = ""       # определится сам при запуске

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class St(StatesGroup):
    playing_ice = State()

# --- FLASK (для хостинга) ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ДАННЫХ ---
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
            xp INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS business (
            user_id INTEGER,
            biz_id INTEGER,
            level INTEGER DEFAULT 0,
            last_collect REAL DEFAULT 0,
            PRIMARY KEY (user_id, biz_id)
        )''')
        for col, ddl in [
            ("tokens", "INTEGER DEFAULT 0"),
            ("last_daily", "REAL DEFAULT 0"),
            ("referrer_id", "INTEGER DEFAULT 0"),
            ("level", "INTEGER DEFAULT 1"),
            ("xp", "INTEGER DEFAULT 0"),
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
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        row = c.fetchone()
    elif un is not None or fn is not None:
        c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (un, fn, uid))
        c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
        row = c.fetchone()
    return row

def needed_xp(level):
    return 200 * level

def _add_xp(conn, uid, amount):
    c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone()
    level, xp = r["level"], r["xp"] + amount
    gained = 0
    while level < 20 and xp >= needed_xp(level):
        xp -= needed_xp(level)
        level += 1
        gained += 1
    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ?", (level, xp, uid))
    return gained

def add_coins(conn, uid, amount):
    c = conn.cursor()
    c.execute("UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?", (amount, uid))
    if amount > 0:
        return _add_xp(conn, uid, amount)
    return 0

def add_tokens(conn, uid, amount):
    conn.execute("UPDATE users SET tokens = MAX(0, tokens + ?) WHERE user_id = ?", (amount, uid))

def get_balance(conn, uid):
    return conn.execute("SELECT coins FROM users WHERE user_id = ?", (uid,)).fetchone()["coins"]

# --- БИЗНЕСЫ ---
BUSINESSES = {
    1: {"name": "🍋 Лимонадный ларёк", "price": 50,    "income": 2},
    2: {"name": "☕ Кофейня",           "price": 200,   "income": 7},
    3: {"name": "🍕 Пиццерия",          "price": 700,   "income": 22},
    4: {"name": "🏭 Фабрика",           "price": 2500,  "income": 70},
    5: {"name": "🚀 IT-стартап",        "price": 10000, "income": 260},
}

def biz_rate(biz_id, level):
    return BUSINESSES[biz_id]["income"] * level

def biz_cost(biz_id, level):
    return int(BUSINESSES[biz_id]["price"] * (1.4 ** level))

def get_biz_rows(conn, uid):
    rows = conn.execute("SELECT biz_id, level, last_collect FROM business WHERE user_id = ?", (uid,)).fetchall()
    owned = {r["biz_id"]: dict(r) for r in rows}
    return {bid: owned.get(bid, {"biz_id": bid, "level": 0, "last_collect": 0.0}) for bid in BUSINESSES}

def biz_pending(biz_id, level, last_collect):
    if level <= 0 or last_collect <= 0:
        return 0, 0.0
    elapsed_h = max(0.0, (time.time() - last_collect) / 3600)
    capped_h = min(elapsed_h, CAP_HOURS)
    return int(biz_rate(biz_id, level) * capped_h), capped_h

def collect_one(conn, uid, bid, row):
    level, last = row["level"], row["last_collect"]
    if level <= 0:
        return 0
    amount, _ = biz_pending(bid, level, last)
    now = time.time()
    elapsed_h = max(0.0, (now - last) / 3600)
    rate = biz_rate(bid, level)
    new_last = now if elapsed_h >= CAP_HOURS else last + (amount / rate) * 3600
    conn.execute("UPDATE business SET last_collect = ? WHERE user_id = ? AND biz_id = ?",
                 (new_last, uid, bid))
    if amount > 0:
        add_coins(conn, uid, amount)
    return amount

def collect_all(conn, uid):
    rows = get_biz_rows(conn, uid)
    return sum(collect_one(conn, uid, bid, row) for bid, row in rows.items())

def total_rate(conn, uid):
    rows = get_biz_rows(conn, uid)
    return sum(biz_rate(bid, r["level"]) for bid, r in rows.items())

def fmt_hours(h):
    if h < 1:
        return f"{int(h * 60)} мин"
    return f"{int(h)} ч {int((h % 1) * 60)} мин"

# --- КНОПКИ ВНИЗУ ЧАТА ---
BTN_BONUS   = "🎁 Бонус"
BTN_PROFILE = "👤 Профиль"
BTN_FARM    = "🏭 Ферма"
BTN_COLLECT = "💰 Собрать"
BTN_CASE    = "📦 Кейс"
BTN_ICE     = "🧊 Льдины"
BTN_TOP     = "🏆 Топ"
BTN_REF     = "👥 Реферал"

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_BONUS),   KeyboardButton(text=BTN_PROFILE)],
        [KeyboardButton(text=BTN_FARM),    KeyboardButton(text=BTN_COLLECT)],
        [KeyboardButton(text=BTN_CASE),    KeyboardButton(text=BTN_ICE)],
        [KeyboardButton(text=BTN_TOP),     KeyboardButton(text=BTN_REF)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие или введи команду",
)

HELP_TEXT = (
    "<b>Команды:</b>\n"
    "/profile — профиль\n"
    "/bonus — бонус раз в 12ч\n"
    "/farm — твоя ферма\n"
    "/buy N — купить или улучшить бизнес\n"
    "/collect — собрать доход\n"
    "/case — кейс за 5⭐\n"
    "/ice — игра Льдины\n"
    "/top — таблица лидеров\n"
    "/ref — реферальная ссылка"
)

# --- ОСНОВНЫЕ ДЕЙСТВИЯ ---

async def do_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
        except ValueError:
            pass

    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        if referrer_id and referrer_id != message.from_user.id:
            c = conn.cursor()
            c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (message.from_user.id,))
            if c.fetchone()["referrer_id"] == 0:
                if c.execute("SELECT 1 FROM users WHERE user_id = ?", (referrer_id,)).fetchone():
                    c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?",
                              (referrer_id, message.from_user.id))
                    add_coins(conn, referrer_id, 5)
                    add_coins(conn, message.from_user.id, 5)
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>Новый реферал!</b>\n"
                            f"{message.from_user.first_name} пришёл по твоей ссылке.\n"
                            f"⭐️ +5 на баланс!",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Копи звёзды: забирай бонус и строй ферму — она приносит доход даже когда ты офлайн.\n\n"
        f"{HELP_TEXT}",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

async def do_profile(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        u = ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        rate = total_rate(conn, message.from_user.id)
        refs = conn.execute("SELECT COUNT(*) AS n FROM users WHERE referrer_id = ?",
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
        f"🏭 <b>Доход фермы:</b> {rate}⭐/ч\n"
        f"👥 <b>Рефералов:</b> {refs}\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

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
        conn.execute("UPDATE users SET last_daily = ? WHERE user_id = ?",
                     (time.time(), message.from_user.id))
        balance = get_balance(conn, message.from_user.id)
    txt = f"🎉 <b>БОНУС ПОЛУЧЕН</b>\n⭐️ +{reward}\n💰 Баланс: {balance}"
    if gained:
        txt += "\n\n📊 <b>Новый уровень!</b>"
    await message.answer(txt, reply_markup=MAIN_KB, parse_mode="HTML")

async def do_farm(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        rows = get_biz_rows(conn, message.from_user.id)
        balance = get_balance(conn, message.from_user.id)

    pending_total = rate_total = 0
    lines = []
    for bid, biz in BUSINESSES.items():
        r = rows[bid]
        lvl = r["level"]
        if lvl == 0:
            lines.append(
                f"<b>{bid}. {biz['name']}</b> — не куплен\n"
                f"   💵 Цена: {biz_cost(bid, 0)}⭐ | 📈 {biz['income']}⭐/ч\n"
                f"   👉 /buy {bid}\n"
            )
        else:
            pend, hours = biz_pending(bid, lvl, r["last_collect"])
            pending_total += pend
            rate = biz_rate(bid, lvl)
            rate_total += rate
            full = " ⚠️ ПОЛНОЕ" if hours >= CAP_HOURS else ""
            block = (
                f"<b>{bid}. {biz['name']}</b> — ур. {lvl}/{MAX_BIZ_LEVEL}\n"
                f"   📈 {rate}⭐/ч | 💵 {pend}⭐ готово{full}\n"
            )
            block += (f"   ⬆️ Ур. {lvl+1}: {biz_cost(bid, lvl)}⭐ → /buy {bid}\n"
                      if lvl < MAX_BIZ_LEVEL else "   🔝 Максимальный уровень\n")
            lines.append(block)

    await message.answer(
        f"🏭 <b>ТВОЯ ФЕРМА</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ Баланс: <b>{balance}</b>\n"
        f"📈 Общий доход: <b>{rate_total}⭐/ч</b>\n"
        f"💵 К сбору: <b>{pending_total}⭐</b> → /collect\n"
        f"⏱ Копится максимум {CAP_HOURS}ч, потом стоп\n"
        f"━━━━━━━━━━━━━━\n\n" + "\n".join(lines),
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

async def do_collect(message: types.Message, state: FSMContext):
    await state.clear()
    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        total = collect_all(conn, message.from_user.id)
        balance = get_balance(conn, message.from_user.id)
        rate = total_rate(conn, message.from_user.id)
    if total <= 0:
        msg = ("🏭 У тебя нет бизнесов. Загляни в /farm" if rate <= 0
               else "⏳ Пока пусто, доход ещё копится.")
        await message.answer(msg, reply_markup=MAIN_KB)
        return
    await message.answer(
        f"💰 <b>ДОХОД СОБРАН</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ +{total}\n"
        f"💳 Баланс: {balance}\n"
        f"📈 Дальше: {rate}⭐/ч\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

async def do_buy(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) not in BUSINESSES:
        await message.answer("❌ Формат: /buy N\nНапример: /buy 1\nСписок — /farm", reply_markup=MAIN_KB)
        return
    bid = int(args[1])
    biz = BUSINESSES[bid]

    with db() as conn:
        ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
        row = get_biz_rows(conn, message.from_user.id)[bid]
        lvl = row["level"]
        if lvl >= MAX_BIZ_LEVEL:
            await message.answer(f"🔝 {biz['name']} уже максимального уровня.", reply_markup=MAIN_KB)
            return

        settled = collect_one(conn, message.from_user.id, bid, row)
        cost = biz_cost(bid, lvl)
        balance = get_balance(conn, message.from_user.id)
        if balance < cost:
            extra = f"\n(собрано по пути: +{settled}⭐)" if settled else ""
            await message.answer(f"❌ Не хватает звёзд.\nНужно {cost}⭐, у тебя {balance}⭐{extra}",
                                 reply_markup=MAIN_KB)
            return

        add_coins(conn, message.from_user.id, -cost)
        now = time.time()
        if lvl == 0:
            conn.execute("INSERT INTO business (user_id, biz_id, level, last_collect) VALUES (?, ?, 1, ?)",
                         (message.from_user.id, bid, now))
        else:
            conn.execute("UPDATE business SET level = ?, last_collect = ? WHERE user_id = ? AND biz_id = ?",
                         (lvl + 1, now, message.from_user.id, bid))
        new_balance = get_balance(conn, message.from_user.id)
        new_rate = biz_rate(bid, lvl + 1)

    action = "КУПЛЕН" if lvl == 0 else f"УЛУЧШЕН ДО УР. {lvl+1}"
    await message.answer(
        f"✅ <b>{biz['name']} {action}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💸 Потрачено: {cost}⭐\n"
        f"📈 Доход: {new_rate}⭐/ч\n"
        f"💳 Баланс: {new_balance}⭐\n"
        f"━━━━━━━━━━━━━━\n"
        f"Собрать доход: /collect",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

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
        try:
            await anim.edit_text(frame)
        except Exception:
            pass

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
        if prize[2] == "coins":
            add_coins(conn, uid, prize[3])
        elif prize[2] == "tokens":
            add_tokens(conn, uid, prize[3])
        balance = get_balance(conn, uid)

    await anim.edit_text(
        f"🎰 <b>РЕЗУЛЬТАТ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Выпало: <b>{prize[0]}</b>\n"
        f"💳 Баланс: {balance}⭐\n"
        f"━━━━━━━━━━━━━━\n"
        f"Ещё раз: /case",
        parse_mode="HTML",
    )

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
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
    await message.answer(
        f"👥 <b>ПРИГЛАСИ ДРУГА</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<code>{link}</code>\n\n"
        f"⭐️ Тебе +5, другу +5\n"
        f"👤 Приглашено: {n}\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

# --- ЛЬДИНЫ ---
ICE_DIFFICULTIES = {
    "easy":    {"name": "🟢 Легко",   "mult": 0.5, "rate": 0.80},
    "medium":  {"name": "🟡 Средне",  "mult": 1.0, "rate": 0.60},
    "hard":    {"name": "🔴 Сложно",  "mult": 2.0, "rate": 0.40},
    "extreme": {"name": "💀 Экстрим", "mult": 3.0, "rate": 0.25},
    "madness": {"name": "🤯 Безумие", "mult": 5.0, "rate": 0.10},
}

async def do_ice(message: types.Message, state: FSMContext):
    args = message.text.split()

    if len(args) < 2:
        await state.clear()
        with db() as conn:
            ensure_user(conn, message.from_user.id, message.from_user.username, message.from_user.first_name)
            balance = get_balance(conn, message.from_user.id)
        lines = [f"/ice {k} — {v['name']} (x{v['mult']}, {int(v['rate']*100)}%)"
                 for k, v in ICE_DIFFICULTIES.items()]
        await message.answer(
            f"🧊 <b>ЛЬДИНЫ</b>\n━━━━━━━━━━━━━━\n"
            f"⭐️ Баланс: {balance}\n\n" + "\n".join(lines) +
            f"\n\n<b>Формат:</b> /ice [сложность] [ставка 1-10]\n"
            f"<b>Пример:</b> <code>/ice extreme 5</code>",
            reply_markup=MAIN_KB, parse_mode="HTML",
        )
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
        f"🎁 В призе: 0⭐\n━━━━━━━━━━━━━━\n"
        f"/jump — прыгнуть\n/take — забрать приз\n/quit — сдаться",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    d = ICE_DIFFICULTIES[data["difficulty"]]
    bet = data["bet"]

    if random.random() < d["rate"]:
        gain = max(1, int(bet * d["mult"]))
        reward, jumps = data["reward"] + gain, data["jumps"] + 1
        await state.update_data(reward=reward, jumps=jumps)
        await message.answer(
            f"✅ <b>УСПЕХ</b>\n━━━━━━━━━━━━━━\n"
            f"💎 +{gain}⭐\n🎁 В призе: <b>{reward}⭐</b>\n🦘 Прыжков: {jumps}\n"
            f"━━━━━━━━━━━━━━\n/jump — ещё\n/take — забрать {reward}⭐\n/quit — сдаться",
            reply_markup=MAIN_KB, parse_mode="HTML",
        )
    else:
        await state.clear()
        await message.answer(
            f"💦 <b>ПРОВАЛ</b>\n━━━━━━━━━━━━━━\n"
            f"Льдина треснула, ты в воде.\n"
            f"💸 Потеряно: {bet}⭐ (приз {data['reward']}⭐ сгорел)\n"
            f"━━━━━━━━━━━━━━\nЕщё раз: /ice",
            reply_markup=MAIN_KB, parse_mode="HTML",
        )

@dp.message(Command("take"))
async def cmd_take(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре. /ice", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    await state.clear()
    reward, bet, jumps = data["reward"], data["bet"], data["jumps"]
    with db() as conn:
        if reward > 0:
            add_coins(conn, message.from_user.id, reward)
        balance = get_balance(conn, message.from_user.id)
    profit = reward - bet
    await message.answer(
        f"🏆 <b>ПРИЗ ЗАБРАН</b>\n━━━━━━━━━━━━━━\n"
        f"🎁 Получено: {reward}⭐\n💰 Ставка: {bet}⭐\n"
        f"📈 Итог: {'+' if profit >= 0 else ''}{profit}⭐\n"
        f"🦘 Прыжков: {jumps}\n💳 Баланс: {balance}⭐\n━━━━━━━━━━━━━━",
        reply_markup=MAIN_KB, parse_mode="HTML",
    )

@dp.message(Command("quit"))
async def cmd_quit(message: types.Message, state: FSMContext):
    if await state.get_state() != St.playing_ice.state:
        await message.answer("❌ Ты не в игре.", reply_markup=MAIN_KB)
        return
    data = await state.get_data()
    await state.clear()
    await message.answer(f"🏳️ <b>СДАЛСЯ</b>\n💸 Ставка {data.get('bet', 0)}⭐ потеряна.",
                         reply_markup=MAIN_KB, parse_mode="HTML")

# --- РЕГИСТРАЦИЯ ---
dp.message.register(do_start,   Command("start"))
dp.message.register(do_profile, Command("profile"))
dp.message.register(do_bonus,   Command("bonus"))
dp.message.register(do_farm,    Command("farm", "biz"))
dp.message.register(do_collect, Command("collect"))
dp.message.register(do_buy,     Command("buy", "up"))
dp.message.register(do_case,    Command("case"))
dp.message.register(do_ice,     Command("ice"))
dp.message.register(do_top,     Command("top"))
dp.message.register(do_ref,     Command("ref"))

dp.message.register(do_bonus,   F.text == BTN_BONUS)
dp.message.register(do_profile, F.text == BTN_PROFILE)
dp.message.register(do_farm,    F.text == BTN_FARM)
dp.message.register(do_collect, F.text == BTN_COLLECT)
dp.message.register(do_case,    F.text == BTN_CASE)
dp.message.register(do_ice,     F.text == BTN_ICE)
dp.message.register(do_top,     F.text == BTN_TOP)
dp.message.register(do_ref,     F.text == BTN_REF)

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
        biz = conn.execute("SELECT COUNT(*) AS n FROM business WHERE level > 0").fetchone()["n"]
        day = conn.execute("SELECT COUNT(*) AS n FROM users WHERE last_daily > ?",
                           (time.time() - 86400,)).fetchone()["n"]
    await message.answer(
        f"📊 <b>СТАТИСТИКА</b>\n👥 Всего: {n}\n🔥 Активных за 24ч: {day}\n"
        f"⭐️ Звёзд у игроков: {stars}\n🏭 Бизнесов куплено: {biz}",
        parse_mode="HTML",
    )

@dp.message(F.text)
async def fallback(message: types.Message, state: FSMContext):
    await message.answer(f"🤔 Не понял.\n\n{HELP_TEXT}", reply_markup=MAIN_KB, parse_mode="HTML")

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
