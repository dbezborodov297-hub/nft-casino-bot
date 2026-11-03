import asyncio
import random
import sqlite3
import time
import hashlib
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9020652959:AAFtla1XWDJCm5JAwyWnOYfO4eOL9dRVVto"
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

class UserStates(StatesGroup):
    reg_username = State()
    reg_password = State()
    login_username = State()
    login_password = State()
    waiting_for_bet = State()
    broadcast_msg = State()
    adm_give_coins = State()
    adm_give_nft = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, balance INTEGER DEFAULT 1000, last_bonus INTEGER DEFAULT 0, market_earnings INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    conn.commit()
    conn.close()

def hash_pass(password): return hashlib.sha256(password.encode()).hexdigest()

def get_user(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id, username, balance, last_bonus, market_earnings FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone(); conn.close(); return res

def get_user_by_username(username):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id, password_hash, balance FROM users WHERE username = ?", (username,))
    res = c.fetchone(); conn.close(); return res

def create_user(user_id, username, password):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, username, password_hash, balance) VALUES (?, ?, ?, 1000)", (user_id, username, hash_pass(password)))
        conn.commit(); return True
    except sqlite3.IntegrityError: return False
    finally: conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall(); conn.close(); return items

def calculate_passive_income(user_id):
    items = get_inventory(user_id)
    total = 0
    for _, name in items:
        if name in SHOP_ITEMS: total += SHOP_ITEMS[name]["income"]
    return total

# --- Клавиатуры ---
def auth_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Регистрация", callback_data="auth_reg"))
    builder.row(InlineKeyboardButton(text="🔑 Войти", callback_data="auth_login"))
    return builder.as_markup()

def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin_panel"))
    return builder.as_markup()

# --- АВТОРИЗАЦИЯ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        await message.answer(f"👋 С возвращением, <b>{user[1]}</b>!\n💰 Баланс: <b>{user[2]}</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer("🌟 <b>Добро пожаловать!</b>\nСоздай аккаунт:", reply_markup=auth_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "auth_reg")
async def reg_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи <b>никнейм</b> (без пробелов):", parse_mode="HTML")
    await state.set_state(UserStates.reg_username)

@dp.message(UserStates.reg_username)
async def reg_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if len(username) < 3 or " " in username:
        await message.answer("❌ Никнейм от 3 символов, без пробелов:"); return
    if get_user_by_username(username):
        await message.answer("❌ Ник занят! Введи другой:"); return
    await state.update_data(reg_username=username)
    await message.answer("🔒 Придумай <b>пароль</b> (мин. 4 символа):", parse_mode="HTML")
    await state.set_state(UserStates.reg_password)

@dp.message(UserStates.reg_password)
async def reg_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 4:
        await message.answer("❌ Пароль слишком короткий:"); return
    data = await state.get_data()
    if create_user(message.from_user.id, data['reg_username'], password):
        await message.answer(f"✅ Аккаунт <b>{data['reg_username']}</b> создан!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "auth_login")
async def login_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔑 Введи <b>никнейм</b>:", parse_mode="HTML")
    await state.set_state(UserStates.login_username)

@dp.message(UserStates.login_username)
async def login_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not get_user_by_username(username):
        await message.answer("❌ Аккаунт не найден:"); return
    await state.update_data(login_username=username)
    await message.answer("🔒 Введи <b>пароль</b>:", parse_mode="HTML")
    await state.set_state(UserStates.login_password)

@dp.message(UserStates.login_password)
async def login_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    user_data = get_user_by_username(data['login_username'])
    if user_data and user_data[1] == hash_pass(password):
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("UPDATE users SET user_id = ? WHERE username = ?", (message.from_user.id, data['login_username']))
        conn.commit(); conn.close()
        await message.answer(f"✅ Вход выполнен!", reply_markup=main_menu(message.from_user.id))
    else:
        await message.answer("❌ Неверный пароль!")
    await state.clear()

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user: return
    items = get_inventory(callback.from_user.id)
    income = calculate_passive_income(callback.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ</b>\n\n🏷 Ник: <b>{user[1]}</b>\n💰 Баланс: <b>{user[2]}</b>\n"
            f"🎒 NFT: <b>{len(items)}</b> шт.\n📈 Доход: <b>+{income}</b> к бонусу")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user: return
    now = int(time.time())
    if now - user[3] < 86400:
        left = 86400 - (now - user[3])
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True); return
    total = DAILY_BONUS + calculate_passive_income(callback.from_user.id)
    update_balance(callback.from_user.id, total)
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now, callback.from_user.id))
    conn.commit(); conn.close()
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
        user = get_user(callback.from_user.id)
        if user[2] < SHOP_ITEMS[item]["price"]:
            await callback.answer("❌ Не хватает монет!", show_alert=True); return
        update_balance(callback.from_user.id, -SHOP_ITEMS[item]["price"])
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item))
        conn.commit(); conn.close()
        await callback.answer(f"✅ Куплено: {item}", show_alert=True)

# --- ИНВЕНТАРЬ ---
@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n"
    if not items: text += "Пусто."
    else:
        for _, name in items: text += f"• {name}\n"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ТАБЛИЦА ЛИДЕРОВ ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>ТОП-10 ИГРОКОВ</b>\n\n"
    for i, (uname, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {uname} — <b>{bal}</b>\n"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КАЗИНО ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>\nВыбери игру:", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "game_coin")
async def cb_coin(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💵 Введи сумму ставки (число):")
    await state.set_state(UserStates.waiting_for_bet)

@dp.message(UserStates.waiting_for_bet)
async def process_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    user = get_user(message.from_user.id)
    if user[2] < bet:
        await message.answer("❌ Не хватает монет!"); await state.clear(); return
    
    if random.choice([True, False]):
        update_balance(message.from_user.id, bet)
        await message.answer(f"🪙 ОРЕЛ! +{bet} монет", reply_markup=main_menu(message.from_user.id))
    else:
        update_balance(message.from_user.id, -bet)
        await message.answer(f"🪙 РЕШКА. -{bet} монет", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True); return
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="🎁 Выдать NFT", callback_data="adm_nft"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚙️ <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введи текст рассылки:")
    await state.set_state(UserStates.broadcast_msg)

@dp.message(UserStates.broadcast_msg)
async def adm_broadcast_send(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall(); conn.close()
    count = 0
    for (uid,) in users:
        try: await bot.send_message(uid, f"📢 {message.text}"); count += 1; await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {count}", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💸 Введи <b>ник</b> и <b>сумму</b> (через пробел):", parse_mode="HTML")
    await state.set_state(UserStates.adm_give_coins)

@dp.message(UserStates.adm_give_coins)
async def adm_give_process(message: types.Message, state: FSMContext):
    try: username, amount = message.text.split(); amount = int(amount)
    except: await message.answer("❌ Формат: Ник 500"); return
    user = get_user_by_username(username)
    if not user: await message.answer("❌ Игрок не найден."); return
    update_balance(user[0], amount)
    await message.answer(f"✅ Выдано {amount} монет.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_nft")
async def adm_nft(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎁 Введи <b>ник</b> и <b>название NFT</b> (через пробел):", parse_mode="HTML")
    await state.set_state(UserStates.adm_give_nft)

@dp.message(UserStates.adm_give_nft)
async def adm_nft_process(message: types.Message, state: FSMContext):
    parts = message.text.split(" ", 1)
    if len(parts) < 2: await message.answer("❌ Формат: Ник Название"); return
    username, nft_name = parts[0], parts[1].strip()
    if nft_name not in SHOP_ITEMS: await message.answer("❌ Нет такого NFT."); return
    user = get_user_by_username(username)
    if not user: await message.answer("❌ Игрок не найден."); return
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user[0], nft_name))
    conn.commit(); conn.close()
    await message.answer(f"✅ Выдано {nft_name}.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

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
