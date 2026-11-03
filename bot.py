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

BOT_TOKEN = "9184406467:AAEGHcnQFmvY2zRNLniKq1ANtZVUD9g6bAk"
ADMIN_ID = 8907438590
SUPPORT_USERNAME = "@Darkichn"
REFERRAL_REWARD = 0.5
STARS_GOAL = 150
STARS_REWARD = 1500

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {
    "🚀 Ракета": {"price": 50, "income": 5},
    "💎 Алмаз": {"price": 100, "income": 10},
    "🗽 Статуя Свободы": {"price": 1200, "income": 50},
    "🕶️ Очки": {"price": 2300, "income": 100}
}
DAILY_BONUS = 50

class GameStates(StatesGroup):
    waiting_bet = State()
    mine_bet = State()
    mine_play = State()
    duel_username = State()
    duel_bet = State()

class AdminStates(StatesGroup):
    give_coins = State()
    take_coins = State()
    broadcast = State()
    give_nft = State()
    ban_user = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT UNIQUE,
                 balance INTEGER DEFAULT 1000, 
                 last_bonus INTEGER DEFAULT 0,
                 referrer_id INTEGER DEFAULT NULL,
                 diamonds REAL DEFAULT 0.0,
                 is_banned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount_diamonds REAL, stars INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY AUTOINCREMENT, challenger_id INTEGER, opponent_id INTEGER, bet INTEGER, status TEXT, board TEXT, turn INTEGER)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, last_bonus, referrer_id, diamonds, is_banned FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        res = (user_id, None, 1000, 0, None, 0.0, 0)
    conn.close()
    return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall(); conn.close()
    return [item[0] for item in items]

def calculate_passive_income(user_id):
    items = get_inventory(user_id)
    return sum(SHOP_ITEMS[name]["income"] for name in items if name in SHOP_ITEMS)

# --- КЛАВИАТУРЫ ---
def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🤝 ДУЭЛИ", callback_data="duel_menu"))
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"), InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="ref_menu"))
    if user_id == ADMIN_ID: builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin_panel"))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"), InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС (x2)", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mines"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message, command: Command):
    user = get_user(message.from_user.id)
    if user[6] == 1: await message.answer("⛔ Ты забанен."); return
        
    if command.args and not user[4]:
        try:
            ref_id = int(command.args)
            if ref_id != message.from_user.id:
                conn = sqlite3.connect('game.db'); c = conn.cursor()
                c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref_id, message.from_user.id))
                c.execute("UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?", (REFERRAL_REWARD, ref_id))
                conn.commit(); conn.close()
                try: await bot.send_message(ref_id, f"🎉 Новый реферал! +{REFERRAL_REWARD} 💎")
                except: pass
        except: pass

    text = (f"🌟 <b>ДОБРО ПОЖАЛОВАТЬ В NFT КАЗИНО</b> 🌟\n\n"
            f"<blockquote>Здесь ты можешь зарабатывать монеты, играть с друзьями и выводить звёзды!</blockquote>\n\n"
            f"👇 <i>Используй кнопки ниже:</i>")
    await message.answer(text, reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

# --- ДУЭЛИ (КРЕСТИКИ-НОЛИКИ) ---
@dp.callback_query(F.data == "duel_menu")
async def cb_duel_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Вызвать на дуэль", callback_data="duel_create"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    text = "⚔️ <b>ДУЭЛИ (КРЕСТИКИ-НОЛИКИ)</b>\n\n<blockquote>Вызови друга на дуэль. Победитель забирает банк!</blockquote>"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "duel_create")
async def cb_duel_create(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи <b>юзернейм</b> противника (без @, или его ID):", parse_mode="HTML")
    await state.set_state(GameStates.duel_username)

@dp.message(GameStates.duel_username)
async def process_duel_username(message: types.Message, state: FSMContext):
    text = message.text.strip().replace("@", "")
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    # Ищем по юзернейму или ID
    if text.isdigit():
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (int(text),))
    else:
        c.execute("SELECT user_id FROM users WHERE username = ?", (text,))
    res = c.fetchone(); conn.close()
    
    if not res:
        await message.answer("❌ Игрок не найден в базе (он должен хотя бы раз зайти в бота)."); return
    if res[0] == message.from_user.id:
        await message.answer("❌ Нельзя вызвать самого себя."); return
        
    await state.update_data(opponent_id=res[0])
    await message.answer("💵 Введи сумму ставки (число):")
    await state.set_state(GameStates.duel_bet)

@dp.message(GameStates.duel_bet)
async def process_duel_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[2] < bet:
        await message.answer("❌ Не хватает монет!"); return
    
    data = await state.get_data()
    opponent_id = data['opponent_id']
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"duel_accept_{message.from_user.id}_{bet}"))
    builder.row(InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"duel_decline_{message.from_user.id}"))
    
    try:
        msg = await bot.send_message(opponent_id, 
            f"⚔️ <b>ТЕБЯ ВЫЗВАЛИ НА ДУЭЛЬ!</b>\n\n<blockquote>Игрок: <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>\nСтавка: <b>{bet}</b> монет\nИгра: Крестики-Нолики</blockquote>\n\n<i>У тебя 10 минут, чтобы принять.</i>",
            reply_markup=builder.as_markup(), parse_mode="HTML")
        
        # Таймер на 10 минут (600 секунд)
        await asyncio.sleep(600)
        
        # Проверяем, принята ли дуэль
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("SELECT status FROM duels WHERE challenger_id = ? AND opponent_id = ? AND bet = ? AND status = 'pending'", (message.from_user.id, opponent_id, bet))
        d = c.fetchone()
        conn.close()
        if d:
            await msg.edit_text("⌛️ <b>Время вышло!</b> Дуэль отменена.", parse_mode="HTML")
            
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить вызов (возможно, игрок заблокировал бота).")
    await state.clear()

@dp.callback_query(F.data.startswith("duel_accept_"))
async def cb_duel_accept(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    challenger_id, bet = int(parts[2]), int(parts[3])
    
    if get_user(callback.from_user.id)[2] < bet:
        await callback.answer("❌ У тебя не хватает монет!", show_alert=True); return
        
    # Создаем доску (9 пустых клеток)
    board = "_________" # 9 символов подчеркивания
    
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (challenger_id, opponent_id, bet, status, board, turn) VALUES (?, ?, ?, 'playing', ?, ?)", 
              (challenger_id, callback.from_user.id, bet, board, challenger_id))
    duel_id = c.lastrowid
    conn.commit(); conn.close()
    
    # Списываем ставки
    update_balance(challenger_id, -bet)
    update_balance(callback.from_user.id, -bet)
    
    await callback.message.edit_text("✅ Ты принял дуэль! Игра началась. Твой ход (❌):", reply_markup=duel_board_kb(board, duel_id, challenger_id))
    try:
        await bot.send_message(challenger_id, f"⚔️ <b>Дуэль принята!</b>\nСоперник сходил первым. Жди своего хода (⭕️).", parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("duel_decline_"))
async def cb_duel_decline(callback: types.CallbackQuery):
    challenger_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("❌ Ты отклонил дуэль.")
    try: await bot.send_message(challenger_id, "❌ Соперник отклонил твою дуэль.")
    except: pass

def duel_board_kb(board, duel_id, turn):
    builder = InlineKeyboardBuilder()
    for i in range(9):
        sym = board[i] if board[i] != "_" else "⬜️"
        builder.button(text=sym, callback_data=f"dcell_{duel_id}_{i}")
    builder.adjust(3)
    return builder.as_markup()

# --- ЛОГИКА ХОДА В КРЕСТИКИ-НОЛИКИ ---
@dp.callback_query(F.data.startswith("dcell_"))
async def cb_duel_move(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    duel_id, cell_idx = int(parts[1]), int(parts[2])
    
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT challenger_id, opponent_id, bet, board, turn FROM duels WHERE id = ? AND status = 'playing'", (duel_id,))
    duel = c.fetchone()
    if not duel:
        await callback.answer("Игра окончена или не найдена."); conn.close(); return
        
    ch_id, op_id, bet, board_str, turn_id = duel
    if callback.from_user.id != turn_id:
        await callback.answer("❌ Сейчас не твой ход!"); conn.close(); return
    if board_str[cell_idx] != "_":
        await callback.answer("❌ Клетка уже занята!"); conn.close(); return
        
    # Ставим символ (X для вызвавшего, O для принявшего)
    symbol = "❌" if callback.from_user.id == ch_id else "⭕️"
    new_board = list(board_str)
    new_board[cell_idx] = symbol
    new_board_str = "".join(new_board)
    
    # Проверка на победу
    win_lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    winner = None
    for a, b, c_idx in win_lines:
        if new_board_str[a] == new_board_str[b] == new_board_str[c_idx] != "_":
            winner = new_board_str[a]
            break
            
    if winner or "_" not in new_board_str:
        # Игра окончена
        c.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (duel_id,))
        conn.commit(); conn.close()
        
        if winner:
            winner_id = ch_id if winner == "❌" else op_id
            update_balance(winner_id, bet * 2)
            text = f"🏆 <b>ПОБЕДА!</b>\nИгрок {winner} выиграл {bet*2} монет!"
        else:
            update_balance(ch_id, bet)
            update_balance(op_id, bet)
            text = "🤝 <b>НИЧЬЯ!</b> Ставки возвращены."
            
        await callback.message.edit_text(text, parse_mode="HTML")
        await bot.send_message(op_id if callback.from_user.id == ch_id else ch_id, text, parse_mode="HTML")
        return
        
    # Передача хода
    next_turn = op_id if turn_id == ch_id else ch_id
    c.execute("UPDATE duels SET board = ?, turn = ? WHERE id = ?", (new_board_str, next_turn, duel_id))
    conn.commit(); conn.close()
    
    await callback.message.edit_reply_markup(reply_markup=duel_board_kb(new_board_str, duel_id, next_turn))
    try:
        await bot.send_message(next_turn, f"⚔️ Твой ход!", reply_markup=duel_board_kb(new_board_str, duel_id, next_turn))
        await callback.message.edit_text("Ход сделан. Ждем соперника...", reply_markup=duel_board_kb(new_board_str, duel_id, next_turn))
    except: pass

# --- МИННОЕ ПОЛЕ (СЕТКА 5x5) ---
@dp.callback_query(F.data == "game_mines")
async def cb_mines(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💣 <b>МИННОЕ ПОЛЕ</b>\n\nВведи сумму ставки (число):", parse_mode="HTML")
    await state.set_state(GameStates.mine_bet)

@dp.message(GameStates.mine_bet)
async def process_mine_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[2] < bet:
        await message.answer("❌ Не хватает монет!"); await state.clear(); return
        
    update_balance(message.from_user.id, -bet)
    # Генерируем 5 мин на поле из 25 клеток
    mines = set(random.sample(range(25), 5))
    await state.update_data(bet=bet, mines=list(mines), opened=[], mult=1.0)
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        builder.button(text="❓", callback_data=f"mcell_{i}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text=f"💰 ЗАБРАТЬ (0)", callback_data="mcashout"))
    
    await message.answer(f"💣 Ставка: {bet}\nОткрывай клетки. Чем больше откроешь, тем выше множитель:", reply_markup=builder.as_markup())
    await state.set_state(GameStates.mine_play)

@dp.callback_query(GameStates.mine_play, F.data.startswith("mcell_"))
async def cb_mine_click(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    data = await state.get_data()
    bet, mines, opened, mult = data['bet'], data['mines'], data['opened'], data['mult']
    
    if idx in opened: await callback.answer("Уже открыто!"); return
    
    if idx in mines:
        await callback.message.edit_text(f"💥 <b>БУМ!</b> Ты наступил на мину и потерял {bet} монет.", reply_markup=casino_menu(), parse_mode="HTML")
        await state.clear(); return
        
    opened.append(idx)
    # Множитель растет: (25 / (25 - кол-во_мин - открытых)) 
    mult = round(1.0 + (len(opened) * 0.25), 2)
    await state.update_data(opened=opened, mult=mult)
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        if i in opened: builder.button(text="💎", callback_data=f"mcell_{i}")
        else: builder.button(text="❓", callback_data=f"mcell_{i}")
    builder.adjust(5)
    
    win_amount = int(bet * mult)
    builder.row(InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({win_amount})", callback_data="mcashout"))
    
    await callback.message.edit_text(f"💣 Множитель: <b>x{mult}</b>\nОткрыто: {len(opened)}/20", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "mcashout")
async def cb_mine_cashout(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet, mult = data['bet'], data['mult']
    win = int(bet * mult)
    update_balance(callback.from_user.id, win)
    await callback.message.edit_text(f"💰 Забрано <b>{win}</b> монет! (x{mult})", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")
    await state.clear()

# (Хэндлеры профиля, рефералки, админки и других игр оставил без изменений, они такие же красивые)

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
