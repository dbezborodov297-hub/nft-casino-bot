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

BOT_TOKEN = "9022493828:AAHPQoC8J70287aofDvBaHauL7tOM7ovJE4"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ФЛАСК ДЛЯ RENDER (ЗАПУСКАЕТСЯ ПЕРВЫМ) ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- МАГАЗИН (ТОЛЬКО СТАРЫЕ NFT) ---
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

# --- NFT ДЛЯ КЕЙСА (ТОЛЬКО НОВЫЕ) ---
CASE_ITEMS = [
    {"name": "HeroicHelmet #1", "chance": 0.1, "price_rub": 1000, "url": "https://t.me/nft/HeroicHelmet-1"},
    {"name": "ResistanceDog #4465", "chance": 0.8, "price_rub": 800, "url": "https://t.me/nft/ResistanceDog-4465"},
    {"name": "ResistanceDog #3469", "chance": 1.4, "price_rub": 600, "url": "https://t.me/nft/ResistanceDog-3469"},
    {"name": "HeartLocket #1146", "chance": 2.2, "price_rub": 300, "url": "https://t.me/nft/HeartLocket-1146"},
    {"name": "HeartLocket #213", "chance": 4.4, "price_rub": 250, "url": "https://t.me/nft/HeartLocket-213"},
    {"name": "ResistanceDog #6371", "chance": 4.8, "price_rub": 400, "url": "https://t.me/nft/ResistanceDog-6371"},
    {"name": "HeartLocket #386", "chance": 7.9, "price_rub": 200, "url": "https://t.me/nft/HeartLocket-386"},
    {"name": "MightyArm #747", "chance": 10.2, "price_rub": 150, "url": "https://t.me/nft/MightyArm-747"},
    {"name": "InputKey #102528", "chance": 34.3, "price_rub": 50, "url": "https://t.me/nft/InputKey-102528"},
    {"name": "30 РУБЛЕЙ", "chance": 43.0, "price_rub": 0, "url": None},
]

# --- NFT ДЛЯ КАРТОЧКИ ---
CARD_ITEMS = [
    {"name": "TimelessBook #49409", "backdrop": "Strawberry", "price_rub": 150, "url": "https://t.me/nft/TimelessBook-49409"},
    {"name": "KhabibsPapakha #787", "backdrop": "Mexican Pink", "price_rub": 250, "url": "https://t.me/nft/KhabibsPapakha-787"},
]

# --- КРАФТ (ЦЕЛИ) ---
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
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🏆 Топ", callback_data="top"))
    builder.row(InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"))
    await message.answer("👋 Привет! Выбери действие:", reply_markup=builder.as_markup())

# --- КЕЙСЫ ---
@dp.callback_query(lambda c: c.data == "cases")
async def cases_menu(callback: types.CallbackQuery):
    text = ("🎁 <b>КЕЙСЫ</b>\n\n"
            "Dragon Glass #1 — 10 руб.\n"
            "Шансы: +30₽ (43%), InputKey (34.3%), MightyArm (10.2%), HeartLocket (7.9%), и другие NFT...\n\n"
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
    r = random.uniform(0, 100)
    cumulative = 0
    chosen = CASE_ITEMS[-1]
    for item in CASE_ITEMS:
        cumulative += item["chance"]
        if r <= cumulative:
            chosen = item
            break
    if chosen["name"] == "30 РУБЛЕЙ":
        update_balance(callback.from_user.id, 30)
        result = "🎉 <b>Ты выбил 30 рублей!</b>"
        btn = InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 В меню", callback_data="back"))
    else:
        add_nft_to_inv(callback.from_user.id, chosen["name"], "Case", chosen["price_rub"], chosen["url"])
        result = f"🎉 <b>Ты выбил {chosen['name']}!</b>\n💰 Ценность: {chosen['price_rub']} руб."
        btn = InlineKeyboardBuilder().row(
            InlineKeyboardButton(text=f"🔗 Открыть {chosen['name']}", url=chosen["url"]),
            InlineKeyboardButton(text="🔙 В меню", callback_data="back")
        )
    await msg.edit_text(f"{result}\n\n💰 Баланс: <b>{get_user(callback.from_user.id)[0]} руб.</b>", reply_markup=btn.as_markup(), parse_mode="HTML")

# --- МАГАЗИН ---
@dp.callback_query(lambda c: c.data == "shop")
async def shop_menu(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        sold = get_sold_count(name)
        left = data["limit"] - sold
        text += f"📦 <b>{name}</b>\n💰 {data['price_rub']} руб.\n📦 {sold}/{data['limit']}\n\n"
        if left > 0:
            builder.row(InlineKeyboardButton(text=f"👀 Посмотреть {name}", callback_data=f"view_{name}"))
        else:
            builder.row(InlineKeyboardButton(text=f"❌ {name} — Распродано", callback_data="noop"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("view_"))
async def view_nft(callback: types.CallbackQuery):
    name = callback.data.replace("view_", "")
    data = SHOP_ITEMS.get(name)
    if not data:
        return await callback.answer("❌ Нет такого NFT.", show_alert=True)
    sold = get_sold_count(name)
    left = data["limit"] - sold
    if left <= 0:
        return await callback.answer("❌ Этот NFT распродан!", show_alert=True)
    text = (f"🖼 <b>{name}</b>\n\n🎨 Фон: <b>{data['backdrop']}</b>\n💰 Цена: <b>{data['price_rub']} руб.</b>\n📦 Осталось: {left}/{data['limit']}\n\n<a href='{data['url']}'>🔗 Посмотреть в Telegram</a>")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"💰 Купить за {data['price_rub']} руб.", callback_data=f"buy_{name}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад в магазин", callback_data="shop"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_nft(callback: types.CallbackQuery):
    name = callback.data.replace("buy_", "")
    data = SHOP_ITEMS.get(name)
    if not data:
        return await callback.answer("❌ Нет такого NFT.", show_alert=True)
    sold = get_sold_count(name)
    if sold >= data["limit"]:
        return await callback.answer("❌ Этот NFT уже распродан!", show_alert=True)
    bal, _, _, _ = get_user(callback.from_user.id)
    if bal < data["price_rub"]:
        return await callback.answer(f"❌ Мало рублей! Нужно {data['price_rub']}.", show_alert=True)
    update_balance(callback.from_user.id, -data["price_rub"])
    add_nft_to_inv(callback.from_user.id, name, data["backdrop"], data["price_rub"], data["url"])
    increment_sold(name)
    await callback.answer(f"✅ Куплено {name}!", show_alert=True)
    await shop_menu(callback)

# --- ПРОФИЛЬ ---
@dp.callback_query(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    bal, total_earned, _, _ = get_user(callback.from_user.id)
    items = get_inv(callback.from_user.id)
    level = total_earned // 500
    progress = min(int((total_earned % 500) / 500 * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    text = (f"╔══════════════════╗\n   👤 <b>ТВОЙ ПРОФИЛЬ</b>\n╚══════════════════╝\n\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n📈 Уровень: <b>{level}</b>\n"
            f"[{bar}] {total_earned % 500}/{500}\n\n"
            f"💰 Баланс: <b>{bal} руб.</b>\n🎒 NFT: <b>{len(items)}</b> шт.\n\n")
    builder = InlineKeyboardBuilder()
    if items:
        text += "<b>Твои NFT:</b>\n"
        for item_id, name, backdrop, price_rub, url in items[:5]:
            text += f"• {name} — {price_rub} руб.\n"
        if len(items) > 5:
            text += f"<i>... и еще {len(items) - 5}</i>\n"
    else:
        text += "🎒 У тебя пока нет NFT."
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ТОП ---
@dp.callback_query(lambda c: c.data == "top")
async def top_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, total_earned FROM users ORDER BY total_earned DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    if not top:
        return await callback.message.edit_text("Пока нет игроков.")
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\n<blockquote>"
    for i, (username, first_name, earned) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{username}" if username else first_name
        text += f"{medal} {name} — <b>{earned} руб.</b>\n"
    text += "</blockquote>"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КАРТОЧКА ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    bal, total_earned, last_card, _ = get_user(user_id)
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
    text = (f"🎉 <b>Тебе выпал NFT!</b>\n\n🖼 <b>{nft['name']}</b>\n🎨 Фон: <b>{nft['backdrop']}</b>\n💰 Ценность: <b>{nft['price_rub']} руб.</b>\n\n💵 <b>Тебе начислено: {rub_reward} руб.!</b>")
    try:
        await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ЕЖЕДНЕВНЫЙ БОНУС ---
@dp.message(Command("daily"))
async def daily_bonus(message: types.Message):
    user_id = message.from_user.id
    bal, _, _, last_daily = get_user(user_id)
    now = time.time()
    if now - last_daily < 86400:
        left = 86400 - (now - last_daily)
        return await message.reply(f"⏳ Жди: {int(left // 3600)}ч {int((left % 3600) // 60)}м.")
    bonus = 50
    update_balance(user_id, bonus)
    update_last_daily(user_id, now)
    await message.reply(f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\nТы получил <b>{bonus} руб.</b>", parse_mode="HTML")

# --- КРАФТ ---
@dp.callback_query(lambda c: c.data == "craft")
async def craft_menu(callback: types.CallbackQuery):
    items = get_inv(callback.from_user.id)
    if not items:
        return await callback.message.edit_text("🎒 Инвентарь пуст. Крафтить нечего.")
    text = "🔨 <b>КРАФТ NFT</b>\nВыбери NFT, который хочешь улучшить:\n\n"
    builder = InlineKeyboardBuilder()
    for item_id, name, backdrop, price_rub, url in items:
        text += f"• <b>{name}</b> ({backdrop}) — {price_rub} руб.\n"
        builder.row(InlineKeyboardButton(text=f"Улучшить {name}", callback_data=f"craft_start_{item_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("craft_start_"))
async def craft_choose_target(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    text = "🎯 <b>Выбери подарок, на который хочешь улучшить свой NFT:</b>\n\n"
    builder = InlineKeyboardBuilder()
    for target_name, target_data in UPGRADE_ITEMS.items():
        text += f"🎁 <b>{target_name}</b>\n💰 Ценность: {target_data['price_rub']} руб.\n🎲 Шанс успеха: <b>{CRAFT_SUCCESS_CHANCE}%</b>\n\n"
        safe_name = target_name.replace(" ", "_")
        builder.row(InlineKeyboardButton(text=f"👀 Посмотреть {target_name}", callback_data=f"view_upgrade_{safe_name}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="craft"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("view_upgrade_"))
async def view_upgrade_nft(callback: types.CallbackQuery):
    safe_name = callback.data.replace("view_upgrade_", "")
    target_name = safe_name.replace("_", " ")
    target_data = UPGRADE_ITEMS.get(target_name)
    if not target_data:
        return await callback.answer("❌ Такого подарка нет.", show_alert=True)
    text = (f"🎁 <b>{target_name}</b>\n\n🎨 Фон: <b>{target_data['backdrop']}</b>\n💰 Ценность: <b>{target_data['price_rub']} руб.</b>\n🎲 Шанс успеха: <b>{CRAFT_SUCCESS_CHANCE}%</b>\n\n<a href='{target_data['url']}'>🔗 Посмотреть в Telegram</a>")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад к выбору", callback_data="craft"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer("❌ Этот NFT уже распродан!", show_alert=True)

@dp.callback_query(lambda c: c.data == "back")
async def back(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases"))
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🏆 Топ", callback_data="top"))
    builder.row(InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"))
    await callback.message.edit_text("👋 Главное меню:", reply_markup=builder.as_markup())

# --- ЗАПУСК С ФИКСОМ ДЛЯ RENDER ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(5)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
