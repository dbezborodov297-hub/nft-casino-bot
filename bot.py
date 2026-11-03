import asyncio
import random
import sqlite3
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9020652959:AAEzaBu5jk9TOWq9pAxcRIxg9zYabRbpMGQ"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "🗽 Статуя Свободы": 1200}
DAILY_BONUS = 50

class GameStates(StatesGroup):
    waiting_for_bet = State()
    minefield_bet = State()
    minefield_play = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (user_id INTEGER, item_name TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance, last_bonus) VALUES (?, 1000, 0)", (user_id,))
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

def update_bonus_time(user_id, timestamp):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return [i[0] for i in items]

def buy_item(user_id, item_name, price):
    bal, _ = get_user(user_id)
    if bal < price: return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit()
    conn.close()
    return True

# --- Клавиатуры ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(
        InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"),
        InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory")
    )
    builder.row(
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"),
        InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily")
    )
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"),
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice")
    )
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mine"))
    builder.row(InlineKeyboardButton(text="🔙 В ГЛАВНОЕ МЕНЮ", callback_data="back_main"))
    return builder.as_markup()

# --- Хэндлеры ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"🌟 <b>Добро пожаловать в NFT CASINO!</b> 🌟\n\n"
            f"👋 Привет, <b>{message.from_user.first_name}</b>!\n"
            f"💳 Твой стартовый баланс: <b>1000 монет</b>.\n\n"
            f"<i>Жми на кнопки ниже, чтобы начать зарабатывать!</i> 👇")
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>\n\nВыбери раздел:", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _ = get_user(callback.from_user.id)
    text = (f"╔══════════════════╗\n"
            f"   👤 <b>ТВОЙ ПРОФИЛЬ</b>\n"
            f"╚══════════════════╝\n\n"
            f"💰 Баланс: <b>{bal}</b> монет\n"
            f"🏆 Статус: <i>Новичок</i>\n\n"
            f"<i>Играй, чтобы повысить статус!</i>")
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, last_bonus = get_user(user_id)
    now = int(time.time())
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        hours = left // 3600
        minutes = (left % 3600) // 60
        await callback.answer(f"⏳ Бонус уже получен!\nЖди: {hours}ч {minutes}м", show_alert=True)
        return
    
    update_balance(user_id, DAILY_BONUS)
    update_bonus_time(user_id, now)
    await callback.answer(f"🎉 Ты получил {DAILY_BONUS} монет!", show_alert=True)
    await callback.message.edit_text("🎁 <b>Бонус получен!</b>\n\nВозвращайся завтра за новой порцией.", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = ("╔══════════════════╗\n"
            "   🛒 <b>МАГАЗИН NFT</b>\n"
            "╚══════════════════╝\n\n")
    builder = InlineKeyboardBuilder()
    for name, price in SHOP_ITEMS.items():
        text += f"🔹 {name} — <b>{price}</b> монет\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    price = SHOP_ITEMS.get(item)
    if not price: return
    
    if buy_item(callback.from_user.id, item, price):
        await callback.answer(f"✅ Успешно куплено: {item}", show_alert=True)
    else:
        await callback.answer("❌ Недостаточно монет!", show_alert=True)

@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    text = ("╔══════════════════╗\n"
            "   🎒 <b>ИНВЕНТАРЬ</b>\n"
            "╚══════════════════╝\n\n")
    if not items:
        text += "<i>Тут пока пусто. Купи свою первую NFT в магазине!</i>"
    else:
        for i in items:
            text += f"🔸 {i}\n"
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")

# --- Казино ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    text = ("╔══════════════════╗\n"
            "   🎰 <b>КАЗИНО</b>\n"
            "╚══════════════════╝\n\n"
            "Выбери игру и испытай удачу:")
    await callback.message.edit_text(text, reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_") & ~F.data.contains("mine"))
async def cb_game(callback: types.CallbackQuery, state: FSMContext):
    game = callback.data.replace("game_", "")
    names = {"coin": "🪙 МОНЕТКА", "dice": "🎲 КУБИК", "darts": "🎯 ДАРТС"}
    await state.update_data(game=game)
    text = f"<b>{names[game]}</b>\n\n💵 Введи сумму ставки (целое число):"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(GameStates.waiting_for_bet)

@dp.message(GameStates.waiting_for_bet)
async def process_bet(message: types.Message, state: FSMContext):
    try:
        bet = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число!")
        return
    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше нуля.")
        return
        
    bal, _ = get_user(message.from_user.id)
    if bal < bet:
        await message.answer(f"❌ Недостаточно монет! Баланс: {bal}")
        await state.clear()
        return

    data = await state.get_data()
    game = data['game']
    result_text = ""
    
    if game == "coin":
        if random.choice([True, False]):
            update_balance(message.from_user.id, bet)
            result_text = f"🪙 Выпал <b>ОРЕЛ</b>!\n🎉 Ты выиграл <b>{bet}</b> монет!"
        else:
            update_balance(message.from_user.id, -bet)
            result_text = f"🪙 Выпала <b>РЕШКА</b>.\n😢 Ты проиграл <b>{bet}</b> монет."
            
    elif game == "dice":
        user_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)
        result_text = f"🎲 Твой кубик: <b>{user_roll}</b>\n🤖 Кубик бота: <b>{bot_roll}</b>\n\n"
        if user_roll > bot_roll:
            update_balance(message.from_user.id, bet)
            result_text += f"🎉 Победа! +{bet} монет."
        elif user_roll < bot_roll:
            update_balance(message.from_user.id, -bet)
            result_text += f"😢 Поражение. -{bet} монет."
        else:
            result_text += "🤝 Ничья. Ставка возвращена."
            
    elif game == "darts":
        if random.random() < 0.4:
            win_amount = int(bet * 2.5)
            update_balance(message.from_user.id, win_amount)
            result_text = f"🎯 <b>В ЯБЛОЧКО!</b> Коэффициент x2.5\n🎉 Ты выиграл <b>{win_amount}</b> монет!"
        else:
            update_balance(message.from_user.id, -bet)
            result_text = f"🎯 <b>МИМО!</b>\n😢 Ты проиграл <b>{bet}</b> монет."

    new_bal, _ = get_user(message.from_user.id)
    await message.answer(f"{result_text}\n\n💰 Баланс: <b>{new_bal}</b>", reply_markup=casino_menu(), parse_mode="HTML")
    await state.clear()

# --- Минное поле ---
@dp.callback_query(F.data == "game_mine")
async def cb_mine_start(callback: types.CallbackQuery, state: FSMContext):
    text = ("╔══════════════════╗\n"
            "   💣 <b>МИННОЕ ПОЛЕ</b>\n"
            "╚══════════════════╝\n\n"
            "Правила: на поле 5 ячеек, в одной спрятана мина.\n"
            "Если откроешь безопасную — забираешь x1.8 от ставки.\n\n"
            "💵 Введи сумму ставки:")
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(GameStates.minefield_bet)

@dp.message(GameStates.minefield_bet)
async def mine_bet(message: types.Message, state: FSMContext):
    try:
        bet = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число!")
        return
    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше нуля.")
        return
        
    bal, _ = get_user(message.from_user.id)
    if bal < bet:
        await message.answer(f"❌ Недостаточно монет! Баланс: {bal}")
        await state.clear()
        return

    # Списываем ставку сразу
    update_balance(message.from_user.id, -bet)
    
    # Генерируем мину (0-4)
    mine_index = random.randint(0, 4)
    await state.update_data(bet=bet, mine_index=mine_index)
    
    builder = InlineKeyboardBuilder()
    for i in range(5):
        builder.add(InlineKeyboardButton(text="❓", callback_data=f"mine_click_{i}"))
    builder.adjust(5)
    
    text = (f"💣 <b>МИННОЕ ПОЛЕ</b>\n\n"
            f"Ставка: <b>{bet}</b> монет\n"
            f"Выбирай ячейку. Одна из них смертельна!")
            
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(GameStates.minefield_play)

@dp.callback_query(F.data.startswith("mine_click_") & (F.data != "game_mine"))
async def mine_click(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get('bet')
    mine_index = data.get('mine_index')
    
    if bet is None:
        await callback.answer("Ошибка. Начни заново.", show_alert=True)
        await state.clear()
        return

    clicked_index = int(callback.data.split('_')[-1])
    
    if clicked_index == mine_index:
        # Попал на мину
        text = (f"💥 <b>БУМ!</b>\n\n"
                f"Ты наступил на мину и потерял <b>{bet}</b> монет.")
        await callback.message.edit_text(text, reply_markup=casino_menu(), parse_mode="HTML")
        await state.clear()
    else:
        # Выиграл
        win_amount = int(bet * 1.8)
        update_balance(callback.from_user.id, win_amount)
        text = (f"💎 <b>ПОВЕЗЛО!</b>\n\n"
                f"Ты нашел безопасную ячейку и выиграл <b>{win_amount}</b> монет!\n"
                f"(Ставка {bet} * 1.8)")
        await callback.message.edit_text(text, reply_markup=casino_menu(), parse_mode="HTML")
        await state.clear()

async def main():
    init_db()
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
