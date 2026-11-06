import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9022493828:AAFpmiRB9LfZBRy3HCZXC1NBVW-mfO_xs8c"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- NFT С ССЫЛКАМИ, ФОНАМИ И ЦЕННОСТЬЮ ---
NFT_ITEMS = [
    {"name": "TimelessBook #18804", "backdrop": "Copper", "price": 10, "url": "https://t.me/nft/TimelessBook-18804"},
    {"name": "TimelessBook #6792", "backdrop": "Silver", "price": 15, "url": "https://t.me/nft/TimelessBook-6792"},
    {"name": "TimelessBook #68921", "backdrop": "Gold", "price": 25, "url": "https://t.me/nft/TimelessBook-68921"},
    {"name": "TimelessBook #33555", "backdrop": "Celtic Blue", "price": 50, "url": "https://t.me/nft/TimelessBook-33555"},
    {"name": "TimelessBook #46921", "backdrop": "Desert Sand", "price": 20, "url": "https://t.me/nft/TimelessBook-46921"},
    {"name": "TimelessBook #35131", "backdrop": "Desert Sand", "price": 40, "url": "https://t.me/nft/TimelessBook-35131"},
]

# --- ШАНСЫ НА КРАФТ ---
CRAFT_CHANCES = {
    "TimelessBook #33555": 5,
    "TimelessBook #35131": 47
}

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 first_name TEXT,
                 coins INTEGER DEFAULT 0,
                 card_points INTEGER DEFAULT 0,
                 last_card REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 item_name TEXT,
                 backdrop TEXT,
                 price INTEGER,
                 url TEXT)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, card_points, last_card FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0, 0, 0)
    conn.close(); return res

def add_points(uid, points):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET card_points = card_points + ? WHERE user_id = ?", (points, uid))
    conn.commit(); conn.close()

def update_last_card(uid, timestamp):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_card = ? WHERE user_id = ?", (timestamp, uid))
    conn.commit(); conn.close()

def add_nft_to_inv(uid, name, backdrop, price, url):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name, backdrop, price, url) VALUES (?, ?, ?, ?, ?)", (uid, name, backdrop, price, url))
    conn.commit(); conn.close()

def get_inv(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name, backdrop, price, url FROM inventory WHERE user_id = ?", (uid,))
    items = c.fetchall(); conn.close(); return items

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    await message.answer("👋 Привет! Пиши <b>.карточка</b>, чтобы открыть NFT и получить очки!", parse_mode="HTML")

# --- КАРТОЧКА (15 МИНУТ) ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, points, last_card = get_user(user_id)
    now = time.time()
    
    if now - last_card < 900:
        left = 900 - (now - last_card)
        return await message.reply(f"⏳ Жди: {int(left // 60)}м {int(left % 60)}с.")
    
    msg = await message.reply("🎴 <b>Открываем карточку...</b>", parse_mode="HTML")
    try:
        await asyncio.sleep(1)
        await msg.edit_text("🔄 <b>Крутим...</b>", parse_mode="HTML")
        await asyncio.sleep(1)
        await msg.edit_text("✨ <b>Почти готово...</b>", parse_mode="HTML")
        await asyncio.sleep(1)
    except: pass
    
    nft = random.choice(NFT_ITEMS)
    add_points(user_id, 50)
    update_last_card(user_id, now)
    add_nft_to_inv(user_id, nft["name"], nft["backdrop"], nft["price"], nft["url"])
    
    # Кнопка для открытия NFT по ссылке
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 Открыть NFT", url=nft["url"]))
    
    text = (
        f"🎉 <b>Тебе выпал NFT!</b>\n\n"
        f"🖼 <b>{nft['name']}</b>\n"
        f"🎨 Фон: <b>{nft['backdrop']}</b>\n"
        f"💰 Ценность: <b>{nft['price']} монет</b>\n\n"
        f"⭐ <b>+50 очков</b> в таблицу лидеров!\n"
        f"📊 Твои очки: <b>{points + 50}</b>"
    )
    
    try:
        await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ИНВЕНТАРЬ ---
@dp.message(Command("inventory"))
async def inventory(message: types.Message):
    items = get_inv(message.from_user.id)
    if not items:
        return await message.reply("🎒 Инвентарь пуст.")
    
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n"
    for item_id, name, backdrop, price, url in items:
        text += f"• <b>{name}</b> ({backdrop}) — {price} монет\n"
    
    await message.reply(text, parse_mode="HTML")

# --- КРАФТ (С ШАНСАМИ) ---
@dp.message(Command("craft"))
async def craft_menu(message: types.Message):
    items = get_inv(message.from_user.id)
    if not items:
        return await message.reply("🎒 Инвентарь пуст.")
    
    builder = InlineKeyboardBuilder()
    for item_id, name, backdrop, price, url in items:
        if name in CRAFT_CHANCES:
            chance = CRAFT_CHANCES[name]
            builder.row(InlineKeyboardButton(
                text=f"{name} ({backdrop}) — Шанс: {chance}%",
                callback_data=f"craft_item_{item_id}"
            ))
    
    if not builder.buttons:
        return await message.reply("❌ Нет NFT, которые можно скрафтить.")
    
    builder.row(InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_craft"))
    await message.answer("🔨 <b>КРАФТ</b>\nВыбери NFT для крафта:", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("craft_item_"))
async def craft_start(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name, backdrop, price, url FROM inventory WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    res = c.fetchone()
    conn.close()
    
    if not res:
        return await callback.answer("❌ NFT не найден.")
    
    name, backdrop, price, url = res
    chance = CRAFT_CHANCES.get(name, 0)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔥 НАЧАТЬ КРАФТ", callback_data=f"craft_do_{item_id}"))
    
    await callback.message.edit_text(
        f"🔨 <b>КРАФТ: {name}</b>\n\n"
        f"🎨 Фон: {backdrop}\n"
        f"💰 Ценность: {price} монет\n"
        f"🎲 Шанс успеха: <b>{chance}%</b>\n\n"
        f"Нажми, чтобы начать:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data.startswith("craft_do_"))
async def craft_do(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name, backdrop, price, url FROM inventory WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    res = c.fetchone()
    
    if not res:
        conn.close()
        return await callback.answer("❌ NFT не найден.")
    
    name, backdrop, price, url = res
    chance = CRAFT_CHANCES.get(name, 0)
    
    await callback.message.edit_text("🔨 <b>Крафтим...</b>\n\n🔄 Плавим NFT...", parse_mode="HTML")
    await asyncio.sleep(2)
    
    if random.randint(1, 100) <= chance:
        new_price = price + 50
        c.execute("UPDATE inventory SET price = ? WHERE id = ?", (new_price, item_id))
        conn.commit()
        await callback.message.edit_text(f"🎉 <b>УСПЕХ!</b>\nТвой <b>{name}</b> улучшен до <b>{new_price}</b> монет!", parse_mode="HTML")
    else:
        c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        conn.commit()
        await callback.message.edit_text(f"💥 <b>ПРОВАЛ!</b>\nТвой <b>{name}</b> сгорел.", parse_mode="HTML")
    conn.close()

@dp.callback_query(lambda c: c.data == "close_craft")
async def close_craft(callback: types.CallbackQuery):
    await callback.message.delete()

# --- ТАБЛИЦА ЛИДЕРОВ ---
@dp.message(Command("top_cards"))
async def top_cards(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, card_points FROM users ORDER BY card_points DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    
    if not top:
        return await message.answer("Пока нет игроков с очками.")
    
    text = "🏆 <b>ТОП ПО КАРТОЧКАМ</b>\n\n<blockquote>"
    for i, (username, first_name, points) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{username}" if username else first_name
        text += f"{medal} {name} — <b>{points}</b> очков\n"
    text += "</blockquote>"
    await message.answer(text, parse_mode="HTML")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
