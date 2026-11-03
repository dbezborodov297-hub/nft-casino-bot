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

BOT_TOKEN = "9184406467:AAEQHc_ViPy6NhbRlKqexzDyGOnxnV7SYC0"
ADMIN_ID = 8907438590
SUPPORT = "@Darkichn"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "💎 Алмаз": 100, "🗽 Статуя Свободы": 1200, "🕶️ Очки": 2300}

class GameStates(StatesGroup):
    waiting_custom_bet = State()
    mine_bet = State()
    mine_play = State()
    duel_user = State()
    duel_bet = State()
    admin_give = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT, 
                 balance INTEGER DEFAULT 1000, 
                 last_bonus INTEGER DEFAULT 0,
                 referrer_id INTEGER DEFAULT NULL,
                 diamonds INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY AUTOINCREMENT, p1 INTEGER, p2 INTEGER, bet INTEGER, board TEXT, turn INTEGER, status TEXT)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT balance, last_bonus, referrer_id, diamonds FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (1000, 0, None, 0)
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

# --- КЛАВИАТУРЫ ---
def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="⚔️ ДУЭЛИ", callback_data="duel_menu"), InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard"), InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    if user_id == ADMIN_ID: builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin"))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА (100)", callback_data="game_coin"), InlineKeyboardButton(text="🎲 КУБИК (100)", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mines"))
    builder.row(InlineKeyboardButton(text="💰 СВОЯ СТАВКА", callback_data="custom_bet"))
    builder.row(InlineKeyboardButton(text="📖 ПРАВИЛА", callback_data="rules"), InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

# --- СТАРТ (КРАСИВО) ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    if message.from_user.username:
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("UPDATE users SET username = ? WHERE user_id = ?", (message.from_user.username, message.from_user.id))
        conn.commit(); conn.close()

    text = (f"🌟 <b>ДОБРО ПОЖАЛОВАТЬ В NFT КАЗИНО!</b> 🌟\n\n"
            f"<blockquote>"
            f"💎 Здесь ты можешь зарабатывать виртуальные монеты, покупать уникальные NFT, "
            f"играть в азартные игры и вызывать друзей на дуэли!\n\n"
            f"📈 <b>Твои возможности:</b>\n"
            f"• 🎰 Играть в казино (Монетка, Кубик, Минное поле)\n"
            f"• ⚔️ Бросать вызов друзьям (Крестики-нолики)\n"
            f"• 🛒 Покупать NFT и получать пассивный доход\n"
            f"• 🏆 Подниматься в таблице лидеров\n\n"
            f"👇 <i>Нажми на кнопку ниже, чтобы начать!</i>"
            f"</blockquote>\n\n"
            f"<b>Твой текущий баланс:</b> <code>{get_user(message.from_user.id)[0]}</code> монет.")
            
    await message.answer(text, reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\nВыбери раздел:", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _, ref, dia = get_user(callback.from_user.id)
    items = get_inventory(callback.from_user.id)
    user_link = f"<a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a>"
    
    text = (f"╔════════════════════════╗\n"
            f"      👤 <b>ТВОЙ ПРОФИЛЬ</b>\n"
            f"╚════════════════════════╝\n\n"
            f"<blockquote>"
            f"🆔 <b>Игрок:</b> {user_link}\n"
            f"💰 <b>Баланс:</b> {bal} монет\n"
            f"💎 <b>Алмазы:</b> {dia} шт.\n"
            f"🎒 <b>NFT в коллекции:</b> {len(items)} шт.\n"
            f"👥 <b>Рефералов:</b> {ref if ref else 0}\n"
            f"</blockquote>\n\n"
            f"<i>Чтобы заработать больше — играй в казино!</i>")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- ТОП (ТАБЛИЦА ЛИДЕРОВ) ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\n<blockquote>"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        user_link = f"<a href='tg://user?id={uid}'>Игрок {uid}</a>"
        text += f"{medal} {user_link} — <b>{bal}</b> монет\n"
    text += "</blockquote>\n\n<i>Нажми на ID, чтобы открыть профиль</i>"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ПРАВИЛА ИГР ---
@dp.callback_query(F.data == "rules")
async def cb_rules(callback: types.CallbackQuery):
    text = (f"📖 <b>ПРАВИЛА ИГР</b>\n\n"
            f"<blockquote>"
            f"<b>🪙 Монетка</b>\n"
            f"Ставка 100 монет. 50/50 шанс выиграть или проиграть.\n\n"
            f"<b>🎲 Кубик</b>\n"
            f"Твой кубик против кубика бота. У кого больше — тот победил. Ставка 100.\n\n"
            f"<b>💣 Минное поле</b>\n"
            f"На поле 5х5 (25 клеток) спрятано 5 мин. Открывай безопасные клетки, "
            f"с каждой открытой клеткой твой множитель растет. Если попадешь на мину — "
            f"теряешь ставку. В любой момент можно нажать «Забрать» и забрать текущий выигрыш.\n\n"
            f"<b>⚔️ Дуэли (Крестики-Нолики)</b>\n"
            f"Вызываешь друга по @нику. Он должен принять вызов. Побеждает тот, кто первым "
            f"соберет три символа в ряд. Победитель забирает банк (ставку обоих игроков)."
            f"</blockquote>")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КАЗИНО ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = "🎰 <b>КАЗИНО</b>\n\n<blockquote>Выбери игру и испытай удачу:</blockquote>"
    await callback.message.edit_text(text, reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_"))
async def quick_game(callback: types.CallbackQuery):
    game = callback.data.split("_")[1]
    if get_user(callback.from_user.id)[0] < 100: await callback.answer("❌ Мало монет!", show_alert=True); return
    if game == "coin":
        if random.choice([True, False]): update_balance(callback.from_user.id, 100); res = "🪙 <b>ОРЕЛ!</b> Ты выиграл <b>+100</b> монет!"
        else: update_balance(callback.from_user.id, -100); res = "🪙 <b>РЕШКА.</b> Ты проиграл <b>-100</b> монет."
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(callback.from_user.id, 100); res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n🎉 <b>Победа!</b> +100"
        elif u < b: update_balance(callback.from_user.id, -100); res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n😢 <b>Поражение.</b> -100"
        else: res = f"🎲 Твой кубик: {u}\nКубик бота: {b}\n🤝 <b>Ничья.</b>"
    
    await callback.message.edit_text(f"{res}\n\n💰 Баланс: <b>{get_user(callback.from_user.id)[0]}</b>", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "custom_bet")
async def custom_bet(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💵 Введи сумму ставки числом:")
    await state.set_state(GameStates.waiting_custom_bet)

@dp.message(GameStates.waiting_custom_bet)
async def process_custom(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[0] < bet: await message.answer("❌ Мало монет!"); await state.clear(); return
    
    if random.choice([True, False]): update_balance(message.from_user.id, bet); res = f"🪙 <b>Победа!</b> +{bet}"
    else: update_balance(message.from_user.id, -bet); res = f"🪙 <b>Проигрыш.</b> -{bet}"
    
    await message.answer(f"{res}\n💰 Баланс: <b>{get_user(message.from_user.id)[0]}</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# --- МИНЫ ---
@dp.callback_query(F.data == "game_mines")
async def mines(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💣 <b>МИННОЕ ПОЛЕ</b>\n\nВведи ставку числом:", parse_mode="HTML")
    await state.set_state(GameStates.mine_bet)

@dp.message(GameStates.mine_bet)
async def mine_start(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[0] < bet: await message.answer("❌ Мало монет!"); await state.clear(); return
    
    update_balance(message.from_user.id, -bet)
    mines = set(random.sample(range(25), 5))
    await state.update_data(bet=bet, mines=list(mines), opened=[], mult=1.0)
    
    builder = InlineKeyboardBuilder()
    for i in range(25): builder.button(text="❓", callback_data=f"mc_{i}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ (0)", callback_data="m_cash"))
    
    await message.answer(f"💣 <b>Ставка:</b> {bet}\n\nОткрывай клетки. Чем больше откроешь, тем выше множитель!", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(GameStates.mine_play)

@dp.callback_query(GameStates.mine_play, F.data.startswith("mc_"))
async def mine_click(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    data = await state.get_data()
    if idx in data['opened']: await callback.answer("Уже открыто!"); return
    
    if idx in data['mines']:
        await callback.message.edit_text(f"💥 <b>БУМ!</b> Ты наступил на мину и потерял <b>{data['bet']}</b> монет.", reply_markup=casino_menu(), parse_mode="HTML")
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
    
    await callback.message.edit_text(f"💣 <b>Множитель:</b> x{data['mult']}\nОткрыто: {len(data['opened'])}/20", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "m_cash")
async def mine_cash(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data: return
    win = int(data['bet'] * data['mult'])
    update_balance(callback.from_user.id, win)
    await callback.message.edit_text(f"💰 Ты забрал <b>{win}</b> монет! (x{data['mult']})", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")
    await state.clear()

# --- ДУЭЛИ ---
@dp.callback_query(F.data == "duel_menu")
async def cb_duel_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Создать дуэль", callback_data="duel_create"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚔️ <b>ДУЭЛИ</b>\n\nВызови друга на игру в Крестики-Нолики!", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "duel_create")
async def duel_create(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи <b>@ник</b> или <b>ID</b> друга:", parse_mode="HTML")
    await state.set_state(GameStates.duel_user)

@dp.message(GameStates.duel_user)
async def duel_user(message: types.Message, state: FSMContext):
    text = message.text.strip().replace("@", "")
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    if text.isdigit(): c.execute("SELECT user_id FROM users WHERE user_id = ?", (int(text),))
    else: c.execute("SELECT user_id FROM users WHERE username = ?", (text,))
    res = c.fetchone(); conn.close()
    if not res: await message.answer("❌ Игрок не найден (он должен был зайти в бота)."); return
    if res[0] == message.from_user.id: await message.answer("❌ Нельзя вызвать себя."); return
    await state.update_data(op_id=res[0])
    await message.answer("💵 Введи сумму ставки:")
    await state.set_state(GameStates.duel_bet)

@dp.message(GameStates.duel_bet)
async def duel_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[0] < bet: await message.answer("❌ Мало монет!"); await state.clear(); return
    
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"dacc_{message.from_user.id}_{bet}"))
    builder.row(InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data="ddec"))
    
    try:
        await bot.send_message(data['op_id'], f"⚔️ <b>ТЕБЯ ВЫЗВАЛИ НА ДУЭЛЬ!</b>\n\n<blockquote>Ставка: <b>{bet}</b> монет\nИгра: Крестики-Нолики</blockquote>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await message.answer("✅ Вызов отправлен!")
    except: await message.answer("❌ Не удалось отправить (бот заблокирован).")
    await state.clear()

@dp.callback_query(F.data.startswith("dacc_"))
async def duel_accept(callback: types.CallbackQuery):
    _, ch_id, bet = callback.data.split("_")
    ch_id, bet = int(ch_id), int(bet)
    
    if get_user(callback.from_user.id)[0] < bet: await callback.answer("❌ Мало монет!", show_alert=True); return
    
    board = "_________"
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (p1, p2, bet, board, turn, status) VALUES (?, ?, ?, ?, ?, 'play')", (ch_id, callback.from_user.id, bet, board, ch_id))
    d_id = c.lastrowid; conn.commit(); conn.close()
    
    update_balance(ch_id, -bet); update_balance(callback.from_user.id, -bet)
    await callback.message.edit_text("✅ Ты принял дуэль. Жди хода соперника.")
    await bot.send_message(ch_id, "⚔️ <b>Твой ход (❌):</b>", reply_markup=duel_kb(board, d_id), parse_mode="HTML")

@dp.callback_query(F.data == "ddec")
async def duel_decline(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Ты отклонил дуэль.")

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
    if callback.from_user.id != turn: await callback.answer("❌ Не твой ход!"); conn.close(); return
    if board[idx] != "_": await callback.answer("❌ Занято!"); conn.close(); return
    
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
            await callback.message.edit_text(f"🏆 <b>ПОБЕДА!</b> Ты выиграл {bet*2} монет!")
            try: await bot.send_message(p2 if w_id == p1 else p1, f"🏆 Соперник победил и забрал {bet*2}.")
            except: pass
        else:
            update_balance(p1, bet); update_balance(p2, bet)
            await callback.message.edit_text("🤝 <b>НИЧЬЯ!</b>")
        return
        
    nturn = p2 if turn == p1 else p1
    c.execute("UPDATE duels SET board = ?, turn = ? WHERE id = ?", (nbs, nturn, d_id))
    conn.commit(); conn.close()
    
    await callback.message.edit_text("Ход сделан. Жди...")
    try: await bot.send_message(nturn, "⚔️ <b>Твой ход:</b>", reply_markup=duel_kb(nbs, d_id), parse_mode="HTML")
    except: pass

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin")
async def admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: await callback.answer("Нет доступа!", show_alert=True); return
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("⚙️ <b>АДМИНКА</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

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
    except: await message.answer("❌ Ошибка.")
    await state.clear()

# --- ЗАГЛУШКА ДЛЯ RENDER ---
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
