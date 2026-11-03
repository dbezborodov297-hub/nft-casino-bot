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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9184406467:AAHOIqK-7lkI7jyHoWq42MPILGyWibEY0dQ"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "💎 Алмаз": 100, "🗽 Статуя Свободы": 1200, "🕶️ Очки": 2300}

class GameStates(StatesGroup):
    waiting_custom_bet = State()
    mine_bet = State()
    mine_play = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 1000, last_bonus INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (1000, 0)
    conn.close(); return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

# --- МЕНЮ ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА (100)", callback_data="bet_coin_100"), InlineKeyboardButton(text="🎲 КУБИК (100)", callback_data="bet_dice_100"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mines"))
    builder.row(InlineKeyboardButton(text="💰 СВОЯ СТАВКА", callback_data="custom_bet"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer("🌟 <b>ДОБРО ПОЖАЛОВАТЬ!</b>", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def prof(callback: types.CallbackQuery):
    bal, _ = get_user(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>ПРОФИЛЬ</b>\n\n💰 Баланс: <b>{bal}</b>", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def daily(callback: types.CallbackQuery):
    _, last = get_user(callback.from_user.id)
    if time.time() - last < 86400:
        await callback.answer("⏳ Рано!", show_alert=True); return
    update_balance(callback.from_user.id, 50)
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (int(time.time()), callback.from_user.id))
    conn.commit(); conn.close()
    await callback.answer("🎉 +50 монет!", show_alert=True)

# --- КАЗИНО (КНОПКИ) ---
@dp.callback_query(F.data == "casino")
async def casino(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("bet_"))
async def quick_bet(callback: types.CallbackQuery):
    _, game, amount = callback.data.split("_")
    amount = int(amount)
    bal = get_user(callback.from_user.id)[0]
    if bal < amount:
        await callback.answer("❌ Мало монет!", show_alert=True); return
    
    if game == "coin":
        if random.choice([True, False]): update_balance(callback.from_user.id, amount); res = f"🪙 ОРЕЛ! +{amount}"
        else: update_balance(callback.from_user.id, -amount); res = f"🪙 РЕШКА. -{amount}"
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(callback.from_user.id, amount); res = f"🎲 {u} vs {b}. Победа! +{amount}"
        elif u < b: update_balance(callback.from_user.id, -amount); res = f"🎲 {u} vs {b}. Проигрыш. -{amount}"
        else: res = f"🎲 {u} vs {b}. Ничья."

    await callback.message.edit_text(f"{res}\n\n💰 Баланс: {get_user(callback.from_user.id)[0]}", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "custom_bet")
async def custom_bet(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💵 Введи сумму ставки числом:")
    await state.set_state(GameStates.waiting_custom_bet)

@dp.message(GameStates.waiting_custom_bet)
async def process_custom(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Число!"); return
    if get_user(message.from_user.id)[0] < bet: await message.answer("❌ Мало монет!"); await state.clear(); return
    
    if random.choice([True, False]): update_balance(message.from_user.id, bet); res = f"🪙 Победа! +{bet}"
    else: update_balance(message.from_user.id, -bet); res = f"🪙 Проигрыш. -{bet}"
    
    await message.answer(f"{res}\n💰 Баланс: {get_user(message.from_user.id)[0]}", reply_markup=main_menu())
    await state.clear()

# --- МИНЫ ---
@dp.callback_query(F.data == "game_mines")
async def mines(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💣 Введи ставку для мин:")
    await state.set_state(GameStates.mine_bet)

@dp.message(GameStates.mine_bet)
async def mine_start(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Число!"); return
    if get_user(message.from_user.id)[0] < bet: await message.answer("❌ Мало!"); await state.clear(); return
    
    update_balance(message.from_user.id, -bet)
    mines = set(random.sample(range(25), 5))
    await state.update_data(bet=bet, mines=list(mines), opened=[], mult=1.0)
    
    builder = InlineKeyboardBuilder()
    for i in range(25): builder.button(text="❓", callback_data=f"mc_{i}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ (0)", callback_data="m_cash"))
    
    await message.answer(f"💣 Ставка: {bet}", reply_markup=builder.as_markup())
    await state.set_state(GameStates.mine_play)

@dp.callback_query(GameStates.mine_play, F.data.startswith("mc_"))
async def mine_click(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    data = await state.get_data()
    if idx in data['opened']: await callback.answer("Уже открыто!"); return
    
    if idx in data['mines']:
        await callback.message.edit_text(f"💥 БУМ! Потеряно {data['bet']}", reply_markup=casino_menu())
        await state.clear(); return
        
    data['opened'].append(idx)
    data['mult'] = round(1.0 + (len(data['opened']) * 0.25), 2)
    await state.update_data(opened=data['opened'], mult=data['mult'])
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        if i in data['opened']: builder.button(text="💎", callback_data=f"mc_{i}")
        else: builder.button(text="❓", callback_data=f"mc_{i}")
    builder.adjust(5)
    win = int(data['bet'] * data['mult'])
    builder.row(InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({win})", callback_data="m_cash"))
    
    await callback.message.edit_text(f"💣 x{data['mult']} | Открыто: {len(data['opened'])}", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "m_cash")
async def mine_cash(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data: return
    win = int(data['bet'] * data['mult'])
    update_balance(callback.from_user.id, win)
    await callback.message.edit_text(f"💰 Забрано {win}!", reply_markup=main_menu())
    await state.clear()

# --- ЗАГЛУШКА ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
