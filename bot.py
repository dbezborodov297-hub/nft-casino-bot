import asyncio, random, sqlite3, os, time, contextlib
from html import escape
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

# ═══════════════════════════════════════════════════════════
BOT_TOKEN = "9088817673:AAE1IVv-cR4x9fxGssTkxQVcHfe_OD4GPj8"        # 👈 токен от @BotFather

START_TOKENS   = 5
GEN_REWARD     = 1                # токенов за генерацию
GEN_COOLDOWN   = 45 * 60 * 60     # 45 часов
REF_REWARD     = 2
REF_NEWBIE     = 1
REF_MILESTONES = {1: 2, 3: 5, 5: 10, 10: 25, 25: 60}
CODE_PREFIX    = "SF"

# Награда промокода: 5–150 звёзд. Большие суммы (100–150) — 5%.
BIG_CHANCE = 0.05
BIG_MIN, BIG_MAX = 100, 150
MID_CHANCE = 0.20
MID_MIN, MID_MAX = 31, 99
SMALL_MIN, SMALL_MAX = 5, 30
# ═══════════════════════════════════════════════════════════

if BOT_TOKEN == "ВСТАВЬ_ТОКЕН" or ":" not in BOT_TOKEN:
    raise SystemExit("\n❌ Вставь токен в строку BOT_TOKEN наверху файла.\n")

DB_PATH = "bot.db"
BOT_USERNAME = ""
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def esc(s):
    return escape(str(s)) if s else ""

app = Flask(__name__)
@app.route("/")
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            tokens INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            last_gen REAL DEFAULT 0,
            gens INTEGER DEFAULT 0,
            created_at REAL DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            ref_paid INTEGER DEFAULT 0,
            activated INTEGER DEFAULT 0,
            ref_earned INTEGER DEFAULT 0,
            welcome INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at REAL,
            stars INTEGER DEFAULT 0,
            used_by INTEGER DEFAULT 0,
            used_at REAL DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS ref_ms (
            user_id INTEGER,
            n INTEGER,
            PRIMARY KEY (user_id, n)
        )""")
        for col, ddl in [
            ("tokens", "INTEGER DEFAULT 0"), ("stars", "INTEGER DEFAULT 0"),
            ("last_gen", "REAL DEFAULT 0"), ("gens", "INTEGER DEFAULT 0"),
            ("created_at", "REAL DEFAULT 0"), ("referrer_id", "INTEGER DEFAULT 0"),
            ("ref_paid", "INTEGER DEFAULT 0"), ("activated", "INTEGER DEFAULT 0"),
            ("ref_earned", "INTEGER DEFAULT 0"), ("welcome", "INTEGER DEFAULT 0"),
        ]:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
        for col, ddl in [
            ("stars", "INTEGER DEFAULT 0"), ("used_by", "INTEGER DEFAULT 0"),
            ("used_at", "REAL DEFAULT 0"),
        ]:
            try:
                c.execute(f"ALTER TABLE codes ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_codes_user ON codes(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ref ON users(referrer_id)")

def ensure_user(conn, uid, un=None, fn=None):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    t = time.time()
    if row is None:
        c.execute("INSERT INTO users (user_id, username, first_name, created_at) VALUES (?,?,?,?)",
                  (uid, un, fn, t))
    elif un is not None or fn is not None:
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (un, fn, uid))
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return c.fetchone()

def add_tokens(conn, uid, n):
    conn.execute("UPDATE users SET tokens = MAX(0, tokens + ?) WHERE user_id=?", (n, uid))

def add_stars(conn, uid, n):
    conn.execute("UPDATE users SET stars = MAX(0, stars + ?) WHERE user_id=?", (n, uid))

def plural(n, a, b, c):
    n = abs(n) % 100
    d = n % 10
    if 10 < n < 20: return c
    if 1 < d < 5: return b
    if d == 1: return a
    return c

def fmt_left(sec):
    sec = int(max(0, sec))
    h, m = sec // 3600, (sec % 3600) // 60
    if h: return f"{h} ч {m} мин"
    if m: return f"{m} мин"
    return f"{sec} сек"

def gen_left(u):
    if not u["last_gen"]: return 0
    return GEN_COOLDOWN - (time.time() - u["last_gen"])

def roll_stars():
    r = random.random()
    if r < BIG_CHANCE:
        return random.randint(BIG_MIN, BIG_MAX), "big"
    if r < BIG_CHANCE + MID_CHANCE:
        return random.randint(MID_MIN, MID_MAX), "mid"
    return random.randint(SMALL_MIN, SMALL_MAX), "small"

def ref_stats(conn, uid):
    total = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?", (uid,)).fetchone()["n"]
    active = conn.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=? AND activated=1", (uid,)).fetchone()["n"]
    return total, active

def make_code(conn):
    while True:
        raw = "".join(random.choices(ALPHABET, k=8))
        code = f"{CODE_PREFIX}-{raw[:4]}-{raw[4:]}"
        if not conn.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone():
            return code

def bind_referrer(conn, uid, ref_id):
    if not ref_id or ref_id == uid:
        return False
    c = conn.cursor()
    if not c.execute("SELECT 1 FROM users WHERE user_id=?", (ref_id,)).fetchone():
        return False
    c.execute("SELECT referrer_id FROM users WHERE user_id=?", (uid,))
    if c.fetchone()["referrer_id"] != 0:
        return False
    c.execute("SELECT referrer_id FROM users WHERE user_id=?", (ref_id,))
    if c.fetchone()["referrer_id"] == uid:
        return False
    c.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref_id, uid))
    return True

def activate_user(conn, uid):
    c = conn.cursor()
    c.execute("SELECT activated, referrer_id, ref_paid FROM users WHERE user_id=?", (uid,))
    u = c.fetchone()
    if u["activated"]:
        return None
    c.execute("UPDATE users SET activated=1 WHERE user_id=?", (uid,))
    add_tokens(conn, uid, REF_NEWBIE)
    ref = u["referrer_id"]
    if not ref or u["ref_paid"]:
        return None
    c.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (uid,))
    add_tokens(conn, ref, REF_REWARD)
    c.execute("UPDATE users SET ref_earned = ref_earned + ? WHERE user_id=?", (REF_REWARD, ref))
    active = c.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=? AND activated=1", (ref,)).fetchone()["n"]
    bonus = 0
    for n, reward in REF_MILESTONES.items():
        if active >= n and not c.execute("SELECT 1 FROM ref_ms WHERE user_id=? AND n=?", (ref, n)).fetchone():
            c.execute("INSERT INTO ref_ms (user_id, n) VALUES (?,?)", (ref, n))
            add_tokens(conn, ref, reward)
            c.execute("UPDATE users SET ref_earned = ref_earned + ? WHERE user_id=?", (reward, ref))
            bonus += reward
    return {"ref": ref, "active": active, "bonus": bonus}

B_GEN, B_PROF, B_REF, B_CODES = "🎟 Сгенерировать", "👤 Профиль", "👥 Рефералы", "📋 Мои коды"

KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text=B_GEN)],
    [KeyboardButton(text=B_PROF), KeyboardButton(text=B_REF)],
    [KeyboardButton(text=B_CODES)],
], resize_keyboard=True, input_field_placeholder="Выбери действие")

HELP = (
    "📖 <b>КАК ЭТО РАБОТАЕТ</b>\n\n"
    "<b>1 · Генерация</b>\n"
    "/generate — создать промокод\n"
    "Каждый код несёт от <b>5 до 150 ⭐</b>\n"
    "Большие суммы 100–150 ⭐ выпадают с шансом <b>5%</b>\n"
    "Генерация доступна раз в <b>45 часов</b>\n"
    "За генерацию также +1 🪙 токен\n\n"
    "<b>2 · Активация</b>\n"
    "/use CODE — забрать звёзды с кода\n"
    "Код можно активировать только один раз\n\n"
    "<b>3 · Профиль и рефералы</b>\n"
    "/profile — баланс и таймер\n"
    "/codes — созданные коды\n"
    "/ref — ссылка и награды за друзей"
)

async def do_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
        except ValueError:
            pass

    welcome, bound = 0, False
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        if not u["welcome"]:
            welcome = START_TOKENS
            add_tokens(conn, uid, START_TOKENS)
            conn.execute("UPDATE users SET welcome=1 WHERE user_id=?", (uid,))
        if ref_id:
            bound = bind_referrer(conn, uid, ref_id)
        bal = conn.execute("SELECT tokens, stars FROM users WHERE user_id=?", (uid,)).fetchone()

    text = f"👋 <b>Привет, {esc(message.from_user.first_name)}!</b>\n\n"
    if welcome:
        text += f"🎁 Стартовый баланс: <b>{welcome} 🪙</b>\n"
    if bound:
        text += f"👥 Ты по приглашению. Создай первый код — получишь ещё <b>+{REF_NEWBIE} 🪙</b>\n"
    if welcome or bound:
        text += f"💳 Сейчас: <b>{bal['tokens']} 🪙</b> · <b>{bal['stars']} ⭐</b>\n"
    text += "\n" + HELP
    await message.answer(text, reply_markup=KB, parse_mode="HTML")

async def do_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(HELP, reply_markup=KB, parse_mode="HTML")

async def do_generate(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        left = gen_left(u)
        if left > 0:
            ready = time.strftime("%d.%m в %H:%M", time.localtime(time.time() + left))
            await message.answer(
                f"⏳ <b>Генерация ещё не готова</b>\n\n"
                f"Осталось: <b>{fmt_left(left)}</b>\n"
                f"Будет доступна {ready}\n\n"
                f"<blockquote>💳 Баланс: {u['tokens']} 🪙 · {u['stars']} ⭐\n"
                f"🎟 Создано кодов: {u['gens']}</blockquote>\n\n"
                f"Пока ждёшь — пригласи друга: /ref",
                reply_markup=KB, parse_mode="HTML")
            return

        code = make_code(conn)
        stars, tier = roll_stars()
        t = time.time()
        conn.execute("INSERT INTO codes (code, user_id, created_at, stars) VALUES (?,?,?,?)",
                     (code, uid, t, stars))
        conn.execute("UPDATE users SET last_gen=?, gens=gens+1 WHERE user_id=?", (t, uid))
        add_tokens(conn, uid, GEN_REWARD)
        was_active = u["activated"]
        info = activate_user(conn, uid)
        u2 = conn.execute("SELECT tokens, stars, gens FROM users WHERE user_id=?", (uid,)).fetchone()

    if info:
        try:
            extra = f"\n🏅 Награда за {info['active']} {plural(info['active'],'друга','друзей','друзей')}: +{info['bonus']} 🪙" if info["bonus"] else ""
            await bot.send_message(
                info["ref"],
                f"🎉 <b>Друг активировался</b>\n\n"
                f"{esc(message.from_user.first_name)} создал первый код.\n"
                f"Тебе начислено <b>+{REF_REWARD} 🪙</b>{extra}",
                parse_mode="HTML")
        except Exception:
            pass

    act_line = f"\n🎁 Бонус за первый код: <b>+{REF_NEWBIE} 🪙</b>" if not was_active else ""
    tier_line = "🔥 <b>Редкая крупная сумма!</b>\n" if tier == "big" else ""
    await message.answer(
        f"✅ <b>ПРОМОКОД СОЗДАН</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"{tier_line}"
        f"Награда кода: <b>{stars} ⭐</b>\n"
        f"Активировать: <code>/use {code}</code>\n\n"
        f"<blockquote>🪙 +{GEN_REWARD} токен{act_line}\n"
        f"💳 Баланс: {u2['tokens']} 🪙 · {u2['stars']} ⭐\n"
        f"🎟 Всего кодов: {u2['gens']}</blockquote>\n\n"
        f"Следующая генерация через <b>45 ч</b>\n"
        f"Все коды — /codes",
        reply_markup=KB, parse_mode="HTML")

async def do_use(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "🎁 <b>Активация кода</b>\n\n"
            "Формат: <code>/use CODE</code>\n"
            "Пример: <code>/use SF-ABCD-EFGH</code>\n\n"
            "Создать код — /generate",
            reply_markup=KB, parse_mode="HTML")
        return
    code = args[1].strip().upper()
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        row = conn.execute("SELECT * FROM codes WHERE code=?", (code,)).fetchone()
        if not row:
            await message.answer("❌ <b>Код не найден</b>\n\nПроверь написание или создай свой — /generate",
                                 reply_markup=KB, parse_mode="HTML")
            return
        if row["used_by"]:
            await message.answer("⚠️ <b>Код уже активирован</b>\n\nОдин код — один раз.",
                                 reply_markup=KB, parse_mode="HTML")
            return
        stars = row["stars"] or roll_stars()[0]
        conn.execute("UPDATE codes SET used_by=?, used_at=? WHERE code=?", (uid, time.time(), code))
        add_stars(conn, uid, stars)
        bal = conn.execute("SELECT stars, tokens FROM users WHERE user_id=?", (uid,)).fetchone()
    big = stars >= BIG_MIN
    await message.answer(
        f"{'🔥' if big else '🎉'} <b>КОД АКТИВИРОВАН</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"Получено: <b>+{stars} ⭐</b>\n"
        f"💳 Баланс: <b>{bal['stars']} ⭐</b> · {bal['tokens']} 🪙",
        reply_markup=KB, parse_mode="HTML")

async def do_profile(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        u = ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        total, active = ref_stats(conn, uid)
        used = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(stars),0) s FROM codes WHERE used_by=?", (uid,)).fetchone()
        last = conn.execute("SELECT code, stars FROM codes WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
                            (uid,)).fetchone()
    left = gen_left(u)
    status = "🟢 готова сейчас" if left <= 0 else f"⏳ через {fmt_left(left)}"
    name = f"@{esc(u['username'])}" if u["username"] else esc(u["first_name"] or "Игрок")
    since = time.strftime("%d.%m.%Y", time.localtime(u["created_at"] or time.time()))
    last_line = f"\n🎟 Последний: <code>{last['code']}</code> · {last['stars']} ⭐" if last else ""

    await message.answer(
        f"👤 <b>ПРОФИЛЬ</b>\n\n"
        f"{name}\n"
        f"id {uid}\n\n"
        f"<blockquote>⭐ Звёзды: {u['stars']}\n"
        f"🪙 Токены: {u['tokens']}\n"
        f"🎟 Кодов создано: {u['gens']}\n"
        f"🎁 Активировано чужих/своих: {used['n']} на {used['s']} ⭐\n"
        f"👥 Приглашено: {total} · активных: {active}\n"
        f"💰 Заработано на друзьях: {u['ref_earned']} 🪙</blockquote>\n\n"
        f"<b>Генерация</b>\n{status}{last_line}\n\n"
        f"📅 С нами с {since}",
        reply_markup=KB, parse_mode="HTML")

async def do_codes(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        rows = conn.execute("SELECT code, stars, used_by, created_at FROM codes "
                            "WHERE user_id=? ORDER BY created_at DESC LIMIT 15", (uid,)).fetchall()
        n = conn.execute("SELECT COUNT(*) n FROM codes WHERE user_id=?", (uid,)).fetchone()["n"]
    if not rows:
        await message.answer(
            "📋 <b>Мои коды</b>\n\n"
            "Пока пусто. Создай первый — /generate",
            reply_markup=KB, parse_mode="HTML")
        return
    lines = []
    for r in rows:
        status = "✅ использован" if r["used_by"] else "🟢 активен"
        lines.append(f"<code>{r['code']}</code> · {r['stars']} ⭐ · {status}")
    await message.answer(
        f"📋 <b>МОИ КОДЫ</b> · всего {n}\n\n"
        f"<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
        f"Активировать: <code>/use CODE</code>\n"
        f"Нажми на код, чтобы скопировать.",
        reply_markup=KB, parse_mode="HTML")

async def do_ref(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    with db() as conn:
        ensure_user(conn, uid, message.from_user.username, message.from_user.first_name)
        total, active = ref_stats(conn, uid)
        earned = conn.execute("SELECT ref_earned FROM users WHERE user_id=?", (uid,)).fetchone()["ref_earned"]
        people = conn.execute("SELECT username, first_name, activated FROM users "
                              "WHERE referrer_id=? ORDER BY created_at DESC LIMIT 10", (uid,)).fetchall()
        done = {r["n"] for r in conn.execute("SELECT n FROM ref_ms WHERE user_id=?", (uid,)).fetchall()}

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    ms_lines = []
    for n, reward in REF_MILESTONES.items():
        if n in done:
            ms_lines.append(f"✅ {n} — +{reward} 🪙 получено")
        elif active >= n:
            ms_lines.append(f"🔓 {n} — +{reward} 🪙 скоро")
        else:
            ms_lines.append(f"🔒 {n} — +{reward} 🪙 (ещё {n - active})")
    nxt = next((n for n in REF_MILESTONES if n not in done), None)
    progress = f"\nДо следующей награды: <b>{max(0, nxt - active)}</b> {plural(max(0, nxt-active),'друг','друга','друзей')}" if nxt else "\nВсе награды получены 🏅"

    ppl = ""
    if people:
        rows = []
        for p in people:
            nm = f"@{esc(p['username'])}" if p["username"] else esc(p["first_name"] or "Игрок")
            rows.append(f"{nm} — {'активен ✅' if p['activated'] else 'ждёт первый код'}")
        ppl = "\n\n<b>Приглашённые</b>\n<blockquote>" + "\n".join(rows) + "</blockquote>"

    await message.answer(
        f"👥 <b>РЕФЕРАЛЫ</b>\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"<blockquote>Друг создаёт первый код → тебе +{REF_REWARD} 🪙\n"
        f"Другу за активацию +{REF_NEWBIE} 🪙\n"
        f"Приглашено: {total} · активных: {active}\n"
        f"Заработано: {earned} 🪙</blockquote>\n\n"
        f"<b>Награды за друзей</b>\n<blockquote>" + "\n".join(ms_lines) + "</blockquote>"
        f"{progress}{ppl}\n\n"
        f"Повторный переход по ссылке награду не даёт.",
        reply_markup=KB, parse_mode="HTML")

async def fallback(message: types.Message, state: FSMContext):
    await message.answer(
        "🤔 <b>Не понял команду</b>\n\n"
        "Нажми кнопку внизу или открой /help",
        reply_markup=KB, parse_mode="HTML")

dp.message.register(do_start, Command("start"))
dp.message.register(do_help, Command("help"))
dp.message.register(do_generate, Command("generate", "gen"))
dp.message.register(do_use, Command("use", "activate"))
dp.message.register(do_profile, Command("profile"))
dp.message.register(do_codes, Command("codes"))
dp.message.register(do_ref, Command("ref"))

dp.message.register(do_generate, F.text == B_GEN)
dp.message.register(do_profile, F.text == B_PROF)
dp.message.register(do_ref, F.text == B_REF)
dp.message.register(do_codes, F.text == B_CODES)
dp.message.register(fallback, F.text)

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
