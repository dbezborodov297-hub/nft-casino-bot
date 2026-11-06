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

BOT_TOKEN = "9022493828:AAFFKM1eo66KPWV-HbQwl2OrMKIyebgDxI4"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- МАГАЗИН С НОВЫМИ NFT (ЦЕНА В РУБЛЯХ) ---
SHOP_ITEMS = {
    "TimelessBook #49409": {"price_rub": 150, "limit": 10, "url": "https://t.me/nft/TimelessBook-49409"},
    "TimelessBook #6545": {"price_rub": 120, "limit": 15, "url": "https://t.me/nft/TimelessBook-6545"},
    "TimelessBook #44126": {"price_rub": 200, "limit": 5, "url": "https://t.me/nft/TimelessBook-44126"},
    "TimelessBook #79905": {"price_rub": 300, "limit": 8, "url": "https://t.me/nft/TimelessBook-79905"},
    "TimelessBook #53434": {"price_rub": 180, "limit": 12, "url": "https://t.me/nft/TimelessBook-53434"},
}

CARD_ITEMS = [
    {"name": "TimelessBook #49409", "backdrop": "Strawberry", "price_rub": 150, "url": "https://t.me/nft/TimelessBook-49409"},
    {"name": "TimelessBook #6545", "backdrop": "Shamrock Green", "price_rub": 120, "url": "https://t.me/nft/TimelessBook-6545"},
    {"name": "TimelessBook #44126", "backdrop": "Gold", "price_rub": 200, "url": "https://t.me/nft/TimelessBook-44126"},
    {"name": "TimelessBook #79905", "backdrop": "Pacific Cyan", "price_rub": 300, "url": "https://t.me/nft/TimelessBook-79905"},
    {"name": "TimelessBook #53434", "backdrop": "French Violet", "price_rub": 180, "url": "https://t.me/nft/TimelessBook-53434"},
]

CRAFT_CHANCES = {
    "TimelessBook #49409": 30,
    "TimelessBook #6545": 50,
    "TimelessBook #44126": 15,
    "TimelessBook #79905": 10,
    "TimelessBook #53434": 40,
}

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 first_name TEXT,
                 balance_rub INTEGER DEFAULT 0,
                 total_earned INTEGER DEFAULT 0,
                 last_card REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 item_name TEXT,
                 backdrop TEXT,
                 price_rub INTEGER,
                 url TEXT)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT balance_rub, total_earned, last_card FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0, 0, 0)
    conn.close(); return res

def update_balance(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance_rub = balance_rub + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, uid))
    conn.commit(); conn.close()

def update_last_card(uid, timestamp):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_card = ? WHERE user_id = ?", (timestamp, uid))
    conn.commit(); conn.close()

def add_nft_to_inv(uid, name, backdrop, price_rub, url):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name, backdrop, price_rub, url) VALUES (?, ?, ?, ?, ?)", (uid, name, backdrop, price_rub, url))
    conn.commit(); conn.close()

def get_inv(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name, backdrop, price_rub, url FROM inventory WHERE user_id = ?", (uid,))
    items = c.fetchall(); conn.close(); return items

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"))
    await message.answer("👋 Привет! Выбери действие:", reply_markup=builder.as_markup())

# --- ПРОФИЛЬ С ПРОГРЕСС-БАРОМ ---
@dp.callback_query(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    bal, total_earned, _ = get_user(callback.from_user.id)
    items = get_inv(callback.from_user.id)
    
    # Уровень и прогресс-бар (зависит от total_earned)
    level = total_earned // 500
    next_level = (level + 1) * 500
    progress = min(int((total_earned % 500) / 500 * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    
    text = (f"╔══════════════════╗\n"
            f"   👤 <b>ТВОЙ ПРОФИЛЬ</b>\n"
            f"╚══════════════════╝\n\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n"
            f"📈 Уровень: <b>{level}</b>\n"
            f"[{bar}] {total_earned % 500}/{500}\n\n"
            f"💰 Баланс: <b>{bal} руб.</b>\n"
            f"🎒 NFT в коллекции: <b>{len(items)}</b> шт.\n\n")
    
    builder = InlineKeyboardBuilder()
    if items:
        text += "<b>Твои NFT:</b>\n"
        for item_id, name, backdrop, price_rub, url in items[:5]: # показываем первые 5
            text += f"• {name} — {price_rub} руб.\n"
        if len(items) > 5:
            text += f"<i>... и еще {len(items) - 5}</i>\n"
    else:
        text += "🎒 У тебя пока нет NFT."
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- МАГАЗИН ---
@dp.callback_query(lambda c: c.data == "shop")
async def shop_menu(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        text += f"📦 <b>{name}</b>\n💰 {data['price_rub']} руб.\n\n"
        builder.row(InlineKeyboardButton(
            text=f"Купить {name} ({data['price_rub']} руб.)",
            callback_data=f"buy_{name}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_nft(callback: types.CallbackQuery):
    name = callback.data.replace("buy_", "")
    data = SHOP_ITEMS.get(name)
    if not data:
        return await callback.answer("❌ Нет такого NFT.", show_alert=True)
    
    bal, _, _ = get_user(callback.from_user.id)
    if bal < data["price_rub"]:
        return await callback.answer(f"❌ Мало рублей! Нужно {data['price_rub']}.", show_alert=True)
    
    update_balance(callback.from_user.id, -data["price_rub"])
    add_nft_to_inv(callback.from_user.id, name, "Shop", data["price_rub"], data["url"])
    
    await callback.answer(f"✅ Куплено {name}!", show_alert=True)

# --- КАРТОЧКА (15 МИНУТ) ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    bal, total_earned, last_card = get_user(user_id)
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
    
    nft = random.choice(CARD_ITEMS)
    rub_reward = random.randint(10, 100)
    update_balance(user_id, rub_reward)
    update_last_card(user_id, now)
    add_nft_to_inv(user_id, nft["name"], nft["backdrop"], nft["price_rub"], nft["url"])
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 Открыть NFT", url=nft["url"]))
    
    text = (
        f"🎉 <b>Тебе выпал NFT!</b>\n\n"
        f"🖼 <b>{nft['name']}</b>\n"
        f"🎨 Фон: <b>{nft['backdrop']}</b>\n"
        f"💰 Ценность: <b>{nft['price_rub']} руб.</b>\n\n"
        f"💵 <b>Тебе начислено: {rub_reward} руб.!</b>"
    )
    
    try:
        await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КРАФТ (С АНИМАЦИЕЙ) ---
@dp.callback_query(lambda c: c.data == "craft")
async def craft_menu(callback: types.CallbackQuery):
    items = get_inv(callback.from_user.id)
    if not items:
        return await callback.message.edit_text("🎒 Инвентарь пуст. Крафтить нечего.")
    
    text = "🔨 <b>КРАФТ NFT</b>\nВыбери NFT для улучшения:\n\n"
    builder = InlineKeyboardBuilder()
    for item_id, name, backdrop, price_rub, url in items:
        chance = CRAFT_CHANCES.get(name, 20)
        text += f"• <b>{name}</b> ({backdrop}) — {price_rub} руб. (шанс {chance}%)\n"
        builder.row(InlineKeyboardButton(
            text=f"Улучшить {name}",
            callback_data=f"craft_{item_id}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("craft_"))
async def craft_process(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT item_name, backdrop, price_rub, url FROM inventory WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    res = c.fetchone()
    
    if not res:
        conn.close()
        return await callback.answer("❌ NFT не найден.")
    
    name, backdrop, price_rub, url = res
    chance = CRAFT_CHANCES.get(name, 20)
    
    await callback.message.edit_text("🔨 <b>КРАФТИМ...</b>\n\n🔄 Нагреваем котёл...", parse_mode="HTML")
    await asyncio.sleep(2)
    await callback.message.edit_text("🔨 <b>КРАФТИМ...</b>\n\n💥 Добавляем ингредиенты...", parse_mode="HTML")
    await asyncio.sleep(2)
    await callback.message.edit_text("🔨 <b>КРАФТИМ...</b>\n\n✨ Финал...", parse_mode="HTML")
    await asyncio.sleep(1)
    
    if random.randint(1, 100) <= chance:
        new_price = int(price_rub * 1.5)
        c.execute("UPDATE inventory SET price_rub = ? WHERE id = ?", (new_price, item_id))
        conn.commit()
        await callback.message.edit_text(
            f"🎉 <b>УСПЕХ!</b>\n\n"
            f"Твой <b>{name}</b> улучшен!\n"
            f"💰 Новая ценность: <b>{new_price} руб.</b>",
            parse_mode="HTML"
        )
    else:
        c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        conn.commit()
        await callback.message.edit_text(
            f"💥 <b>ПРОВАЛ!</b>\n\n"
            f"Твой <b>{name}</b> сгорел в котле.",
            parse_mode="HTML"
        )
    conn.close()

@dp.callback_query(lambda c: c.data == "back")
async def back(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"))
    await callback.message.edit_text("👋 Главное меню:", reply_markup=builder.as_markup())

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
