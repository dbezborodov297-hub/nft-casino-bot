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

BOT_TOKEN = "9184406467:AAFeavoCTZpOSLxO0S4C5gIzBX9lseYI3ZU"
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

class GameStates(StatesGroup):
    waiting_bet = State()
    mine_bet = State()

class AdminStates(StatesGroup):
    give_coins = State()
    take_coins = State()
    broadcast = State()

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

# --- КЛАВИАТУРЫ ---
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

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"),
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice")
    )
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС (x2)", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mines"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

def mine_mult_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1.0x (Легко)", callback_data="mines_mult_1.0"),
        InlineKeyboardButton(text="1.5x", callback_data="mines_mult_1.5")
    )
    builder.row(
        InlineKeyboardButton(text="2.0x (Средне)", callback_data="mines_mult_2.0"),
        InlineKeyboardButton(text="3.0x", callback_data="mines_mult_3.0")
    )
    builder.row(
        InlineKeyboardButton(text="5.0x (Хардкор)", callback_data="mines_mult_5.0")
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino"))
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
    user_link = f"<a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a>"
    text = (f"👤 <b>ПРОФИЛЬ</b>\n\n🆔 Игрок: {user_link}\n💰 Баланс: <b>{bal}</b>\n"
            f"🎒 NFT: <b>{len(items)}</b>\n📈 Доход: <b>+{income}</b>")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    _, last_bonus = get_user(callback.from_user.id)
    now = int(time.time())
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True); return
    total = DAILY_BONUS + calculate_passive_income(callback.from_user.id)
    update_balance(callback.from_user.id, total)
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now, callback.from_user.id))
    conn.commit(); conn.close()
    await callback.answer(f"🎉 Получено {total} монет!", show_alert=True)

# --- ТОП (КРАСИВО, ЧЕРЕЗ ЦИТАТУ) ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\n<blockquote>"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}. "
        user_link = f"<a href='tg://user?id={uid}'>{uid}</a>"
        text += f"{medal} {user_link} — <b>{bal}</b> монет\n"
    text += "</blockquote>\n\n<i>Нажми на ID, чтобы открыть профиль игрока</i>"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

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
            await callback.answer("❌ Не хватает монет!", show_alert=True); return
        update_balance(callback.from_user.id, -SHOP_ITEMS[item]["price"])
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item))
        conn.commit(); conn.close()
        await callback.answer(f"✅ Куплено!", show_alert=True)

@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n<blockquote>" + ("Пусто." if not items else "\n".join(f"• {name}" for name in items)) + "</blockquote>"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- КАЗИНО ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>\n\nВыбери игру:", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_"))
async def cb_game_select(callback: types.CallbackQuery, state: FSMContext):
    game = callback.data.split("_")[1]
    if game == "mines":
        await callback.message.edit_text("💣 <b>МИННОЕ ПОЛЕ</b>\n\nВыбери сложность (множитель). Чем выше множитель, тем сложнее выиграть:", reply_markup=mine_mult_menu(), parse_mode="HTML")
        return
        
    names = {"coin": "🪙 Монетка", "dice": "🎲 Кубик", "darts": "🎯 Дартс"}
    await state.update_data(game=game)
    await callback.message.edit_text(f"{names[game]}\n\n💵 Введи сумму ставки (число):", parse_mode="HTML")
    await state.set_state(GameStates.waiting_bet)

@dp.message(GameStates.waiting_bet)
async def process_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[0] < bet:
        await message.answer("❌ Не хватает монет!"); await state.clear(); return

    data = await state.get_data()
    game = data['game']
    res = ""
    
    if game == "coin":
        if random.choice([True, False]): update_balance(message.from_user.id, bet); res = f"🪙 ОРЕЛ! +{bet}"
        else: update_balance(message.from_user.id, -bet); res = f"🪙 РЕШКА. -{bet}"
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(message.from_user.id, bet); res = f"🎲 {u} vs {b}. Победа! +{bet}"
        elif u < b: update_balance(message.from_user.id, -bet); res = f"🎲 {u} vs {b}. Поражение. -{bet}"
        else: res = f"🎲 {u} vs {b}. Ничья."
    elif game == "darts":
        if random.random() < 0.4: win = int(bet*2); update_balance(message.from_user.id, win); res = f"🎯 В яблочко! +{win}"
        else: update_balance(message.from_user.id, -bet); res = f"🎯 Мимо. -{bet}"
        
    new_bal = get_user(message.from_user.id)[0]
    await message.answer(f"<blockquote>{res}</blockquote>\n\n💰 Баланс: <b>{new_bal}</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# --- МИННОЕ ПОЛЕ (МНОЖИТЕЛИ) ---
@dp.callback_query(F.data.startswith("mines_mult_"))
async def cb_mines_mult(callback: types.CallbackQuery, state: FSMContext):
    mult = float(callback.data.split("_")[2])
    await state.update_data(mult=mult)
    await callback.message.edit_text(f"💣 Множитель: <b>{mult}x</b>\n\nВведи сумму ставки:", parse_mode="HTML")
    await state.set_state(GameStates.mine_bet)

@dp.message(GameStates.mine_bet)
async def process_mine_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: await message.answer("❌ Введи число!"); return
    if get_user(message.from_user.id)[0] < bet:
        await message.answer("❌ Не хватает монет!"); await state.clear(); return

    data = await state.get_data()
    mult = data['mult']
    
    # Шанс победы зависит от множителя (1.0 = 90%, 5.0 = 10%)
    win_chance = 1.0 - (mult * 0.16) 
    if random.random() < win_chance:
        win = int(bet * mult)
        update_balance(message.from_user.id, win)
        res = f"💎 Ты выжил! Множитель {mult}x сработал. +{win} монет!"
    else:
        update_balance(message.from_user.id, -bet)
        res = f"💥 БУМ! Ты наступил на мину. Потеряно {bet} монет."

    await message.answer(f"<blockquote>{res}</blockquote>\n\n💰 Баланс: <b>{get_user(message.from_user.id)[0]}</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True); return
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); users_count = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users"); total_money = c.fetchone()[0] or 0
    conn.close()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="📉 Забрать монеты", callback_data="adm_take"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    
    text = f"⚙️ <b>АДМИНКА</b>\n\n<blockquote>👥 Игроков: {users_count}\n💰 Монет: {total_money}</blockquote>"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💸 Введи <b>ID</b> и <b>сумму</b> через пробел:", parse_mode="HTML")
    await state.set_state(AdminStates.give_coins)

@dp.message(AdminStates.give_coins)
async def process_give(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amount = message.text.split()
        update_balance(int(uid), int(amount))
        await message.answer(f"✅ Выдано {amount} монет пользователю {uid}.", reply_markup=main_menu(message.from_user.id))
    except: await message.answer("❌ Ошибка формата.")
    await state.clear()

@dp.callback_query(F.data == "adm_take")
async def adm_take(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📉 Введи <b>ID</b> и <b>сумму</b> для списания:", parse_mode="HTML")
    await state.set_state(AdminStates.take_coins)

@dp.message(AdminStates.take_coins)
async def process_take(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amount = message.text.split()
        update_balance(int(uid), -int(amount))
        await message.answer(f"✅ Списано {amount} монет у {uid}.", reply_markup=main_menu(message.from_user.id))
    except: await message.answer("❌ Ошибка формата.")
    await state.clear()

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введи текст рассылки:")
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id FROM users"); users = c.fetchall(); conn.close()
    count = 0
    for (uid,) in users:
        try: await bot.send_message(uid, f"📢 <b>Сообщение:</b>\n\n{message.text}", parse_mode="HTML"); count += 1; await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {count}", reply_markup=main_menu(message.from_user.id))
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
