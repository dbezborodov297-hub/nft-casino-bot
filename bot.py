import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9209660223:AAEUC0yzyJPV3DB3ah6LdJwracFPBGn50nc"
ADMIN_ID = 8907438590
EVENT_DAYS = 15
EVENT_PRIZE = 500

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

BASE_SHOP = {
    "🚀 Rocket Dog #18": {"base": 10, "limit": 15, "bonus": 10.0},
    "💎 Diamond Dog #22": {"base": 23, "limit": 10, "bonus": 10.3},
    "🍾 Bottle #1": {"base": 25, "limit": 70, "bonus": 3.0},
    "🪄 Wand #4": {"base": 70, "limit": 145, "bonus": 14.2},
    "🪔 Lamp #7": {"base": 120, "limit": 35, "bonus": 19.2},
    "🏅 Medal #9": {"base": 44, "limit": 45, "bonus": 11.1},
    "🛟 Lifebuoy #3": {"base": 50, "limit": 90, "bonus": 12.8},
    "🕶️ Dark Glasses #0": {"base": 750, "limit": 5, "bonus": 34.7},
    "🎃 Pumpkin Dog #1": {"base": 50, "limit": 50, "bonus": 9.9},
    "🍭 Lollipop #2": {"base": 15, "limit": 144, "bonus": 5.0},
    "🎗️ Ribbon": {"base": 47, "limit": 65, "bonus": 7.9},
    "🎖️ Medal Skin": {"base": 75, "limit": 15, "bonus": 8.3},
    "🎩 Hat": {"base": 150, "limit": 60, "bonus": 19.8},
    "🎭 Mask": {"base": 90, "limit": 130, "bonus": 19.9},
    "🎒 Backpack": {"base": 35, "limit": 180, "bonus": 11.3},
    "🪀 Yo-yo": {"base": 125, "limit": 55, "bonus": 18.2},
    "🧶 Yarn": {"base": 220, "limit": 9, "bonus": 28.9},
    "👓 Glasses": {"base": 775, "limit": 120, "bonus": 34.8},
    "🥽 Goggles": {"base": 333, "limit": 105, "bonus": 27.0}
}
SHOP = {}

app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, coins INTEGER DEFAULT 0, iris INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_card REAL DEFAULT 0, last_daily REAL DEFAULT 0, is_admin INTEGER DEFAULT 0, referrer_id INTEGER DEFAULT NULL, event_points INTEGER DEFAULT 0, ref_earned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_sold (item_name TEXT PRIMARY KEY, sold_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_name TEXT, price INTEGER, status TEXT DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted_bots (chat_id INTEGER, bot_id INTEGER, PRIMARY KEY (chat_id, bot_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS clans (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, owner_id INTEGER, members TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, username TEXT, timestamp REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS prices (item_name TEXT PRIMARY KEY, current_price INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    for name, data in BASE_SHOP.items():
        c.execute("INSERT OR IGNORE INTO shop_sold (item_name, sold_count) VALUES (?, 0)", (name,))
        c.execute("INSERT OR REPLACE INTO prices (item_name, current_price) VALUES (?, ?)", (name, data["base"]))
        SHOP[name] = {"price": data["base"], "limit": data["limit"], "bonus": data["bonus"], "base": data["base"]}
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('event_start', ?)", (str(time.time()),))
    conn.commit(); conn.close()

def get_event_start():
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'event_start'")
    res = c.fetchone(); conn.close()
    return float(res[0]) if res else time.time()

def load_prices():
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name, current_price FROM prices")
    for name, price in c.fetchall():
        if name in SHOP: SHOP[name]["price"] = price
    conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, iris, xp, level, last_card, last_daily, is_admin, referrer_id, event_points, ref_earned FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0, 0, 0, 1, 0, 0, 0, None, 0, 0)
    conn.close(); return res

def add_event(uid, coins):
    pts = coins * 100
    if pts > 0:
        conn = sqlite3.connect('bot.db'); c = conn.cursor()
        c.execute("UPDATE users SET event_points = event_points + ? WHERE user_id = ?", (pts, uid))
        conn.commit(); conn.close()

def update_info(uid, uname, fname):
    conn = sqlite3.connect('bot.db')
    conn.execute("INSERT INTO users (user_id, username, first_name) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name", (uid, uname, fname))
    conn.commit(); conn.close()

def get_inv(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (uid,))
    items = c.fetchall(); conn.close(); return items

def get_bonus(uid):
    items = get_inv(uid); bonus = 0.0
    for _, item in items:
        base_name = item.split(" [")[0]
        if base_name in SHOP: bonus += SHOP[base_name]["bonus"]
    return bonus

def get_rank(coins):
    if coins < 50: return "🥉 Новичок"
    elif coins < 150: return "🥈 Любитель"
    elif coins < 500: return "🥇 Профи"
    else: return "👑 Магнат"

async def is_admin(msg):
    if msg.from_user.id == ADMIN_ID: return True
    return get_user(msg.from_user.id)[6] == 1

async def market_fluct():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(3600 * 4)
        if not SHOP: continue
        name = random.choice(list(SHOP.keys()))
        data = SHOP[name]
        cur = data["price"]; base = data["base"]
        new = max(int(cur * (1 - random.uniform(0.02, 0.05))), int(base * 0.7))
        if new < cur:
            data["price"] = new
            conn = sqlite3.connect('bot.db'); c = conn.cursor()
            c.execute("UPDATE prices SET current_price = ? WHERE item_name = ?", (new, name))
            conn.commit(); conn.close()

async def broadcast(text):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT user_id FROM users"); users = c.fetchall(); conn.close()
    for (uid,) in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except: pass

async def check_event():
    while True:
        await asyncio.sleep(3600)
        start = get_event_start()
        if time.time() - start > EVENT_DAYS * 86400:
            conn = sqlite3.connect('bot.db'); c = conn.cursor()
            c.execute("SELECT user_id, username, event_points FROM users ORDER BY event_points DESC LIMIT 10")
            top = c.fetchall(); conn.close()
            if top:
                text = f"🏆 <b>ИТОГИ ИВЕНТА НА {EVENT_PRIZE} ЗВЁЗД!</b> 🏆\n\n<blockquote>"
                for i, (uid, uname, points) in enumerate(top, 1):
                    text += f"{i}. @{uname or 'Аноним'} — {points/100:.0f} ⭐\n"
                text += "</blockquote>"
                await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
            break

@dp.message(Command("start"))
async def start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    get_user(user_id)
    update_info(user_id, message.from_user.username, message.from_user.first_name)
    if command.args and command.args.isdigit():
        ref = int(command.args)
        if ref != user_id:
            conn = sqlite3.connect('bot.db'); c = conn.cursor()
            c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
            res = c.fetchone()
            if res and res[0] is None:
                c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref, user_id))
                c.execute("UPDATE users SET coins = coins + 3, ref_earned = ref_earned + 3 WHERE user_id = ?", (ref,))
                conn.commit()
                try: await bot.send_message(ref, "🎉 Новый реферал! +3 монеты.")
                except: pass
            conn.close()
    await message.answer("👋 Привет! /help — команды.\n💡 <i>Совет: .карточка — доход.</i>", parse_mode="HTML")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (f"📖 <b>ИНСТРУКЦИЯ</b>\n\n<b>🎮 Игры:</b>\n• <b>.карточка</b> — открыть (5 мин)\n• <b>/roulette [ставка]</b> — рулетка с NFT\n• <b>/daily</b> — бонус (+30)\n\n<b>👤 Экономика:</b>\n• <b>/profile</b> — профиль\n• <b>/top</b> — топ монет\n• <b>/top_iris</b> — топ ирисок\n• <b>/shop</b> — магазин (кнопки)\n• <b>/inventory</b> — NFT\n• <b>/exchange [сумма]</b> — ириски на монеты (2:1)\n• <b>/ref</b> — рефералка\n\n<b>🏆 Ивент:</b>\n• <b>/event</b> — таблица ивента\n\n<b>🏪 Рынок:</b>\n• <b>/sell [Название] [Цена]</b>\n• <b>/market</b>\n• <b>/buy [ID]</b>\n\n<b>🔨 Крафт:</b>\n• <b>/craft</b> — улучшить NFT\n\n<b>🛡 Кланы:</b>\n• <b>/clan_create [Название]</b>\n• <b>/clan_info [Название]</b>\n\n<b>📊 Аналитика:</b>\n• <b>/stats</b> — полный отчет\n\n<b>🔨 Модерация:</b>\n• <b>/mute</b>, <b>/unmute</b>, <b>/ban</b>, <b>/kick</b>, <b>/unban</b>\n• <b>/clear [число]</b>\n• <b>/close_chat</b>, <b>/open_chat</b>\n• <b>/mute_bot</b>, <b>/mute_all_bots</b>, <b>/unmute_all_bots</b>\n\n<b>👑 Админы:</b>\n• <b>/add_admin [ID]</b>, <b>/remove_admin [ID]</b>, <b>/admin_list</b>")
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    coins, iris, xp, level, _, _, is_admin, _, event_points, ref_earned = get_user(target.id)
    rank = get_rank(coins)
    bonus = get_bonus(target.id)
    needed_xp = level * 5000
    bar = "█" * min(int((xp / needed_xp) * 10), 10) + "░" * (10 - min(int((xp / needed_xp) * 10), 10))
    status = "👑 Админ" if is_admin else "👤 Игрок"
    text = (f"👤 <b>ПРОФИЛЬ {target.first_name}</b>\n\n🆔 <code>{target.id}</code>\n🛡 {status}\n🏅 Ранг: <b>{rank}</b>\n📈 Ур: <b>{level}</b> [{bar}] ({xp}/{needed_xp})\n\n🪙 Монеты: <b>{coins}</b>\n🍬 Ириски: <b>{iris}</b>\n🎁 Бонус: <b>+{bonus:.1f}%</b>\n🏆 Очки ивента: <b>{event_points}</b>\n👥 Рефералов: <b>{ref_earned // 3}</b>\n\n💡 <i>Совет: .карточка — доход.</i>")
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ref"))
async def ref_cabinet(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, _, _, _, _, _, ref_earned = get_user(user_id)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name FROM users WHERE referrer_id = ?", (user_id,))
    refs = c.fetchall(); conn.close()
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={user_id}"
    text = (f"👥 <b>РЕФЕРАЛЬНЫЙ КАБИНЕТ</b>\n\n🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n👤 Приглашено друзей: <b>{len(refs)}</b>\n🪙 Заработано на рефералах: <b>{ref_earned}</b> монет\n🎁 За каждого друга: <b>+3 монеты</b>\n\n")
    if refs:
        text += "<b>Твои рефералы:</b>\n"
        for i, (uname, fname) in enumerate(refs[:10], 1):
            name = f"@{uname}" if uname else fname
            text += f"{i}. {name}\n"
        if len(refs) > 10:
            text += f"... и еще {len(refs) - 10}\n"
    else:
        text += "Пока никого нет. Поделись ссылкой!"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    chat_id = message.chat.id
    now = time.time()
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ?", (chat_id,))
    total = c.fetchone()[0]
    c.execute("SELECT username, COUNT(*) FROM chat_stats WHERE chat_id = ? GROUP BY username ORDER BY COUNT(*) DESC LIMIT 10", (chat_id,))
    top_all = c.fetchall()
    c.execute("SELECT username, COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ? GROUP BY username ORDER BY COUNT(*) DESC LIMIT 5", (chat_id, now - 86400))
    top_24 = c.fetchall()
    c.execute("SELECT username, COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ? GROUP BY username ORDER BY COUNT(*) DESC LIMIT 5", (chat_id, now - 18000))
    top_5 = c.fetchall()
    conn.close()
    text = f"📊 <b>АНАЛИТИКА ЧАТА</b>\n\n<blockquote>💬 Всего сообщений: {total}</blockquote>\n"
    if top_all:
        text += "<b>🏆 Топ-10 за всё время:</b>\n<blockquote>"
        for i, (uname, cnt) in enumerate(top_all, 1):
            name = f"@{uname}" if uname else "Аноним"
            text += f"{i}. {name} — {cnt}\n"
        text += "</blockquote>\n"
    if top_24:
        text += "<b>📅 Топ-5 за 24 часа:</b>\n<blockquote>"
        for i, (uname, cnt) in enumerate(top_24, 1):
            name = f"@{uname}" if uname else "Аноним"
            text += f"{i}. {name} — {cnt}\n"
        text += "</blockquote>\n"
    if top_5:
        text += "<b>🕒 Топ-5 за 5 часов:</b>\n<blockquote>"
        for i, (uname, cnt) in enumerate(top_5, 1):
            name = f"@{uname}" if uname else "Аноним"
            text += f"{i}. {name} — {cnt}\n"
        text += "</blockquote>"
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("event"))
async def event_table(message: types.Message):
    start = get_event_start()
    left_days = EVENT_DAYS - (time.time() - start) / 86400
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT user_id, username, event_points FROM users ORDER BY event_points DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    text = f"🏆 <b>ИВЕНТ НА {EVENT_PRIZE} ЗВЁЗД</b>\nОсталось: <b>{max(0, int(left_days))} дней</b>\n\n<blockquote>"
    for i, (uid, uname, points) in enumerate(top, 1):
        text += f"{i}. @{uname or 'Аноним'} — {points/100:.0f} ⭐\n"
    text += "</blockquote>\n💡 <i>Каждая монета = 100 очков.</i>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("exchange"))
async def exchange(message: types.Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if len(args) < 1: return await message.reply("❌ /exchange [сумма]")
    try: iris_amount = int(args[0])
    except: return await message.reply("❌ Сумма числом.")
    if iris_amount <= 0: return await message.reply("❌ Больше нуля.")
    coins, iris, _, _, _, _, _, _, _, _ = get_user(message.from_user.id)
    if iris < iris_amount: return await message.reply(f"❌ У тебя только {iris} ирисок.")
    coins_to_add = iris_amount // 2
    if coins_to_add == 0: return await message.reply("❌ Минимум 2 ириски.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET iris = iris - ?, coins = coins + ? WHERE user_id = ?", (iris_amount, coins_to_add, message.from_user.id))
    conn.commit(); conn.close()
    await message.reply(f"✅ Обменял <b>{iris_amount}</b> ирисок на <b>{coins_to_add}</b> монет!", parse_mode="HTML")

@dp.message(Command("daily"))
async def daily_bonus(message: types.Message):
    _, _, _, _, _, last_daily, _, _, _, _ = get_user(message.from_user.id)
    now = time.time()
    if now - last_daily < 86400: return await message.reply("⏳ Жди 24ч.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + 30, last_daily = ? WHERE user_id = ?", (now, message.from_user.id))
    conn.commit(); conn.close()
    add_event(message.from_user.id, 30)
    await message.reply("🎁 +30 монет!")

@dp.message(Command("roulette"))
async def roulette(message: types.Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if len(args) < 1: return await message.reply("❌ /roulette [ставка]")
    try: bet = int(args[0])
    except: return await message.reply("❌ Ставка числом.")
    coins = get_user(message.from_user.id)[0]
    if coins < bet: return await message.reply("❌ Мало монет.")
    if bet < 5: return await message.reply("❌ Мин. ставка 5.")
    all_items = list(SHOP.keys())
    msg = await message.reply("🎰 <b>Крутим рулетку...</b>\n\n❓ | ❓ | ❓", parse_mode="HTML")
    try:
        await asyncio.sleep(1)
        await msg.edit_text(f"🎰 <b>Крутим рулетку...</b>\n\n{random.choice(all_items)} | ❓ | ❓", parse_mode="HTML")
        await asyncio.sleep(1)
        await msg.edit_text(f"🎰 <b>Крутим рулетку...</b>\n\n{random.choice(all_items)} | {random.choice(all_items)} | ❓", parse_mode="HTML")
        await asyncio.sleep(1)
    except: pass
    roll = [random.choice(all_items) for _ in range(3)]
    win = (roll[0] == roll[1] or roll[1] == roll[2] or roll[0] == roll[2])
    result_text = f"🎰 <b>Результат:</b>\n\n{roll[0]} | {roll[1]} | {roll[2]}\n\n"
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if win:
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (bet, message.from_user.id))
        result_text += f"🎉 <b>ПОБЕДА!</b> +{bet} монет!"
        add_event(message.from_user.id, bet)
    else:
        c.execute("UPDATE users SET coins = MAX(0, coins - ?) WHERE user_id = ?", (bet, message.from_user.id))
        result_text += f"😢 <b>Проигрыш.</b> -{bet} монет."
    conn.commit(); conn.close()
    try: await msg.edit_text(result_text + f"\n\n💰 Баланс: {get_user(message.from_user.id)[0]}", parse_mode="HTML")
    except: await message.answer(result_text + f"\n\n💰 Баланс: {get_user(message.from_user.id)[0]}", parse_mode="HTML")

@dp.message(Command("craft"))
async def craft_menu(message: types.Message):
    items = get_inv(message.from_user.id)
    if len(items) < 3: return await message.reply("❌ Для крафта нужно минимум 3 NFT.", parse_mode="HTML")
    builder = InlineKeyboardBuilder()
    for item_id, name in items:
        builder.row(InlineKeyboardButton(text=f"{name}", callback_data=f"craft_{item_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_craft"))
    await message.answer("🔨 <b>КРАФТ</b>\nВыбери NFT для улучшения:", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("craft_") and c.data != "close_craft")
async def craft_item(callback: types.CallbackQuery):
    item_id = int(callback.data.replace("craft_", ""))
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    res = c.fetchone(); conn.close()
    if not res: return await callback.answer("❌ NFT не найден.")
    name = res[0]
    base_name = name.split(" [")[0]
    base_price = SHOP[base_name]["price"] if base_name in SHOP else 10
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="+10 монет (Шанс 80%)", callback_data=f"do_craft_{item_id}_10"))
    builder.row(InlineKeyboardButton(text="+50 монет (Шанс 50%)", callback_data=f"do_craft_{item_id}_50"))
    builder.row(InlineKeyboardButton(text="+100 монет (Шанс 20%)", callback_data=f"do_craft_{item_id}_100"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="close_craft"))
    text = (f"🔨 <b>КРАФТ: {name}</b>\n\nТекущая цена: <b>{base_price}</b> монет\nВыбери, на сколько хочешь улучшить:")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("do_craft_"))
async def do_craft(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    item_id, add_price = int(parts[2]), int(parts[3])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    res = c.fetchone()
    if not res:
        conn.close()
        return await callback.answer("❌ NFT не найден.")
    name = res[0]
    base_name = name.split(" [")[0]
    await callback.message.edit_text("🔨 <b>Крафтим...</b>\n\n🔄 Плавим NFT в котле...", parse_mode="HTML")
    await asyncio.sleep(2)
    chance = 80 if add_price == 10 else (50 if add_price == 50 else 20)
    if random.randint(1, 100) <= chance:
        new_name = f"{base_name} [+{add_price} монет]"
        c.execute("UPDATE inventory SET item_name = ? WHERE id = ?", (new_name, item_id))
        conn.commit()
        await callback.message.edit_text(f"🎉 <b>УСПЕХ!</b>\nТвой NFT улучшен до: <b>{new_name}</b>", parse_mode="HTML")
    else:
        c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        conn.commit()
        await callback.message.edit_text(f"💥 <b>ПРОВАЛ!</b>\nТвой <b>{name}</b> сгорел в котле.", parse_mode="HTML")
    conn.close()

@dp.callback_query(lambda c: c.data == "close_craft")
async def close_craft(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.message(Command("shop"))
async def shop(message: types.Message):
    load_prices()
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    text = "🛒 <b>МАГАЗИН NFT</b>\n\nНажми на кнопку:"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP.items():
        c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (name,))
        sold = c.fetchone()[0]
        text += f"\n\n📦 <b>{name}</b>\n💰 {data['price']} монет (+{data['bonus']}%)\n📦 {sold}/{data['limit']}"
        builder.row(InlineKeyboardButton(text=f"Купить {name} ({data['price']} 🪙)", callback_data=f"buy_nft_{name}"))
    builder.row(InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_shop"))
    conn.close()
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("buy_nft_"))
async def buy_nft_callback(callback: types.CallbackQuery):
    item_name = callback.data.replace("buy_nft_", "")
    data = SHOP.get(item_name)
    if not data: return await callback.answer("❌ Нет такого.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (item_name,))
    if c.fetchone()[0] >= data["limit"]: conn.close(); return await callback.answer("❌ Распродано!", show_alert=True)
    if get_user(callback.from_user.id)[0] < data["price"]: conn.close(); return await callback.answer(f"❌ Мало монет!", show_alert=True)
    c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (data["price"], callback.from_user.id))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item_name))
    c.execute("UPDATE shop_sold SET sold_count = sold_count + 1 WHERE item_name = ?", (item_name,))
    if random.random() < 0.3:
        new_price = int(data["price"] * 1.02)
        data["price"] = new_price
        c.execute("UPDATE prices SET current_price = ? WHERE item_name = ?", (new_price, item_name))
    conn.commit(); conn.close()
    news = f"📰 <b>НОВОСТЬ!</b> {callback.from_user.first_name} скупил <b>{item_name}</b> за {data['price']} монет!"
    await broadcast(news)
    await callback.answer(f"✅ Куплено!", show_alert=True)

@dp.callback_query(lambda c: c.data == "close_shop")
async def close_shop(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.message(Command("inventory"))
async def inventory(message: types.Message):
    items = get_inv(message.from_user.id)
    if not items: return await message.reply("🎒 Пусто. /shop", parse_mode="HTML")
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n" + "\n".join([f"• {name} ID:{i}" for i, name in items])
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("sell"))
async def sell_item(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return await message.reply("❌ /sell Rocket 20")
    search_name = args[1].lower()
    item_name = next((k for k in SHOP.keys() if search_name in k.lower()), None)
    if not item_name: return await message.reply("❌ Нет такого.")
    try: price = int(args[2])
    except: return await message.reply("❌ Цена числом.")
    item_to_sell = next(((i, n) for i, n in get_inv(message.from_user.id) if n == item_name), None)
    if not item_to_sell: return await message.reply("❌ Нет такого у тебя.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE id = ?", (item_to_sell[0],))
    c.execute("INSERT INTO market (seller_id, item_name, price) VALUES (?, ?, ?)", (message.from_user.id, item_to_sell[1], price))
    conn.commit(); conn.close()
    await message.reply(f"✅ Выставлено за {price}! /market", parse_mode="HTML")

@dp.message(Command("market"))
async def market(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name, price FROM market WHERE status = 'active'")
    lots = c.fetchall(); conn.close()
    if not lots: return await message.reply("🏪 Пусто. /sell", parse_mode="HTML")
    text = "🏪 <b>РЫНОК</b>\n\n" + "\n".join([f"📦 {n} | 💰 {p} | 🆔 {i}" for i, n, p in lots])
    await message.answer(text + "\n\n💡 /buy [ID]", parse_mode="HTML")

@dp.message(Command("buy"))
async def buy_lot(message: types.Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): return await message.reply("❌ /buy [ID]")
    lot_id = int(args[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT seller_id, item_name, price FROM market WHERE id = ? AND status = 'active'", (lot_id,))
    lot = c.fetchone()
    if not lot: conn.close(); return await message.reply("❌ Нет лота.")
    s_id, name, price = lot
    if s_id == message.from_user.id: conn.close(); return await message.reply("❌ Свой лот.")
    if get_user(message.from_user.id)[0] < price: conn.close(); return await message.reply("❌ Мало монет.")
    builder = InlineKeyboardBuilder().row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"acc_{lot_id}_{message.from_user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dec_{lot_id}")
    )
    try:
        await bot.send_message(s_id, f"💰 Сделка! <b>{name}</b> за {price}.", reply_markup=builder.as_markup(), parse_mode="HTML")
        conn.close(); await message.reply("✅ Отправлено!")
    except:
        conn.close(); await message.reply("❌ Продавец не в боте.")

@dp.callback_query(lambda c: c.data.startswith("acc_"))
async def accept(callback: types.CallbackQuery):
    _, lot_id, b_id = callback.data.split("_")
    lot_id, b_id = int(lot_id), int(b_id)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT seller_id, item_name, price FROM market WHERE id = ? AND status = 'active'", (lot_id,))
    lot = c.fetchone()
    if not lot: conn.close(); await callback.message.edit_text("❌ Продано."); return
    s_id, name, price = lot
    if get_user(b_id)[0] < price: conn.close(); await callback.message.edit_text("❌ Нет денег."); return
    c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (price, b_id))
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, s_id))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (b_id, name))
    c.execute("UPDATE market SET status = 'sold' WHERE id = ?", (lot_id,))
    conn.commit(); conn.close()
    await callback.message.edit_text(f"✅ Продано {name} за {price}!")
    try: await bot.send_message(b_id, f"🎉 Куплено <b>{name}</b>!", parse_mode="HTML")
    except: pass

@dp.callback_query(lambda c: c.data.startswith("dec_"))
async def decline(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отклонено.")

@dp.message(Command("top"))
async def top_coins(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    if not top: return await message.answer("Пусто.")
    text = "🏆 <b>ТОП МОНЕТ</b>\n\n<blockquote>" + "".join([f"{'🥇' if i==1 else '🥈' if i==2 else '🥉' if i==3 else f'{i}.'} {f'@{u}' if u else f} — <b>{c}</b> 🪙\n" for i, (u, f, c) in enumerate(top, 1)]) + "</blockquote>"
    await message.answer(text + "\n💡 <i>Копи и покупай NFT.</i>", parse_mode="HTML")

@dp.message(Command("top_iris"))
async def top_iris(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, iris FROM users ORDER BY iris DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    if not top: return await message.answer("Пусто.")
    text = "🏆 <b>ТОП ИРИСОК</b>\n\n<blockquote>" + "".join([f"{'🥇' if i==1 else '🥈' if i==2 else '🥉' if i==3 else f'{i}.'} {f'@{u}' if u else f} — <b>{c}</b> 🍬\n" for i, (u, f, c) in enumerate(top, 1)]) + "</blockquote>"
    await message.answer(text + "\n💡 <i>Собирай ириски!</i>", parse_mode="HTML")

@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card, _, _, _, _, _ = get_user(user_id)
    now = time.time()
    if now - last_card < 300: return await message.reply(f"⏳ Жди: {int((300-(now-last_card))//60)}м.", parse_mode="HTML")
    msg = await message.reply("🎴 <b>Открываем карточку...</b>", parse_mode="HTML")
    try:
        await asyncio.sleep(1.5)
        await msg.edit_text("🔄 <b>Крутим барабаны...</b>", parse_mode="HTML")
        await asyncio.sleep(1.5)
        await msg.edit_text("✨ <b>Почти готово...</b>", parse_mode="HTML")
        await asyncio.sleep(1.5)
    except: pass
    base = random.randint(5, 10)
    bonus_p = get_bonus(user_id) / 100.0
    final = int(base * (1 + bonus_p))
    if random.random() < 0.05:
        final *= 5
        reward = f"🌟 <b>ЗОЛОТАЯ КАРТОЧКА!</b> x5\n🪙 +{final} монет!"
        nc, ni = coins + final, iris
        add_event(user_id, final)
    elif random.choice([True, False]):
        reward = f"🪙 +{final} монет!"
        nc, ni = coins + final, iris
        add_event(user_id, final)
    else:
        reward = f"🍬 +{final} ирисок!"
        nc, ni = coins, iris + final
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = ?, iris = ?, xp = xp + 5, last_card = ? WHERE user_id = ?", (nc, ni, now, user_id))
    conn.commit(); conn.close()
    try:
        await msg.edit_text(f"🎉 <b>Карточка открыта!</b>\n<blockquote>{reward}</blockquote>\n💡 <i>Покупай NFT в /shop.</i>", parse_mode="HTML")
    except:
        await message.answer(f"🎉 <b>Карточка открыта!</b>\n<blockquote>{reward}</blockquote>\n💡 <i>Покупай NFT в /shop.</i>", parse_mode="HTML")

@dp.message(Command("clan_create"))
async def clan_create(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("/clan_create [Название]")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    try:
        c.execute("INSERT INTO clans (name, owner_id, members) VALUES (?, ?, ?)", (args[1], message.from_user.id, str(message.from_user.id)))
        conn.commit(); await message.reply(f"🛡 Клан <b>{args[1]}</b> создан!", parse_mode="HTML")
    except: await message.reply("❌ Уже есть.")
    conn.close()

@dp.message(Command("clan_info"))
async def clan_info(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("❌ /clan_info [Название]")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT owner_id, members FROM clans WHERE name = ?", (args[1],))
    res = c.fetchone(); conn.close()
    if not res: return await message.reply("❌ Не найден.")
    await message.reply(f"🛡 <b>{args[1]}</b>\n👑 Лидер: <code>{res[0]}</code>\n👥 Участников: {len(res[1].split(','))}", parse_mode="HTML")

@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message: return await message.reply("❌ Нет прав.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 3600)
        await message.reply("🤐 Замучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message: return await message.reply("❌ Нет прав.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply("🔊 Размучен.")
    except: pass

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message: return await message.reply("❌ Нет прав.")
    try: await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id); await message.reply("🔨 Забанен.")
    except: pass

@dp.message(Command("kick"))
async def kick_user(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message: return await message.reply("❌ Нет прав.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply("👢 Кикнут.")
    except: pass

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ /unban ID")
    try: await bot.unban_chat_member(message.chat.id, int(args[1])); await message.reply("🔓 Разбанен.")
    except: pass

@dp.message(Command("close_chat"))
async def close_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try: await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False)); await message.reply("🔒 Закрыт.")
    except: pass

@dp.message(Command("open_chat"))
async def open_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try: await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)); await message.reply("🔓 Открыт.")
    except: pass

@dp.message(Command("clear"))
async def clear_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await message.delete()
    deleted = 0
    for i in range(1, count + 1):
        try: await bot.delete_message(message.chat.id, message.message_id - i); deleted += 1; await asyncio.sleep(0.1)
        except: pass
    msg = await message.answer(f"🧹 Очищено: {deleted}")
    await asyncio.sleep(3); await msg.delete()

@dp.message(lambda message: message.from_user and message.from_user.is_bot)
async def check_muted_bots(message: types.Message):
    if message.chat.type == "private": return
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT 1 FROM muted_bots WHERE chat_id = ? AND (bot_id = ? OR bot_id = 0)", (message.chat.id, message.from_user.id))
    if c.fetchone():
        try: await message.delete()
        except: pass
    conn.close()

@dp.message(Command("mute_bot"))
async def mute_bot(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message or not message.reply_to_message.from_user.is_bot: return await message.reply("❌ Ответь на бота.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, ?)", (message.chat.id, message.reply_to_message.from_user.id))
    conn.commit(); conn.close()
    await message.reply("🤐 Заглушен.")

@dp.message(Command("mute_all_bots"))
async def mute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, 0)", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🤐 Все боты.")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🔊 Все разглушены.")

@dp.message(Command("add_admin"))
async def add_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return await message.reply("❌ Только владелец.")
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): return await message.reply("❌ /add_admin ID")
    tid = int(args[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if not c.execute("SELECT 1 FROM users WHERE user_id = ?", (tid,)).fetchone():
        conn.close(); return await message.reply("❌ Юзер не в боте.")
    c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (tid,)); conn.commit(); conn.close()
    await message.reply(f"✅ {tid} админ.")
    try: await bot.send_message(tid, "👑 <b>Вас назначили администратором бота!</b>", parse_mode="HTML")
    except: pass

@dp.message(Command("remove_admin"))
async def remove_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return await message.reply("❌ Только владелец.")
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): return await message.reply("❌ /remove_admin ID")
    tid = int(args[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (tid,)); conn.commit(); conn.close()
    await message.reply(f"✅ {tid} снят.")
    try: await bot.send_message(tid, "❌ Вас сняли с админа.")
    except: pass

@dp.message(Command("admin_list"))
async def admin_list(message: types.Message):
    if message.from_user.id != ADMIN_ID: return await message.reply("❌ Только владелец.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT user_id, username, first_name FROM users WHERE is_admin = 1")
    admins = c.fetchall(); conn.close()
    if not admins: return await message.reply("👑 Нет админов.")
    text = "👑 <b>АДМИНЫ:</b>\n\n" + "\n".join([f"• {f'@{u}' if u else f} (<code>{i}</code>)" for i, u, f in admins])
    await message.reply(text, parse_mode="HTML")

@dp.message(lambda m: m.text and not m.text.startswith("/") and not m.text.startswith("."))
async def track_stats(message: types.Message):
    if message.chat.type == "private" or message.from_user.is_bot: return
    update_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO chat_stats (chat_id, user_id, username, timestamp) VALUES (?, ?, ?, ?)", (message.chat.id, message.from_user.id, message.from_user.username, time.time()))
    conn.commit(); conn.close()

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    asyncio.create_task(market_fluct())
    asyncio.create_task(check_event())
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
