import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9209660223:AAGgLkyjHQ1UYlkNh30ysYYA4YceSOoMGxc"
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- НАСТРОЙКИ МАГАЗИНА (БАЗОВЫЕ ЦЕНЫ) ---
BASE_SHOP_ITEMS = {
    "🚀 Rocket Dog #18": {"base_price": 10, "limit": 15, "bonus": 10.0},
    "💎 Diamond Dog #22": {"base_price": 23, "limit": 10, "bonus": 10.3},
    "🍾 Bottle #1": {"base_price": 25, "limit": 70, "bonus": 3.0},
    "🪄 Wand #4": {"base_price": 70, "limit": 145, "bonus": 14.2},
    "🪔 Lamp #7": {"base_price": 120, "limit": 35, "bonus": 19.2},
    "🏅 Medal #9": {"base_price": 44, "limit": 45, "bonus": 11.1},
    "🛟 Lifebuoy #3": {"base_price": 50, "limit": 90, "bonus": 12.8}
}

SHOP_ITEMS = {}

# --- ФЛАСК ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT, 
                 first_name TEXT,
                 coins INTEGER DEFAULT 0, 
                 iris INTEGER DEFAULT 0,
                 xp INTEGER DEFAULT 0,
                 level INTEGER DEFAULT 1,
                 last_card REAL DEFAULT 0,
                 last_daily REAL DEFAULT 0,
                 is_admin INTEGER DEFAULT 0,
                 referrer_id INTEGER DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_sold (item_name TEXT PRIMARY KEY, sold_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_name TEXT, price INTEGER, status TEXT DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted_bots (chat_id INTEGER, bot_id INTEGER, PRIMARY KEY (chat_id, bot_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS clans (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, owner_id INTEGER, members TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, username TEXT, timestamp REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS prices (item_name TEXT PRIMARY KEY, current_price INTEGER)''')
    
    for name, data in BASE_SHOP_ITEMS.items():
        c.execute("INSERT OR IGNORE INTO shop_sold (item_name, sold_count) VALUES (?, 0)", (name,))
        c.execute("INSERT OR IGNORE INTO prices (item_name, current_price) VALUES (?, ?)", (name, data["base_price"]))
        SHOP_ITEMS[name] = {"price": data["base_price"], "limit": data["limit"], "bonus": data["bonus"], "base_price": data["base_price"]}
    conn.commit(); conn.close()

def load_current_prices():
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name, current_price FROM prices")
    for name, price in c.fetchall():
        if name in SHOP_ITEMS:
            SHOP_ITEMS[name]["price"] = price
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, iris, xp, level, last_card, last_daily, is_admin, referrer_id FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (0, 0, 0, 1, 0, 0, 0, None)
    conn.close(); return res

def update_user_info(user_id, username, first_name):
    conn = sqlite3.connect('bot.db')
    conn.execute(
        "INSERT INTO users (user_id, username, first_name) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
        (user_id, username, first_name))
    conn.commit(); conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall(); conn.close()
    return items

def get_total_bonus(user_id):
    items = get_inventory(user_id)
    bonus = 0.0
    for _, item in items:
        if item in SHOP_ITEMS:
            bonus += SHOP_ITEMS[item]["bonus"]
    return bonus

def find_shop_item(text):
    text = text.lower()
    for key in SHOP_ITEMS.keys():
        if text in key.lower():
            return key
    return None

def get_rank(coins):
    if coins < 50: return "🥉 Новичок"
    elif coins < 150: return "🥈 Любитель"
    elif coins < 500: return "🥇 Профи"
    else: return "👑 Магнат"

async def is_admin(message: types.Message):
    if message.from_user.id == ADMIN_ID: return True
    return get_user(message.from_user.id)[6] == 1

# --- МЕХАНИКА РЫНКА (ПАДЕНИЕ ЦЕН) ---
async def market_fluctuation():
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(3600 * 6) 
        if not SHOP_ITEMS: continue
        item_name = random.choice(list(SHOP_ITEMS.keys()))
        item_data = SHOP_ITEMS[item_name]
        current = item_data["price"]
        base = item_data["base_price"]
        drop_percent = random.uniform(0.10, 0.15)
        new_price = max(int(current * (1 - drop_percent)), int(base * 0.5))
        if new_price < current:
            item_data["price"] = new_price
            conn = sqlite3.connect('bot.db'); c = conn.cursor()
            c.execute("UPDATE prices SET current_price = ? WHERE item_name = ?", (new_price, item_name))
            conn.commit(); conn.close()
            print(f"📉 Рынок: {item_name} подешевел до {new_price}")

# --- ИНСТРУКЦИЯ ---
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        f"📖 <b>ИНСТРУКЦИЯ</b>\n\n"
        f"<b>🎮 Игры:</b>\n"
        f"• <b>.карточка</b> — открыть (5 мин, шанс на золотую x5)\n"
        f"• <b>/roulette [красное/зеленое] [ставка]</b> — рулетка\n"
        f"• <b>/daily</b> — ежедневный бонус (+30 монет)\n"
        f"• <b>/duel</b> — дуэль на кубиках (ответом)\n\n"
        f"<b>👤 Экономика:</b>\n"
        f"• <b>/profile</b> — профиль и ранг\n"
        f"• <b>/top</b> — топ по монетам\n"
        f"• <b>/top_iris</b> — топ по ирискам\n"
        f"• <b>/shop</b> — магазин NFT\n"
        f"• <b>/inventory</b> — твои NFT\n"
        f"• <b>/ref</b> — реферальный кабинет\n\n"
        f"<b>🏪 Рынок:</b>\n"
        f"• <b>/sell [Название] [Цена]</b>\n"
        f"• <b>/market</b>\n"
        f"• <b>/buy [ID]</b>\n\n"
        f"<b>🛡 Кланы:</b>\n"
        f"• <b>/clan_create [Название]</b>\n"
        f"• <b>/clan_info [Название]</b>\n\n"
        f"<b>📊 Аналитика:</b>\n"
        f"• <b>/stats</b> — полный отчет по чату\n\n"
        f"<b>🔨 Модерация (админы):</b>\n"
        f"• <b>/mute</b>, <b>/unmute</b>, <b>/ban</b>, <b>/kick</b>, <b>/unban</b>\n"
        f"• <b>/clear [число]</b>\n"
        f"• <b>/close_chat</b>, <b>/open_chat</b>\n"
        f"• <b>/mute_bot</b>, <b>/mute_all_bots</b>, <b>/unmute_all_bots</b>\n\n"
        f"<b>👑 Управление (владелец):</b>\n"
        f"• <b>/add_admin [ID]</b>, <b>/remove_admin [ID]</b>, <b>/admin_list</b>"
    )
    await message.answer(text, parse_mode="HTML")

# --- РАСШИРЕННАЯ АНАЛИТИКА ---
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    chat_id = message.chat.id
    now = time.time()
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ?", (chat_id,))
    total_msgs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, now - 18000))
    count_5h = c.fetchone()[0]
    c.execute("SELECT username, COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ? GROUP BY username ORDER BY COUNT(*) DESC LIMIT 3", (chat_id, now - 18000))
    top_5h = c.fetchall()
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, now - 86400))
    count_24h = c.fetchone()[0]
    c.execute("SELECT username, COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ? GROUP BY username ORDER BY COUNT(*) DESC LIMIT 3", (chat_id, now - 86400))
    top_24h = c.fetchall()
    conn.close()
    
    text = (f"📊 <b>ПОЛНАЯ АНАЛИТИКА</b>\n\n<blockquote>💬 Всего: {total_msgs}</blockquote>\n"
            f"<b>🕒 За 5ч:</b> {count_5h} сообщений\n")
    for i, (u, cnt) in enumerate(top_5h, 1):
        text += f"{i}. @{u or 'Аноним'} — {cnt}\n"
    text += f"\n<b>📅 За 24ч:</b> {count_24h} сообщений\n"
    for i, (u, cnt) in enumerate(top_24h, 1):
        text += f"{i}. @{u or 'Аноним'} — {cnt}\n"
    await message.reply(text, parse_mode="HTML")

# --- РУЛЕТКА ---
@dp.message(Command("roulette"))
async def roulette(message: types.Message, command: CommandObject):
    args = command.args.split() if command.args else []
    if len(args) < 2: return await message.reply("❌ /roulette [красное/зеленое] [ставка]")
    color = args[0].lower()
    if color not in ["красное", "зеленое"]: return await message.reply("❌ Красное или зеленое.")
    try: bet = int(args[1])
    except: return await message.reply("❌ Ставка числом.")
    coins = get_user(message.from_user.id)[0]
    if coins < bet: return await message.reply("❌ Мало монет.")
    if bet < 5: return await message.reply("❌ Мин. ставка 5.")
    
    result = random.choice(["красное", "зеленое"])
    win = result == color
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if win:
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (bet, message.from_user.id))
        text = f"🎡 {result.upper()}! 🎉 +{bet}"
    else:
        c.execute("UPDATE users SET coins = MAX(0, coins - ?) WHERE user_id = ?", (bet, message.from_user.id))
        text = f"🎡 {result.upper()}. 😢 -{bet}"
    conn.commit(); conn.close()
    await message.reply(f"{text}\n💰 Баланс: {get_user(message.from_user.id)[0]}", parse_mode="HTML")

# --- РЕФЕРАЛЬНЫЙ КАБИНЕТ ---
@dp.message(Command("ref"))
async def ref_cabinet(message: types.Message):
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={message.from_user.id}"
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (message.from_user.id,))
    count = c.fetchone()[0]; conn.close()
    await message.reply(f"👥 <b>РЕФЕРАЛКА</b>\n\n🔗 <code>{ref_link}</code>\n\n👤 Друзей: {count}", parse_mode="HTML")

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    get_user(user_id)
    update_user_info(user_id, message.from_user.username, message.from_user.first_name)
    if command.args and command.args.isdigit():
        ref = int(command.args)
        if ref != user_id:
            conn = sqlite3.connect('bot.db'); c = conn.cursor()
            c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
            res = c.fetchone()
            if res and res[0] is None:
                c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref, user_id))
                c.execute("UPDATE users SET coins = coins + 10 WHERE user_id = ?", (ref,))
                conn.commit()
                try: await bot.send_message(ref, "🎉 Новый реферал! +10 монет.")
                except: pass
            conn.close()
    await message.answer("👋 Привет! /help — команды.\n💡 <i>Совет: .карточка — доход.</i>", parse_mode="HTML")

# --- ЕЖЕДНЕВНЫЙ БОНУС ---
@dp.message(Command("daily"))
async def daily_bonus(message: types.Message):
    _, _, _, _, _, last_daily, _, _ = get_user(message.from_user.id)
    now = time.time()
    if now - last_daily < 86400: return await message.reply("⏳ Жди 24ч.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + 30, last_daily = ? WHERE user_id = ?", (now, message.from_user.id))
    conn.commit(); conn.close()
    await message.reply("🎁 +30 монет!")

# --- ДУЭЛЬ ---
@dp.message(Command("duel"))
async def duel_dice(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение друга.")
    opp = message.reply_to_message.from_user
    if opp.id == message.from_user.id or opp.is_bot: return
    bet = 20
    if get_user(message.from_user.id)[0] < bet or get_user(opp.id)[0] < bet: return await message.reply("❌ Нужно 20 монет.")
    p1, p2 = random.randint(1, 6), random.randint(1, 6)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if p1 > p2:
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (bet, message.from_user.id))
        c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (bet, opp.id))
        res = f"⚔️ {message.from_user.first_name}: {p1} | {opp.first_name}: {p2}\n🏆 Победил {message.from_user.first_name}!"
    elif p1 < p2:
        c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (bet, message.from_user.id))
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (bet, opp.id))
        res = f"⚔️ {message.from_user.first_name}: {p1} | {opp.first_name}: {p2}\n🏆 Победил {opp.first_name}!"
    else: res = f"⚔️ {p1} | {p2}\n🤝 Ничья!"
    conn.commit(); conn.close()
    await message.reply(res, parse_mode="HTML")

# --- МАГАЗИН ---
@dp.message(Command("shop"))
async def shop(message: types.Message):
    load_current_prices()
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    for name, data in SHOP_ITEMS.items():
        c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (name,))
        sold = c.fetchone()[0]
        text += f"📦 <b>{name}</b>\n💰 {data['price']} монет (база {data['base_price']})\n📈 +{data['bonus']}%\n📦 {sold}/{data['limit']}\n\n"
    conn.close()
    await message.answer(text + "💡 <i>Совет: рынок иногда падает, следи за ценами!</i>", parse_mode="HTML")

@dp.message(Command("buy_shop"))
async def buy_shop(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return
    item_name = find_shop_item(args[1].strip())
    if not item_name: return await message.reply("❌ Нет такого.")
    data = SHOP_ITEMS[item_name]
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (item_name,))
    if c.fetchone()[0] >= data["limit"]: conn.close(); return await message.reply("❌ Распродано!")
    if get_user(message.from_user.id)[0] < data["price"]: conn.close(); return await message.reply("❌ Мало монет!")
    
    c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (data["price"], message.from_user.id))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (message.from_user.id, item_name))
    c.execute("UPDATE shop_sold SET sold_count = sold_count + 1 WHERE item_name = ?", (item_name,))
    conn.commit(); conn.close()
    
    if random.random() < 0.2:
        new_price = int(data["price"] * 1.05)
        data["price"] = new_price
        conn = sqlite3.connect('bot.db'); c = conn.cursor()
        c.execute("UPDATE prices SET current_price = ? WHERE item_name = ?", (new_price, item_name))
        conn.commit(); conn.close()
        await message.reply(f"✅ Куплено <b>{item_name}</b> за {data['price']}!\n📈 Спрос вырос, цена поднялась до {new_price}!", parse_mode="HTML")
    else:
        await message.reply(f"✅ Куплено <b>{item_name}</b> за {data['price']}!\n💡 <i>Совет: /inventory</i>", parse_mode="HTML")

@dp.message(Command("inventory"))
async def inventory(message: types.Message):
    items = get_inventory(message.from_user.id)
    if not items: return await message.reply("🎒 Пусто. /shop", parse_mode="HTML")
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n" + "\n".join([f"• {name} (+{SHOP_ITEMS[name]['bonus']}%) ID:{i}" for i, name in items])
    await message.reply(text, parse_mode="HTML")

# --- РЫНОК ---
@dp.message(Command("sell"))
async def sell_item(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return await message.reply("❌ /sell rocket 20")
    item_name = find_shop_item(args[1].strip())
    try: price = int(args[2])
    except: return await message.reply("❌ Цена числом.")
    item_to_sell = next(((i, n) for i, n in get_inventory(message.from_user.id) if n == item_name), None)
    if not item_to_sell: return await message.reply("❌ Нет такого.")
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

# --- ПРОФИЛЬ ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    coins, iris, xp, level, _, _, is_admin, _ = get_user(target.id)
    rank = get_rank(coins)
    bonus = get_total_bonus(target.id)
    needed_xp = level * 5000
    bar = "█" * min(int((xp / needed_xp) * 10), 10) + "░" * (10 - min(int((xp / needed_xp) * 10), 10))
    status = "👑 Админ" if is_admin else "👤 Игрок"
    text = (f"👤 <b>ПРОФИЛЬ {target.first_name}</b>\n\n🆔 <code>{target.id}</code>\n🛡 {status}\n🏅 Ранг: <b>{rank}</b>\n📈 Ур: <b>{level}</b> [{bar}] ({xp}/{needed_xp})\n\n🪙 Монеты: <b>{coins}</b>\n🍬 Ириски: <b>{iris}</b>\n🎁 Бонус: <b>+{bonus:.1f}%</b>\n\n💡 <i>Совет: .карточка — доход.</i>")
    await message.answer(text, parse_mode="HTML")

# --- ТОПЫ ---
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

# --- КАРТОЧКА ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card, _, _, _ = get_user(user_id)
    now = time.time()
    if now - last_card < 300: return await message.reply(f"⏳ Жди: {int((300-(now-last_card))//60)}м.", parse_mode="HTML")
    msg = await message.reply("🎴 <b>Открываем...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🔄 <b>Крутим...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    base = random.randint(5, 10)
    bonus_p = get_total_bonus(user_id) / 100.0
    final = int(base * (1 + bonus_p))
    if random.random() < 0.05:
        final *= 5
        reward = f"🌟 <b>ЗОЛОТАЯ!</b> x5\n🪙 +{final} монет!"
        nc, ni = coins + final, iris
    elif random.choice([True, False]):
        reward = f"🪙 +{final} монет!"
        nc, ni = coins + final, iris
    else:
        reward = f"🍬 +{final} ирисок!"
        nc, ni = coins, iris + final
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = ?, iris = ?, xp = xp + 5, last_card = ? WHERE user_id = ?", (nc, ni, now, user_id))
    conn.commit(); conn.close()
    await msg.edit_text(f"🎉 <b>Открыто!</b>\n<blockquote>{reward}</blockquote>\n💡 <i>Покупай NFT в /shop.</i>", parse_mode="HTML")

# --- КЛАНЫ ---
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

# --- МОДЕРАЦИЯ ---
@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_admin(message) or not message.reply_to_message: return await message.reply("❌ Нет прав или нет ответа.")
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

# --- ГЛУШИЛКА БОТОВ ---
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
    conn.commit(); conn.close(); await message.reply("🤐 Заглушен.")

@dp.message(Command("mute_all_bots"))
async def mute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, 0)", (message.chat.id,))
    conn.commit(); conn.close(); await message.reply("🤐 Все боты.")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close(); await message.reply("🔊 Все разглушены.")

# --- УПРАВЛЕНИЕ АДМИНАМИ ---
@dp.message(Command("add_admin"))
async def add_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return await message.reply("❌ Только владелец.")
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): return await message.reply("❌ /add_admin ID")
    target_id = int(args[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if not c.execute("SELECT 1 FROM users WHERE user_id = ?", (target_id,)).fetchone():
        conn.close(); return await message.reply("❌ Юзер не в боте.")
    c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_id,)); conn.commit(); conn.close()
    await message.reply(f"✅ {target_id} админ.")
    try: await bot.send_message(target_id, "👑 <b>Вас назначили администратором бота!</b>", parse_mode="HTML")
    except: pass

@dp.message(Command("remove_admin"))
async def remove_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return await message.reply("❌ Только владелец.")
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): return await message.reply("❌ /remove_admin ID")
    target_id = int(args[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_id,)); conn.commit(); conn.close()
    await message.reply(f"✅ {target_id} снят.")
    try: await bot.send_message(target_id, "❌ Вас сняли с админа.")
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

# --- СЧЕТЧИК ---
@dp.message(lambda m: m.text and not m.text.startswith("/") and not m.text.startswith("."))
async def track_stats(message: types.Message):
    if message.chat.type == "private" or message.from_user.is_bot: return
    update_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO chat_stats (chat_id, user_id, username, timestamp) VALUES (?, ?, ?, ?)", (message.chat.id, message.from_user.id, message.from_user.username, time.time()))
    conn.commit(); conn.close()

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    asyncio.create_task(market_fluctuation())
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
