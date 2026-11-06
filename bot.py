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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9022493828:AAHFyJzQwR9cMrqbFiHkq_hbK9dTI7ZWY_4"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class States(StatesGroup):
    mine_bet = State()
    mine_game = State()
    offer_price = State()

# --- МАГАЗИН (ОСТАВИЛ ТОЛЬКО СТАРЫЕ, ЧТОБЫ НЕ БЫЛО КАШИ) ---
SHOP_ITEMS = {
    "TimelessBook #49409": {"price_rub": 150, "limit": 130, "url": "https://t.me/nft/TimelessBook-49409", "backdrop": "Strawberry"},
    "TimelessBook #6545": {"price_rub": 120, "limit": 80, "url": "https://t.me/nft/TimelessBook-6545", "backdrop": "Shamrock Green"},
    "TimelessBook #44126": {"price_rub": 200, "limit": 170, "url": "https://t.me/nft/TimelessBook-44126", "backdrop": "Gold"},
    "TimelessBook #79905": {"price_rub": 300, "limit": 115, "url": "https://t.me/nft/TimelessBook-79905", "backdrop": "Pacific Cyan"},
    "TimelessBook #53434": {"price_rub": 180, "limit": 12, "url": "https://t.me/nft/TimelessBook-53434", "backdrop": "French Violet"},
    "KhabibsPapakha #787": {"price_rub": 250, "limit": 67, "url": "https://t.me/nft/KhabibsPapakha-787", "backdrop": "Mexican Pink"},
    "KhabibsPapakha #12334": {"price_rub": 350, "limit": 55, "url": "https://t.me/nft/KhabibsPapakha-12334", "backdrop": "Unknown"},
    "KhabibsPapakha #12260": {"price_rub": 500, "limit": 15, "url": "https://t.me/nft/KhabibsPapakha-12260", "backdrop": "Unknown"},
}

# --- NFT ДЛЯ КЕЙСА (НОВЫЕ) ---
CASE_ITEMS = [
    {"name": "HeroicHelmet #1", "chance": 0.1, "price_rub": 1000, "url": "https://t.me/nft/HeroicHelmet-1", "backdrop": "Unknown"},
    {"name": "ResistanceDog #4465", "chance": 0.8, "price_rub": 800, "url": "https://t.me/nft/ResistanceDog-4465", "backdrop": "Unknown"},
    {"name": "ResistanceDog #3469", "chance": 1.4, "price_rub": 600, "url": "https://t.me/nft/ResistanceDog-3469", "backdrop": "Unknown"},
    {"name": "HeartLocket #1146", "chance": 2.2, "price_rub": 300, "url": "https://t.me/nft/HeartLocket-1146", "backdrop": "Heart"},
    {"name": "HeartLocket #213", "chance": 4.4, "price_rub": 250, "url": "https://t.me/nft/HeartLocket-213", "backdrop": "Heart"},
    {"name": "ResistanceDog #6371", "chance": 4.8, "price_rub": 400, "url": "https://t.me/nft/ResistanceDog-6371", "backdrop": "Unknown"},
    {"name": "HeartLocket #386", "chance": 7.9, "price_rub": 200, "url": "https://t.me/nft/HeartLocket-386", "backdrop": "Heart"},
    {"name": "MightyArm #747", "chance": 10.2, "price_rub": 150, "url": "https://t.me/nft/MightyArm-747", "backdrop": "Unknown"},
    {"name": "InputKey #102528", "chance": 34.3, "price_rub": 50, "url": "https://t.me/nft/InputKey-102528", "backdrop": "Unknown"},
    {"name": "30 РУБЛЕЙ", "chance": 43.0, "price_rub": 0, "url": None, "backdrop": "Money"},
]

CARD_ITEMS = [
    {"name": "TimelessBook #49409", "backdrop": "Strawberry", "price_rub": 150, "url": "https://t.me/nft/TimelessBook-49409"},
    {"name": "KhabibsPapakha #787", "backdrop": "Mexican Pink", "price_rub": 250, "url": "https://t.me/nft/KhabibsPapakha-787"},
]

UPGRADE_ITEMS = {
    "KhabibsPapakha #22922": {"price_rub": 800, "url": "https://t.me/nft/KhabibsPapakha-22922", "backdrop": "Black"},
    "KhabibsPapakha #12396": {"price_rub": 600, "url": "https://t.me/nft/KhabibsPapakha-12396", "backdrop": "Unknown"},
}

CRAFT_SUCCESS_CHANCE = 25

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 first_name TEXT,
                 balance_rub INTEGER DEFAULT 0,
                 total_earned INTEGER DEFAULT 0,
                 last_card REAL DEFAULT 0,
                 last_daily REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 item_name TEXT,
                 backdrop TEXT,
                 price_rub INTEGER,
                 url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_sold (
                 item_name TEXT PRIMARY KEY,
                 sold_count INTEGER DEFAULT 0)''')
    for name in SHOP_ITEMS:
        c.execute("INSERT OR IGNORE INTO shop_sold (item_name, sold_count) VALUES (?, 0)", (name,))
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT balance_rub, total_earned, last_card, last_daily FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0, 0, 0, 0)
    conn.close(); return res

def update_balance(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance_rub = balance_rub + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, uid))
    conn.commit(); conn.close()

def update_last_card(uid, timestamp):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_card = ? WHERE user_id = ?", (timestamp, uid))
    conn.commit(); conn.close()

def update_last_daily(uid, timestamp):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (timestamp, uid))
    conn.commit(); conn.close()

def add_nft_to_inv(uid, name, backdrop, price_rub, url):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name, backdrop, price_rub, url) VALUES (?, ?, ?, ?, ?)", (uid, name, backdrop, price_rub, url))
    conn.commit(); conn.close()

def get_inv(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT id, item_name, backdrop, price_rub, url FROM inventory WHERE user_id = ?", (uid,))
    items = c.fetchall(); conn.close(); return items

def get_sold_count(name):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT sold_count FROM shop_sold WHERE item_name = ?", (name,))
    res = c.fetchone(); conn.close(); return res[0] if res else 0

def increment_sold(name):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE shop_sold SET sold_count = sold_count + 1 WHERE item_name = ?", (name,))
    conn.commit(); conn.close()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases"))
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="💣 Минное поле", callback_data="mines_menu"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="top"))
    builder.row(InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"))
    builder.row(InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"))
    await message.answer("👋 Привет! Выбери действие:", reply_markup=builder.as_markup())

# --- КЕЙСЫ ---
@dp.callback_query(lambda c: c.data == "cases")
async def cases_menu(callback: types.CallbackQuery):
    text = ("🎁 <b>КЕЙСЫ</b>\n\n"
            "Dragon Glass #1 — 10 руб.\n"
            "Шансы: +30₽ (43%), InputKey (34.3%), MightyArm (10.2%), HeartLocket (7.9%), и другие...\n\n"
            "Нажми, чтобы крутить:")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Крутить кейс (10 руб.)", callback_data="open_case"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "open_case")
async def open_case(callback: types.CallbackQuery):
    bal, _, _, _ = get_user(callback.from_user.id)
    if bal < 10:
        return await callback.answer("❌ Мало рублей! Нужно 10.", show_alert=True)
    
    update_balance(callback.from_user.id, -10)
    
    msg = await callback.message.edit_text("🎁 <b>Открываем кейс...</b>\n\n🔄 Крутим...", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🎁 <b>Открываем кейс...</b>\n\n✨ Почти готово...", parse_mode="HTML")
    await asyncio.sleep(1)
    
    # Выбор по шансам
    r = random.uniform(0, 100)
    cumulative = 0
    chosen = None
    for item in CASE_ITEMS:
        cumulative += item["chance"]
        if r <= cumulative:
            chosen = item
            break
    
    if chosen is None:
        chosen = CASE_ITEMS[-1] # Если что-то пошло не так, даем последний (рубли)
    
    if chosen["name"] == "30 РУБЛЕЙ":
        update_balance(callback.from_user.id, 30)
        result = "🎉 <b>Ты выбил 30 рублей!</b>"
        btn = InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 В меню", callback_data="back"))
    else:
        add_nft_to_inv(callback.from_user.id, chosen["name"], chosen["backdrop"], chosen["price_rub"], chosen["url"])
        result = f"🎉 <b>Ты выбил {chosen['name']}!</b>\n💰 Ценность: {chosen['price_rub']} руб."
        btn = InlineKeyboardBuilder().row(
            InlineKeyboardButton(text=f"🔗 Открыть {chosen['name']}", url=chosen["url"]),
            InlineKeyboardButton(text="🔙 В меню", callback_data="back")
        )
    
    await msg.edit_text(f"{result}\n\n💰 Баланс: <b>{get_user(callback.from_user.id)[0]} руб.</b>", reply_markup=btn.as_markup(), parse_mode="HTML")

# (ОСТАЛЬНОЙ КОД: МИННОЕ ПОЛЕ, МАГАЗИН, ПРОФИЛЬ, ТОП, КРАФТ, КАРТОЧКА, ИНВЕНТАРЬ)
# Вставь сюда функции из предыдущего сообщения (mines_menu, process_mine_bet, mine_click, mine_cashout, shop_menu, view_nft, buy_nft, profile, top_leaderboard, open_card, daily_bonus, craft_menu, craft_choose_target, view_upgrade_nft, noop, back)

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
