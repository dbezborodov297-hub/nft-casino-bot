import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9209660223:AAEch3uBXtWKwwnRV8tJCGS0sxH1_R-5_wg" 
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- НАСТРОЙКИ МАГАЗИНА ---
SHOP_ITEMS = {
    "🚀 Rocket Dog #18": {"price": 10, "limit": 15, "bonus": 10.0},
    "💎 Diamond Dog #22": {"price": 23, "limit": 10, "bonus": 10.3}
}

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
                 last_card REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_sold (
                 item_name TEXT PRIMARY KEY,
                 sold_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 seller_id INTEGER,
                 item_name TEXT,
                 price INTEGER,
                 status TEXT DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted_bots (
                 chat_id INTEGER, 
                 bot_id INTEGER, 
                 PRIMARY KEY (chat_id, bot_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS clans (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT UNIQUE,
                 owner_id INTEGER,
                 members TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_stats (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 chat_id INTEGER,
                 user_id INTEGER,
                 timestamp REAL)''')
    
    for item in SHOP_ITEMS:
        c.execute("INSERT OR IGNORE INTO shop_sold (item_name, sold_count) VALUES (?, 0)", (item,))
        
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, iris, xp, level, last_card FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (0, 0, 0, 1, 0)
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
        key_lower = key.lower()
        if text in key_lower or ("rocket" in text and "rocket" in key_lower) or ("ракет" in text and "rocket" in key_lower) or ("diamond" in text and "diamond" in key_lower) or ("алмаз" in text and "diamond" in key_lower):
            return key
    return None

async def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID

# --- ИНСТРУКЦИЯ ---
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        f"📖 <b>ИНСТРУКЦИЯ</b>\n\n"
        f"<b>Экономика:</b>\n"
        f"• <b>.карточка</b> — открыть (раз в 5 минут, 5-10 монет/ирисок + бонус)\n"
        f"• <b>/profile</b> — профиль\n"
        f"• <b>/top</b> — топ по монетам\n"
        f"• <b>/top_iris</b> — топ по ирискам\n"
        f"• <b>/shop</b> — магазин NFT\n"
        f"• <b>/inventory</b> — твои NFT\n\n"
        f"<b>Рынок (P2P):</b>\n"
        f"• <b>/sell [Название] [Цена]</b> — выставить NFT\n"
        f"• <b>/market</b> — все лоты\n"
        f"• <b>/buy [ID]</b> — купить лот\n\n"
        f"<b>Кланы:</b>\n"
        f"• <b>/clan_create [Название]</b>\n"
        f"• <b>/clan_info [Название]</b>\n\n"
        f"<b>Аналитика:</b>\n"
        f"• <b>/stats</b>\n\n"
        f"<b>Модерация (только для тебя):</b>\n"
        f"• <b>/mute</b>, <b>/unmute</b>, <b>/ban</b>, <b>/kick</b>, <b>/unban</b>\n"
        f"• <b>/clear [число]</b>\n"
        f"• <b>/close_chat</b>, <b>/open_chat</b>\n"
        f"• <b>/mute_bot</b>, <b>/mute_all_bots</b>, <b>/unmute_all_bots</b>\n\n"
        f"💡 <b>СОВЕТ:</b> Покупай NFT командой <code>/buy_shop rocket</code> или <code>/buy_shop diamond</code>."
    )
    await message.answer(text, parse_mode="HTML")

# --- МАГАЗИН ---
@dp.message(Command("shop"))
async def shop(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    for name, data in SHOP_ITEMS.items():
        c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (name,))
        sold = c.fetchone()[0]
        text += f"📦 <b>{name}</b>\n"
        text += f"💰 Цена: {data['price']} монет\n"
        text += f"📈 Бонус к прибыли: +{data['bonus']}%\n"
        text += f"📦 Продано: {sold}/{data['limit']}\n\n"
    conn.close()
    text += "💡 Купить: <code>/buy_shop rocket</code> или <code>/buy_shop diamond</code>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("buy_shop"))
async def buy_shop(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("❌ Используй: /buy_shop rocket (или diamond)")
    
    item_name = find_shop_item(args[1].strip())
    if not item_name: return await message.reply("❌ Нет такого предмета.")
    
    data = SHOP_ITEMS[item_name]
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (item_name,))
    sold = c.fetchone()[0]
    if sold >= data["limit"]:
        conn.close(); return await message.reply(f"❌ {item_name} распродан!")
    
    coins, _, _, _, _ = get_user(message.from_user.id)
    if coins < data["price"]:
        conn.close(); return await message.reply(f"❌ Не хватает монет! Нужно {data['price']}.")
    
    c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (data["price"], message.from_user.id))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (message.from_user.id, item_name))
    c.execute("UPDATE shop_sold SET sold_count = sold_count + 1 WHERE item_name = ?", (item_name,))
    conn.commit(); conn.close()
    
    await message.reply(
        f"✅ Ты купил <b>{item_name}</b> за {data['price']} монет!\n"
        f"Теперь каждый раз, когда ты открываешь <b>.карточку</b>, ты получаешь на <b>{data['bonus']}%</b> больше!\n\n"
        f"💡 <i>Совет: открой /inventory, чтобы увидеть свои NFT.</i>", 
        parse_mode="HTML"
    )

@dp.message(Command("inventory"))
async def inventory(message: types.Message):
    items = get_inventory(message.from_user.id)
    bonus = get_total_bonus(message.from_user.id)
    if not items: 
        return await message.reply("🎒 Инвентарь пуст.\n💡 <i>Совет: зайди в /shop и купи Ракету за 10 монет.</i>", parse_mode="HTML")
    
    text = "🎒 <b>ТВОЙ ИНВЕНТАРЬ</b>\n\n"
    for item_id, name in items:
        text += f"• {name} (+{SHOP_ITEMS[name]['bonus']}%) — ID: <code>{item_id}</code>\n"
    text += f"\n📈 <b>Общий бонус:</b> +{bonus:.1f}%"
    text += f"\n\n💡 <i>Совет: если предмет не нужен, продай его на рынке командой /sell.</i>"
    await message.reply(text, parse_mode="HTML")

# --- РЫНОК (P2P) ---
@dp.message(Command("sell"))
async def sell_item(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return await message.reply("❌ Используй: /sell rocket 20")
    
    item_name = find_shop_item(args[1].strip())
    if not item_name: return await message.reply("❌ Нет такого предмета.")
    
    try: price = int(args[2])
    except: return await message.reply("❌ Цена должна быть числом.")
    
    items = get_inventory(message.from_user.id)
    item_to_sell = None
    for item_id, name in items:
        if name == item_name:
            item_to_sell = (item_id, name)
            break
            
    if not item_to_sell: return await message.reply(f"❌ У тебя нет {item_name}.")
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE id = ?", (item_to_sell[0],))
    c.execute("INSERT INTO market (seller_id, item_name, price) VALUES (?, ?, ?)", (message.from_user.id, item_to_sell[1], price))
    conn.commit(); conn.close()
    
    await message.reply(
        f"✅ Ты выставил <b>{item_to_sell[1]}</b> на рынок за <b>{price}</b> монет!\n\n"
        f"💡 <i>Совет: если хочешь продать быстрее, поставь цену ниже, чем в /shop.</i>", 
        parse_mode="HTML"
    )

@dp.message(Command("market"))
async def market(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, seller_id, item_name, price FROM market WHERE status = 'active'")
    lots = c.fetchall(); conn.close()
    
    if not lots: 
        return await message.reply("🏪 Рынок пуст.\n💡 <i>Совет: ты можешь стать первым! Выставь свой NFT через /sell.</i>", parse_mode="HTML")
    
    text = "🏪 <b>РЫНОК NFT</b>\n\n"
    for lot_id, seller_id, item_name, price in lots:
        text += f"📦 <b>{item_name}</b>\n"
        text += f"💰 Цена: {price} монет\n"
        text += f"🆔 Лот: <code>{lot_id}</code>\n\n"
    text += "Купить: <code>/buy [ID]</code>\n\n"
    text += "💡 <i>Совет: покупая тут, ты даешь заработать другому игроку.</i>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("buy"))
async def buy_lot(message: types.Message):
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ Используй: /buy [ID лота]")
    try: lot_id = int(args[1])
    except: return await message.reply("❌ ID должен быть числом.")
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT seller_id, item_name, price FROM market WHERE id = ? AND status = 'active'", (lot_id,))
    lot = c.fetchone()
    
    if not lot:
        conn.close(); return await message.reply("❌ Лот не найден или уже продан.")
    
    seller_id, item_name, price = lot
    if seller_id == message.from_user.id:
        conn.close(); return await message.reply("❌ Нельзя купить свой лот.")
    
    coins, _, _, _, _ = get_user(message.from_user.id)
    if coins < price:
        conn.close(); return await message.reply(f"❌ Не хватает монет! Нужно {price}.")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{lot_id}_{message.from_user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{lot_id}")
    )
    
    try:
        await bot.send_message(
            seller_id, 
            f"💰 <b>Новая сделка!</b>\n\n"
            f"Покупатель хочет купить твой <b>{item_name}</b> за <b>{price}</b> монет.\n"
            f"Принять?", 
            reply_markup=builder.as_markup(), 
            parse_mode="HTML"
        )
        conn.close()
        await message.reply("✅ Запрос отправлен продавцу. Жди ответа!\n💡 <i>Совет: не выходи из бота, чтобы быстрее увидеть ответ.</i>", parse_mode="HTML")
    except:
        conn.close()
        await message.reply("❌ Не удалось отправить запрос продавцу (он не начинал диалог с ботом).")

@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_deal(callback: types.CallbackQuery):
    _, lot_id, buyer_id = callback.data.split("_")
    lot_id, buyer_id = int(lot_id), int(buyer_id)
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT seller_id, item_name, price FROM market WHERE id = ? AND status = 'active'", (lot_id,))
    lot = c.fetchone()
    
    if not lot:
        conn.close(); await callback.message.edit_text("❌ Лот уже продан."); return
    
    seller_id, item_name, price = lot
    buyer_coins = get_user(buyer_id)[0]
    if buyer_coins < price:
        conn.close(); await callback.message.edit_text("❌ У покупателя не хватает монет."); return
    
    c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (price, buyer_id))
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, seller_id))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (buyer_id, item_name))
    c.execute("UPDATE market SET status = 'sold' WHERE id = ?", (lot_id,))
    conn.commit(); conn.close()
    
    await callback.message.edit_text(f"✅ Сделка совершена! Ты продал {item_name} за {price} монет.")
    try:
        await bot.send_message(buyer_id, f"🎉 Ты купил <b>{item_name}</b> за {price} монет!", parse_mode="HTML")
    except: pass

@dp.callback_query(lambda c: c.data.startswith("decline_"))
async def decline_deal(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Сделка отклонена.")

# --- ПРОФИЛЬ ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    coins, iris, xp, level, last_card = get_user(target.id)
    bonus = get_total_bonus(target.id)
    needed_xp = level * 5000
    progress = min(int((xp / needed_xp) * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    text = (f"👤 <b>ПРОФИЛЬ {target.first_name}</b>\n\n"
            f"🆔 <code>{target.id}</code>\n"
            f"📈 Уровень: <b>{level}</b>\n"
            f"✨ Опыт: <b>{xp}</b> / {needed_xp}\n"
            f"[{bar}]\n\n"
            f"🪙 Монеты: <b>{coins}</b>\n"
            f"🍬 Ириски: <b>{iris}</b>\n"
            f"🎁 Бонус к прибыли: <b>+{bonus:.1f}%</b>\n\n"
            f"💡 <i>Совет: открывай .карточку каждые 5 минут — это твой основной доход.</i>")
    await message.answer(text, parse_mode="HTML")

# --- ТОП ПО МОНЕТАМ ---
@dp.message(Command("top"))
async def top_coins(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 5")
    top_players = c.fetchall(); conn.close()
    if not top_players: return await message.answer("Пока нет игроков в топе.")
    
    text = "🏆 <b>ТОП ПО МОНЕТАМ</b> 🏆\n\n<blockquote>"
    for i, (username, first_name, coins) in enumerate(top_players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        if username: display_name = f"@{username}"
        elif first_name: display_name = first_name
        else: display_name = "Игрок"
        text += f"{medal} {display_name} — <b>{coins}</b> 🪙\n"
    text += "</blockquote>"
    text += "\n💡 <i>Совет: чтобы попасть в топ, копи монеты и не забывай про бонусы от NFT.</i>"
    await message.answer(text, parse_mode="HTML")

# --- ТОП ПО ИРИСКАМ ---
@dp.message(Command("top_iris"))
async def top_iris(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, iris FROM users ORDER BY iris DESC LIMIT 5")
    top_players = c.fetchall(); conn.close()
    if not top_players: return await message.answer("Пока нет игроков в топе.")
    
    text = "🏆 <b>ТОП ПО ИРИСКАМ</b> 🏆\n\n<blockquote>"
    for i, (username, first_name, iris) in enumerate(top_players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        if username: display_name = f"@{username}"
        elif first_name: display_name = first_name
        else: display_name = "Игрок"
        text += f"{medal} {display_name} — <b>{iris}</b> 🍬\n"
    text += "</blockquote>"
    text += "\n💡 <i>Совет: ириски падают из карточек так же часто, как и монеты. Собирай их!</i>"
    await message.answer(text, parse_mode="HTML")

# --- КАРТОЧКА ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card = get_user(user_id)
    now = time.time()
    if now - last_card < 300:
        left = 300 - (now - last_card)
        return await message.reply(f"⏳ Жди: {int(left // 60)}м {int(left % 60)}с.\n💡 <i>Совет: пока ждешь, загляни в /shop.</i>", parse_mode="HTML")
    
    msg = await message.reply("🎴 <b>Открываем карточку...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🔄 <b>Крутим барабаны...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("✨ <b>Почти готово...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    base_amount = random.randint(5, 10)
    bonus_percent = get_total_bonus(user_id) / 100.0
    final_amount = int(base_amount * (1 + bonus_percent))

    if random.choice([True, False]):
        reward = f"🪙 Тебе выпало <b>{final_amount}</b> монет!"
        new_coins, new_iris = coins + final_amount, iris
    else:
        reward = f"🍬 Тебе выпало <b>{final_amount}</b> ирисок!"
        new_coins, new_iris = coins, iris + final_amount

    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = ?, iris = ?, xp = xp + 5, last_card = ? WHERE user_id = ?", (new_coins, new_iris, now, user_id))
    conn.commit(); conn.close()
    
    await msg.edit_text(
        f"🎉 <b>Карточка открыта!</b>\n\n<blockquote>{reward}</blockquote>\n\n"
        f"💡 <i>Совет: не забывай покупать NFT в /shop — они увеличивают твой дроп!</i>", 
        parse_mode="HTML"
    )

# --- КЛАНЫ ---
@dp.message(Command("clan_create"))
async def clan_create(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("Используй: /clan_create [Название]")
    clan_name = args[1]
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    try:
        c.execute("INSERT INTO clans (name, owner_id, members) VALUES (?, ?, ?)", (clan_name, message.from_user.id, str(message.from_user.id)))
        conn.commit()
        await message.reply(f"🛡 Клан <b>{clan_name}</b> создан! Ты лидер.\n💡 <i>Совет: позови друзей, чтобы они вступили в твой клан.</i>", parse_mode="HTML")
    except sqlite3.IntegrityError:
        await message.reply("❌ Клан с таким названием уже существует.")
    conn.close()

@dp.message(Command("clan_info"))
async def clan_info(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("Используй: /clan_info [Название]")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT owner_id, members FROM clans WHERE name = ?", (args[1],))
    res = c.fetchone(); conn.close()
    if not res: return await message.reply("❌ Клан не найден.")
    owner, members = res
    members_list = members.split(",")
    await message.reply(f"🛡 <b>Клан {args[1]}</b>\n👑 Лидер: <code>{owner}</code>\n👥 Участников: {len(members_list)}", parse_mode="HTML")

# --- СТАТИСТИКА ---
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    chat_id = message.chat.id
    now = time.time()
    five_hours_ago = now - (5 * 3600)
    one_day_ago = now - (24 * 3600)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, five_hours_ago))
    count_5h = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, one_day_ago))
    count_24h = c.fetchone()[0]
    conn.close()
    text = (f"📊 <b>АНАЛИТИКА ЧАТА</b>\n\n<blockquote>🕒 За 5 часов: <b>{count_5h}</b> сообщений\n📅 За 24 часа: <b>{count_24h}</b> сообщений</blockquote>")
    await message.reply(text, parse_mode="HTML")

# --- ОЧИСТКА ---
@dp.message(Command("clear"))
async def clear_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await message.delete()
    deleted = 0
    for i in range(1, count + 1):
        try:
            await bot.delete_message(message.chat.id, message.message_id - i)
            deleted += 1
            await asyncio.sleep(0.1)
        except: pass
    msg = await message.answer(f"🧹 Очищено: {deleted}")
    await asyncio.sleep(3)
    await msg.delete()

# --- МОДЕРАЦИЯ ---
@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 3600)
        await message.reply(f"🤐 Замучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply(f"🔊 Размучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"👢 Кикнут.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ Введи ID.")
    try:
        await bot.unban_chat_member(message.chat.id, int(args[1]))
        await message.reply(f"🔓 Разбанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("close_chat"))
async def close_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
        await message.reply("🔒 Закрыт.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("open_chat"))
async def open_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply("🔓 Открыт.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

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
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message or not message.reply_to_message.from_user.is_bot:
        return await message.reply("❌ Ответь на сообщение бота.")
    target = message.reply_to_message.from_user
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, ?)", (message.chat.id, target.id))
    conn.commit(); conn.close()
    await message.reply(f"🤐 Бот заглушен.")

@dp.message(Command("mute_all_bots"))
async def mute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, 0)", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🤐 Все боты заглушены.")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🔊 Все боты разглушены.")

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    update_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я твой верный помощник. Напиши /help, чтобы увидеть все команды.\n\n"
        "💡 <i>Совет: начни с .карточка, чтобы заработать первые монеты!</i>", 
        parse_mode="HTML"
    )

# --- СЧЕТЧИК ---
@dp.message(lambda m: m.text and not m.text.startswith("/") and not m.text.startswith("."))
async def track_stats(message: types.Message):
    if message.chat.type == "private" or message.from_user.is_bot: return
    update_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO chat_stats (chat_id, user_id, timestamp) VALUES (?, ?, ?)", (message.chat.id, message.from_user.id, time.time()))
    conn.commit(); conn.close()

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
