import asyncio
import random
import sqlite3
import time
import hashlib
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ButtonStyle

BOT_TOKEN = "9020652959:AAFf-5eGmohPmVqDEG7rhR6n2r4ToHX3OJw"
# ВАЖНО: Вставь сюда свой Telegram ID (узнать можно у бота @userinfobot)
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Новые NFT с пассивным доходом (проценты)
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
    # Игры
    waiting_for_bet = State()
    minefield_bet = State()
    minefield_play = State()
    # Рынок
    selling_price = State()
    offer_amount = State()
    # Админка
    broadcast_msg = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    # Таблица пользователей: добавлены username и password_hash
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

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
    c.execute("SELECT user_id, password_hash FROM users WHERE username = ?", (username,))
    res = c.fetchone()
    conn.close()
    return res

def create_user(user_id, username, password):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, username, password_hash, balance) VALUES (?, ?, ?, 1000)", 
                  (user_id, username, hash_pass(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_market_earnings(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET market_earnings = market_earnings + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_bonus_time(user_id, timestamp):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return items

def calculate_passive_income(user_id):
    """Считает доход от всех NFT в инвентаре"""
    items = get_inventory(user_id)
    total_income = 0
    for _, name in items:
        if name in SHOP_ITEMS:
            total_income += SHOP_ITEMS[name]["income"]
    return total_income

def buy_item(user_id, item_name, price):
    if calculate_passive_income(user_id) + price > 100000: # Защита от читов
        pass
    
    bal, _, _, _, _ = get_user(user_id)
    if bal < price: return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit()
    conn.close()
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
    
    # Кнопка админки только для админа
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
    if user: # Если уже есть в базе
        text = f"👋 С возвращением, <b>{user[1]}</b>!\n💰 Баланс: <b>{user[2]}</b>\n📈 Доход с NFT: <b>+{calculate_passive_income(message.from_user.id)}</b> монет к бонусу."
        await message.answer(text, reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    else:
        text = "🌟 <b>Добро пожаловать в NFT CASINO!</b>\n\nДля начала игры тебе нужно создать аккаунт.\nНажми кнопку ниже:"
        await message.answer(text, reply_markup=auth_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "auth_reg")
async def reg_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи желаемый <b>никнейм</b> (без пробелов):", parse_mode="HTML")
    await state.set_state(UserStates.reg_username)

@dp.message(UserStates.reg_username)
async def reg_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if len(username) < 3 or " " in username:
        await message.answer("❌ Никнейм должен быть от 3 символов и без пробелов. Попробуй еще раз:")
        return
    
    if get_user_by_username(username):
        await message.answer("❌ Этот никнейм уже занят! Введи другой:")
        return
        
    await state.update_data(reg_username=username)
    await message.answer("🔒 Теперь придумай <b>пароль</b> (минимум 4 символа):", parse_mode="HTML")
    await state.set_state(UserStates.reg_password)

@dp.message(UserStates.reg_password)
async def reg_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 4:
        await message.answer("❌ Пароль слишком короткий (минимум 4 символа):")
        return
        
    data = await state.get_data()
    username = data['reg_username']
    
    if create_user(message.from_user.id, username, password):
        await message.answer(f"✅ Аккаунт <b>{username}</b> успешно создан!\nТвой стартовый баланс: 1000 монет.", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer("❌ Ошибка при создании. Возможно, ник занят.")
    await state.clear()

@dp.callback_query(F.data == "auth_login")
async def login_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔑 Введи свой <b>никнейм</b>:", parse_mode="HTML")
    await state.set_state(UserStates.login_username)

@dp.message(UserStates.login_username)
async def login_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not get_user_by_username(username):
        await message.answer("❌ Такого аккаунта нет. Введи ник еще раз:")
        return
    await state.update_data(login_username=username)
    await message.answer("🔒 Введи <b>пароль</b>:", parse_mode="HTML")
    await state.set_state(UserStates.login_password)

@dp.message(UserStates.login_password)
async def login_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    username = data['login_username']
    
    user_data = get_user_by_username(username)
    if user_data and user_data[1] == hash_pass(password):
        # Привязываем текущий Telegram ID к аккаунту (на случай смены устройства)
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        c.execute("UPDATE users SET user_id = ? WHERE username = ?", (message.from_user.id, username))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Успешный вход в аккаунт <b>{username}</b>!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer("❌ Неверный пароль!")
    await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ У тебя нет доступа!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    
    text = "⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\nВыбери действие:"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введи текст сообщения для рассылки всем игрокам:")
    await state.set_state(UserStates.broadcast_msg)

@dp.message(UserStates.broadcast_msg)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    count = 0
    await message.answer("🚀 Начинаю рассылку...")
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 <b>Сообщение от администрации:</b>\n\n{text}", parse_mode="HTML")
            count += 1
            await asyncio.sleep(0.05) # Защита от бана Telegram за спам
        except:
            pass
    await message.answer(f"✅ Рассылка завершена! Отправлено {count} пользователям.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ПРОФИЛЬ И БОНУСЫ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала авторизуйся /start")
        return
    
    _, username, balance, _, earnings = user
    items = get_inventory(callback.from_user.id)
    income = calculate_passive_income(callback.from_user.id)
    
    text = (f"╔══════════════════╗\n"
            f"   👤 <b>ПРОФИЛЬ</b>\n"
            f"╚══════════════════╝\n\n"
            f"🏷 Ник: <b>{username}</b>\n"
            f"💰 Баланс: <b>{balance}</b> монет\n"
            f"🎒 NFT: <b>{len(items)}</b> шт.\n"
            f"📈 Доход с NFT: <b>+{income}</b> к бонусу\n"
            f"💼 Заработано на рынке: <b>{earnings}</b>")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
        
    now = int(time.time())
    if now - user[3] < 86400:
        left = 86400 - (now - user[3])
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True)
        return
        
    # Считаем доход
    base_bonus = DAILY_BONUS
    nft_income = calculate_passive_income(callback.from_user.id)
    total_bonus = base_bonus + nft_income
    
    update_balance(callback.from_user.id, total_bonus)
    update_bonus_time(callback.from_user.id, now)
    
    await callback.answer(f"🎉 Бонус: +{base_bonus} (база) +{nft_income} (NFT) = {total_bonus} монет!", show_alert=True)
    await callback.message.edit_text("🎁 Бонус получен!", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- МАГАЗИН (С ПРОЦЕНТАМИ) ---
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        text += f"{name} — <b>{data['price']}</b> монет\n"
        text += f"└ Прибыль: <b>+{data['income']}</b> к бонусу\n\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🏪 РЫНОК ИГРОКОВ", callback_data="market", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    if item in SHOP_ITEMS:
        price = SHOP_ITEMS[item]["price"]
        if buy_item(callback.from_user.id, item, price):
            await callback.answer(f"✅ Куплено: {item}", show_alert=True)
        else:
            await callback.answer("❌ Не хватает монет!", show_alert=True)
