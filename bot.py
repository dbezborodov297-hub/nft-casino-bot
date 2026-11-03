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

BOT_TOKEN = "9184406467:AAEUfAvmvw2I420oLYuaGbQfw6p6Kg6Rn4M"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "💎 Алмаз": 100, "🗽 Статуя Свободы": 1200, "🕶️ Очки": 2300}

class GameStates(StatesGroup):
    waiting_bet = State()
    mine_bet = State()
    mine_play = State()
    duel_user = State()
    duel_bet = State()
    admin_give = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 1000, last_bonus INTEGER DEFAULT 0, diamonds REAL DEFAULT 0.0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY AUTOINCREMENT, p1 INTEGER, p2 INTEGER, bet INTEGER, board TEXT, turn INTEGER, status TEXT)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT balance, last_bonus, diamonds FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (1000, 0, 0.0)
    conn.close(); return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall(); conn.close()
    return [item[0] for item in items]

# --- МЕНЮ ---
def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="⚔️ ДУЭЛИ", callback_data="duel_menu"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    if user_id == ADMIN_ID: builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin"))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА (100)", callback_data="game_coin"), InlineKeyboardButton(text="🎲 КУБИК (100)", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mines"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    if message.from_user.username:
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("UPDATE users SET username = ? WHERE user_id = ?", (message.from_user.username, message.from_user.id))
        conn.commit(); conn.close()
    await message.answer("🌟 <b>ДОБРО ПОЖАЛОВАТЬ В NFT КАЗИНО</b> 🌟", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

# --- СБРОС СОСТОЯНИЙ (ЧИСТКА БАГОВ) ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "duel_menu")
async def cb_duel_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Создать дуэль", callback_data="duel_create"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚔️ <b>ДУЭЛИ</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _, dia = get_user(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>ПРОФИЛЬ</b>\n\n💰 Баланс: <b>{bal}</b>\n💎 Алмазы: <b>{dia}</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- КАЗИНО (КНОПКИ) ---
@dp.callback_query(F.data.startswith("game_"))
async def quick_game(callback: types.CallbackQuery):
    game = callback.data.split("_")[1]
    if game == "mines":
        await callback.message.edit_text("💣 Введи ставку для мин:")
        return
    if get_user(callback.from_user.id)[0] < 100: await callback.answer("❌ Мало монет!", show_alert=True); return
    if game == "coin":
        if random.choice([True, False]): update_balance(callback.from_user.id, 100); res = "🪙 ОРЕЛ! +100"
        else: update_balance(callback.from_user.id, -100); res = "🪙 РЕШКА. -100"
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(callback.from_user.id, 100); res = f"🎲 {u} vs {b}. Победа! +100"
        elif u < b: update_balance(callback.from_user.id, -100); res = f"🎲 {u} vs {b}. Проигрыш. -100"
        else: res = f"🎲 {u} vs {b}. Ничья."
    await callback.message.edit_text(f"{res}\n\n💰 Баланс: {get_user(callback.from_user.id)[0]}", reply_markup=casino_menu(), parse_mode="HTML")

# --- МИНЫ ---
@dp.message(GameStates.mine_bet)
async def mine_start(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Число!"); return
    update_balance(message.from_user.id, -bet)
    await state.update_data(bet=bet, mines=random.sample(range(25), 5), opened=[], mult=1.0)
    builder = InlineKeyboardBuilder()
    for i in range(25): builder.button(text="❓", callback_data=f"mc_{i}")
    builder.adjust(5); builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ (0)", callback_data="m_cash"))
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
    data['opened'].append(idx); data['mult'] = round(1.0 + (len(data['opened']) * 0.25), 2)
    await state.update_data(opened=data['opened'], mult=data['mult'])
    builder = InlineKeyboardBuilder()
    for i in range(25):
        if i in data['opened']: builder.button(text="💎", callback_data=f"mc_{i}")
        else: builder.button(text="❓", callback_data=f"mc_{i}")
    builder.adjust(5); builder.row(InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({int(data['bet']*data['mult'])})", callback_data="m_cash"))
    await callback.message.edit_text(f"💣 x{data['mult']}", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "m_cash")
async def mine_cash(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data: return
    update_balance(callback.from_user.id, int(data['bet'] * data['mult']))
    await callback.message.edit_text(f"💰 Забрано!", reply_markup=main_menu(callback.from_user.id))
    await state.clear()

# --- ДУЭЛИ ---
@dp.callback_query(F.data == "duel_create")
async def duel_create(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи @ник или ID друга:")
    await state.set_state(GameStates.duel_user)

@dp.message(GameStates.duel_user)
async def duel_user(message: types.Message, state: FSMContext):
    text = message.text.strip().replace("@", "")
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    if text.isdigit(): c.execute("SELECT user_id FROM users WHERE user_id = ?", (int(text),))
    else: c.execute("SELECT user_id FROM users WHERE username = ?", (text,))
    res = c.fetchone(); conn.close()
    if not res or res[0] == message.from_user.id: await message.answer("❌ Не найден или это ты."); return
    await state.update_data(op_id=res[0])
    await message.answer("💵 Введи ставку:")
    await state.set_state(GameStates.duel_bet)

@dp.message(GameStates.duel_bet)
async def duel_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Число!"); return
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"dacc_{message.from_user.id}_{bet}"))
    builder.row(InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"ddec"))
    try: await bot.send_message(data['op_id'], f"⚔️ ВЫЗОВ НА ДУЭЛЬ!\nСтавка: {bet}", reply_markup=builder.as_markup())
    except: await message.answer("❌ Не удалось отправить.")
    await message.answer("✅ Отправлено!")
    await state.clear()

@dp.callback_query(F.data.startswith("dacc_"))
async def duel_accept(callback: types.CallbackQuery):
    _, ch_id, bet = callback.data.split("_")
    ch_id, bet = int(ch_id), int(bet)
    board = "_________"
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (p1, p2, bet, board, turn, status) VALUES (?, ?, ?, ?, ?, 'play')", (ch_id, callback.from_user.id, bet, board, ch_id))
    d_id = c.lastrowid; conn.commit(); conn.close()
    update_balance(ch_id, -bet); update_balance(callback.from_user.id, -bet)
    await callback.message.edit_text("✅ Принято. Жди хода.")
    await bot.send_message(ch_id, "⚔️ Твой ход (❌):", reply_markup=duel_kb(board, d_id))

def duel_kb(board, d_id):
    builder = InlineKeyboardBuilder()
    for i in range(9): builder.button(text=board[i] if board[i] != "_" else "⬜️", callback_data=f"dc_{d_id}_{i}")
    builder.adjust(3); return builder.as_markup()

@dp.callback_query(F.data.startswith("dc_"))
async def duel_move(callback: types.CallbackQuery):
    _, d_id, idx = callback.data.split("_")
    d_id, idx = int(d_id), int(idx)
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT p1, p2, bet, board, turn FROM duels WHERE id = ? AND status = 'play'", (d_id,))
    d = c.fetchone()
    if not d: await callback.answer("Игра окончена."); conn.close(); return
    p1, p2, bet, board, turn = d
    if callback.from_user.id != turn or board[idx] != "_": await callback.answer("Не твой ход или занято!"); conn.close(); return
    
    sym = "❌" if callback.from_user.id == p1 else "⭕️"
    nb = list(board); nb[idx] = sym; nbs = "".join(nb)
    
    winner = None
    for a,b,c_i in [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]:
        if nbs[a] == nbs[b] == nbs[c_i] != "_": winner = nbs[a]; break
        
    if winner or "_" not in nbs:
        c.execute("UPDATE duels SET status = 'fin' WHERE id = ?", (d_id,))
        conn.commit(); conn.close()
        if winner:
            w_id = p1 if winner == "❌" else p2
            update_balance(w_id, bet*2)
            await callback.message.edit_text(f"🏆 Победа! +{bet*2}")
            try: await bot.send_message(p2 if w_id == p1 else p1, f"🏆 Соперник победил.")
            except: pass
        else:
            update_balance(p1, bet); update_balance(p2, bet)
            await callback.message.edit_text("🤝 Ничья!")
        return
        
    nturn = p2 if turn == p1 else p1
    c.execute("UPDATE duels SET board = ?, turn = ? WHERE id = ?", (nbs, nturn, d_id))
    conn.commit(); conn.close()
    
    await callback.message.edit_text("Ход сделан. Жди...")
    try: await bot.send_message(nturn, "⚔️ Твой ход:", reply_markup=duel_kb(nbs, d_id))
    except: pass

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin")
async def admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: await callback.answer("Нет доступа!", show_alert=True); return
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚙️ АДМИНКА", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи ID и сумму (через пробел):")
    await state.set_state(GameStates.admin_give)

@dp.message(GameStates.admin_give)
async def adm_give_proc(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amt = message.text.split()
        update_balance(int(uid), int(amt))
        await message.answer(f"✅ Выдано {amt} юзеру {uid}", reply_markup=main_menu(message.from_user.id))
    except: await message.answer("❌ Ошибка формата.")
    await state.clear()

# --- ЗАГЛУШКА ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
