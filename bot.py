import asyncio
import random
import sqlite3
import time
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9184406467:AAGqWDc0a0qeMODcwJH8WCF5kn7lZypBFnE"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {
    "🚀 Ракета": {"price": 50, "income": 5},
    "💎 Алмаз": {"price": 100, "income": 10},
    "🗽 Статуя Свободы": {"price": 1200, "income": 50},
    "🕶️ Очки": {"price": 2300, "income": 100}
}
DAILY_BONUS = 50

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 1000, last_bonus INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        res = (1000, 0)
    conn.close()
    return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return [item[0] for item in items]

def calculate_passive_income(user_id):
    items = get_inventory(user_id)
    total = 0
    for name in items:
        if name in SHOP_ITEMS:
            total += SHOP_ITEMS[name]["income"]
    return total

# --- МЕНЮ ---
def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(
        InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), 
        InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory")
    )
    builder.row(
        InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard"), 
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
    )
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin_panel"))
    return builder.as_markup()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer("🌟 <b>Добро пожаловать в NFT КАЗИНО!</b>\n\nТвой баланс: 1000 монет.", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _ = get_user(callback.from_user.id)
    items = get_inventory(callback.from_user.id)
    income = calculate_passive_income(callback.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ</b>\n\n"
            f"🆔 ID: {callback.from_user.id}\n"
            f"💰 Баланс: <b>{bal}</b> монет\n"
            f"🎒 NFT: <b>{len(items)}</b> шт.\n"
            f"📈 Доход с NFT: <b>+{income}</b> к бонусу")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    _, last_bonus = get_user(callback.from_user.id)
    now = int(time.time())
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True)
        return
    total = DAILY_BONUS + calculate_passive_income(callback.from_user.id)
    update_balance(callback.from_user.id, total)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now, callback.from_user.id))
    conn.commit()
    conn.close()
    await callback.answer(f"🎉 Получено {total} монет!", show_alert=True)
    await callback.message.edit_text("🎁 Бонус получен!", reply_markup=main_menu(callback.from_user.id))

# --- МАГАЗИН ---
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        text += f"{name} — <b>{data['price']}</b>\n└ Доход: +{data['income']}\n\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    if item in SHOP_ITEMS:
        bal, _ = get_user(callback.from_user.id)
        if bal < SHOP_ITEMS[item]["price"]:
            await callback.answer("❌ Не хватает монет!", show_alert=True)
            return
        update_balance(callback.from_user.id, -SHOP_ITEMS[item]["price"])
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item))
        conn.commit()
        conn.close()
        await callback.answer(f"✅ Куплено: {item}", show_alert=True)

# --- ИНВЕНТАРЬ ---
@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n"
    if not items:
        text += "Пусто."
    else:
        for name in items:
            text += f"• {name}\n"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ТОП ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    
    text = "🏆 <b>ТОП-10 ИГРОКОВ</b>\n\n"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} ID {uid} — <b>{bal}</b>\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КАЗИНО (МГНОВЕННО, БЕЗ ВВОДА СТАВОК) ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА (ставка 100)", callback_data="game_coin_100"))
    builder.row(InlineKeyboardButton(text="🎲 КУБИК (ставка 100)", callback_data="game_dice_100"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>\n\nВыбери игру (ставка 100 монет):", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_"))
async def cb_game(callback: types.CallbackQuery):
    game = callback.data.split("_")[1]
    bal, _ = get_user(callback.from_user.id)
    
    if bal < 100:
        await callback.answer("❌ Не хватает монет для ставки!", show_alert=True)
        return
        
    if game == "coin":
        if random.choice([True, False]):
            update_balance(callback.from_user.id, 100)
            res = "🪙 ОРЕЛ! Ты выиграл 100 монет!"
        else:
            update_balance(callback.from_user.id, -100)
            res = "🪙 РЕШКА. Ты проиграл 100 монет."
            
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b:
            update_balance(callback.from_user.id, 100)
            res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n🎉 Победа! +100 монет."
        elif u < b:
            update_balance(callback.from_user.id, -100)
            res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n😢 Поражение. -100 монет."
        else:
            res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n🤝 Ничья."

    new_bal, _ = get_user(callback.from_user.id)
    await callback.message.edit_text(f"{res}\n\n💰 Баланс: <b>{new_bal}</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚙️ <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery):
    await callback.message.edit_text("💸 Чтобы выдать монеты, просто напиши боту: `give ID СУММА`", parse_mode="HTML")

@dp.message(F.text.startswith("give "))
async def admin_give_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, uid, amount = message.text.split()
        uid, amount = int(uid), int(amount)
        update_balance(uid, amount)
        await message.answer(f"✅ Выдано {amount} монет пользователю {uid}.")
    except:
        await message.answer("❌ Ошибка формата. Пример: `give 123456789 500`")

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is running", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
