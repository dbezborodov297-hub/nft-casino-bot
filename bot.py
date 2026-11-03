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
from aiogram.enums import ButtonStyle

BOT_TOKEN = "9020652959:AAHASViYYeKXFUuk7h3FJjmE5K6Sf1grcso"
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
    minefield_bet = State()
    minefield_play = State()
    selling_price = State()
    offer_amount = State()
    # Админские состояния
    broadcast_msg = State()
    adm_give_coins = State()
    adm_take_coins = State()
    adm_give_nft = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT UNIQUE, 
                 password_hash TEXT,
                 balance INTEGER DEFAULT 1000, 
                 last_bonus INTEGER DEFAULT 0, 
                 market_earnings INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_name TEXT, price INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY AUTOINCREMENT, market_id INTEGER, buyer_id INTEGER, amount INTEGER)''')
    conn.commit()
    conn.close()

def hash_pass(password): return hashlib.sha256(password.encode()).hexdigest()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, last_bonus, market_earnings FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res

def get_user_by_username(username):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, password_hash, balance FROM users WHERE username = ?", (username,))
    res = c.fetchone()
    conn.close()
    return res

def create_user(user_id, username, password):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, username, password_hash, balance) VALUES (?, ?, ?, 1000)", (user_id, username, hash_pass(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError: return False
    finally: conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def update_market_earnings(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET market_earnings = market_earnings + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def update_bonus_time(user_id, timestamp):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit(); conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return items

def calculate_passive_income(user_id):
    items = get_inventory(user_id)
    total_income = 0
    for _, name in items:
        if name in SHOP_ITEMS: total_income += SHOP_ITEMS[name]["income"]
    return total_income

def buy_item(user_id, item_name, price):
    bal = get_user(user_id)[2]
    if bal < price: return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit(); conn.close()
    return True

# --- Клавиатуры ---
def auth_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Регистрация", callback_data="auth_reg", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🔑 Войти в аккаунт", callback_data="auth_login", style=ButtonStyle.PRIMARY))
    return builder.as_markup()

def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino", style=ButtonStyle.PRIMARY))
    builder.row(
        InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory", style=ButtonStyle.SUCCESS)
    )
    builder.row(
        InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile", style=ButtonStyle.SUCCESS)
    )
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily", style=ButtonStyle.SUCCESS))
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel", style=ButtonStyle.DANGER))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin", style=ButtonStyle.PRIMARY),
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice", style=ButtonStyle.PRIMARY)
    )
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС", callback_data="game_darts", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mine", style=ButtonStyle.DANGER))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    return builder.as_markup()

# --- АВТОРИЗАЦИЯ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        text = f"👋 С возвращением, <b>{user[1]}</b>!\n💰 Баланс: <b>{user[2]}</b>\n📈 Доход с NFT: <b>+{calculate_passive_income(message.from_user.id)}</b> к бонусу."
        await message.answer(text, reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer("🌟 <b>Добро пожаловать!</b>\n\nТебе нужно создать аккаунт.", reply_markup=auth_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "auth_reg")
async def reg_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи желаемый <b>никнейм</b>:")
    await state.set_state(UserStates.reg_username)

@dp.message(UserStates.reg_username)
async def reg_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if len(username) < 3 or " " in username:
        await message.answer("❌ Никнейм от 3 символов, без пробелов:")
        return
    if get_user_by_username(username):
        await message.answer("❌ Ник уже занят! Введи другой:")
        return
    await state.update_data(reg_username=username)
    await message.answer("🔒 Придумай <b>пароль</b> (мин. 4 символа):")
    await state.set_state(UserStates.reg_password)

@dp.message(UserStates.reg_password)
async def reg_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 4:
        await message.answer("❌ Пароль слишком короткий:")
        return
    data = await state.get_data()
    if create_user(message.from_user.id, data['reg_username'], password):
        await message.answer(f"✅ Аккаунт <b>{data['reg_username']}</b> создан!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "auth_login")
async def login_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔑 Введи свой <b>никнейм</b>:")
    await state.set_state(UserStates.login_username)

@dp.message(UserStates.login_username)
async def login_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not get_user_by_username(username):
        await message.answer("❌ Такого аккаунта нет:")
        return
    await state.update_data(login_username=username)
    await message.answer("🔒 Введи <b>пароль</b>:")
    await state.set_state(UserStates.login_password)

@dp.message(UserStates.login_password)
async def login_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    user_data = get_user_by_username(data['login_username'])
    if user_data and user_data[1] == hash_pass(password):
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        c.execute("UPDATE users SET user_id = ? WHERE username = ?", (message.from_user.id, data['login_username']))
        conn.commit(); conn.close()
        await message.answer(f"✅ Вход выполнен!", reply_markup=main_menu(message.from_user.id))
    else:
        await message.answer("❌ Неверный пароль!")
    await state.clear()

# --- АДМИНКА (РАСШИРЕННАЯ) ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    # Собираем статистику
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users_count = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_money = c.fetchone()[0] or 0
    conn.close()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast", style=ButtonStyle.PRIMARY))
    builder.row(
        InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="📉 Забрать монеты", callback_data="adm_take", style=ButtonStyle.DANGER)
    )
    builder.row(InlineKeyboardButton(text="🎁 Выдать NFT", callback_data="adm_nft", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    
    text = (f"⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            f"👥 Игроков: <b>{users_count}</b>\n"
            f"💰 Монет в экономике: <b>{total_money}</b>\n\n"
            f"Выбери действие:")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введи текст рассылки:")
    await state.set_state(UserStates.broadcast_msg)

@dp.message(UserStates.broadcast_msg)
async def adm_broadcast_send(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 <b>Администрация:</b>\n\n{message.text}", parse_mode="HTML")
            count += 1; await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {count}", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💸 Введи <b>ник</b> и <b>сумму</b> через пробел (например: `Dark 500`):", parse_mode="HTML")
    await state.set_state(UserStates.adm_give_coins)

@dp.message(UserStates.adm_give_coins)
async def adm_give_process(message: types.Message, state: FSMContext):
    try:
        username, amount = message.text.split()
        amount = int(amount)
    except:
        await message.answer("❌ Ошибка. Формат: `Ник 500`", parse_mode="HTML"); return
    user = get_user_by_username(username)
    if not user:
        await message.answer("❌ Игрок не найден."); return
    update_balance(user[0], amount)
    await message.answer(f"✅ Выдано {amount} монет игроку {username}.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_take")
async def adm_take(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📉 Введи <b>ник</b> и <b>сумму</b> для списания (например: `Dark 500`):", parse_mode="HTML")
    await state.set_state(UserStates.adm_take_coins)

@dp.message(UserStates.adm_take_coins)
async def adm_take_process(message: types.Message, state: FSMContext):
    try:
        username, amount = message.text.split()
        amount = int(amount)
    except:
        await message.answer("❌ Ошибка. Формат: `Ник 500`", parse_mode="HTML"); return
    user = get_user_by_username(username)
    if not user:
        await message.answer("❌ Игрок не найден."); return
    update_balance(user[0], -amount)
    await message.answer(f"✅ Списано {amount} монет у {username}.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "adm_nft")
async def adm_nft(callback: types.CallbackQuery, state: FSMContext):
    text = "🎁 Введи <b>ник</b> и <b>точное название NFT</b> через пробел.\n\nДоступные:\n"
    for name in SHOP_ITEMS.keys(): text += f"• {name}\n"
    text += "\nПример: `Dark 🕶️ Очки`"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(UserStates.adm_give_nft)

@dp.message(UserStates.adm_give_nft)
async def adm_nft_process(message: types.Message, state: FSMContext):
    # Отделяем ник от названия NFT (название может содержать пробелы)
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("❌ Ошибка. Формат: `Ник 🕶️ Очки`", parse_mode="HTML"); return
    username, nft_name = parts[0], parts[1].strip()
    
    if nft_name not in SHOP_ITEMS:
        await message.answer("❌ Такого NFT нет в магазине."); return
        
    user = get_user_by_username(username)
    if not user:
        await message.answer("❌ Игрок не найден."); return
        
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user[0], nft_name))
    conn.commit(); conn.close()
    
    await message.answer(f"✅ Выдано {nft_name} игроку {username}.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ТАБЛИЦА ЛИДЕРОВ (ИСПРАВЛЕНА) ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="📈 По рынку", callback_data="top_market", style=ButtonStyle.PRIMARY)
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text("🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\nВыбери категорию:", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "top_balance")
async def cb_top_balance(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    # Берем и ник, и баланс из базы (быстро, без запросов к Telegram)
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    
    text = "🏆 <b>ТОП ПО БАЛАНСУ</b>\n\n"
    for i, (uname, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {uname} — <b>{bal}</b> монет\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="leaderboard", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "top_market")
async def cb_top_market(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT username, market_earnings FROM users WHERE market_earnings > 0 ORDER BY market_earnings DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    
    if not top:
        await callback.answer("Пока нет продаж на рынке!", show_alert=True); return

    text = "📈 <b>ТОП ПО РЫНКУ</b>\n\n"
    for i, (uname, earn) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {uname} — <b>{earn}</b> монет\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="leaderboard", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ПРОФИЛЬ И БОНУСЫ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user: return
    _, username, balance, _, earnings = user
    items = get_inventory(callback.from_user.id)
    income = calculate_passive_income(callback.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ</b>\n\n🏷 Ник: <b>{username}</b>\n💰 Баланс: <b>{balance}</b>\n"
            f"🎒 NFT: <b>{len(items)}</b> шт.\n📈 Доход: <b>+{income}</b> к бонусу\n💼 Наторговал: <b>{earnings}</b>")
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
    update_bonus_time(callback.from_user.id, now)
    await callback.answer(f"🎉 Получено {total} монет!", show_alert=True)
    await callback.message.edit_text("🎁 Бонус получен!", reply_markup=main_menu(callback.from_user.id))

# --- МАГАЗИН ---
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        text += f"{name} — <b>{data['price']}</b>\n└ Доход: +{data['income']}\n\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🏪 РЫНОК", callback_data="market", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    if item in SHOP_ITEMS:
        if buy_item(callback.from_user.id, item, SHOP_ITEMS[item]["price"]):
            await callback.answer(f"✅ Куплено!", show_alert=True)
        else:
            await callback.answer("❌ Не хватает монет!", show_alert=True)

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
    print("Бот и веб-сервер запущены!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
