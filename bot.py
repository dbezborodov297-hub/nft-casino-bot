import asyncio
import random
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9020652959:AAGEHtKFJxpIxNzgMyxYvin3jhTnMt8lHJg"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Магазин NFT (только твои 2 предмета) ---
SHOP_ITEMS = {
    "🚀 Ракета": 50,
    "🗽 Статуя Свободы": 1200
}

# --- FSM для ставок ---
class GameStates(StatesGroup):
    waiting_for_bet = State()

# --- База данных ---
def init_db():
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                      (user_id INTEGER PRIMARY KEY, balance INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventory
                      (user_id INTEGER, item_name TEXT)''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 1000))
        conn.commit()
        balance = 1000
    else:
        balance = result[0]
    conn.close()
    return balance

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = cursor.fetchall()
    conn.close()
    if not items:
        return "Твой инвентарь пуст."
    res = "Твои NFT:\n"
    for item in items:
        res += f"• {item[0]}\n"
    return res

def buy_item(user_id, item_name, price):
    bal = get_balance(user_id)
    if bal < price:
        return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit()
    conn.close()
    return True

# --- Клавиатуры ---
def main_menu():
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🎰 Казино")],
            [types.KeyboardButton(text="🛒 Магазин NFT"), types.KeyboardButton(text="🎒 Инвентарь")],
            [types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🎁 Бонус")]
        ],
        resize_keyboard=True
    )
    return keyboard

def casino_menu():
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Своя ставка 🎲")],
            [types.KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

# --- Хэндлеры ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_balance(message.from_user.id)
    await message.answer(f"Привет, {message.from_user.first_name}!\nУ тебя на счету 1000 монет. Вперед за NFT!", reply_markup=main_menu())

@dp.message(F.text == "💰 Баланс")
async def balance(message: types.Message):
    bal = get_balance(message.from_user.id)
    await message.answer(f"Твой баланс: {bal} монет")

@dp.message(F.text == "🎁 Бонус")
async def bonus(message: types.Message):
    update_balance(message.from_user.id, 100)
    await message.answer("Ты получил 100 бонусных монет!")

@dp.message(F.text == "🎒 Инвентарь")
async def inventory(message: types.Message):
    items = get_inventory(message.from_user.id)
    await message.answer(items)

@dp.message(F.text == "🛒 Магазин NFT")
async def shop(message: types.Message):
    text = "Добро пожаловать в магазин NFT!\nВыбери, что купить:\n\n"
    keyboard = []
    for name, price in SHOP_ITEMS.items():
        text += f"{name} — {price} монет\n"
        keyboard.append([types.KeyboardButton(text=f"Купить {name}")])
    keyboard.append([types.KeyboardButton(text="⬅️ Назад")])
    
    markup = types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    await message.answer(text, reply_markup=markup)

@dp.message(F.text.startswith("Купить "))
async def buy_handler(message: types.Message):
    item = message.text.replace("Купить ", "")
    if item in SHOP_ITEMS:
        price = SHOP_ITEMS[item]
        if buy_item(message.from_user.id, item, price):
            await message.answer(f"Успешно куплено: {item} за {price} монет!")
        else:
            await message.answer("Недостаточно монет для покупки!")
    else:
        await message.answer("Такого товара нет.")

@dp.message(F.text == "⬅️ Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu())

@dp.message(F.text == "🎰 Казино")
async def casino(message: types.Message):
    await message.answer("Добро пожаловать в казино! Нажми кнопку ниже, чтобы ввести ставку.", reply_markup=casino_menu())

# --- Логика игры (Монетка) ---
@dp.message(F.text == "Своя ставка 🎲")
async def ask_bet(message: types.Message, state: FSMContext):
    await message.answer("Введи сумму ставки (целое число):")
    await state.set_state(GameStates.waiting_for_bet)

@dp.message(GameStates.waiting_for_bet)
async def process_bet(message: types.Message, state: FSMContext):
    try:
        bet = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введи целое число!")
        return

    if bet <= 0:
        await message.answer("Ставка должна быть больше нуля.")
        return

    user_id = message.from_user.id
    bal = get_balance(user_id)

    if bal < bet:
        await message.answer(f"Недостаточно монет! Твой баланс: {bal}")
        await state.clear()
        return

    # Бросок монетки
    result = random.choice(["Орел 🦅", "Решка 🪙"])
    win = random.choice([True, False])

    if win:
        update_balance(user_id, bet)
        await message.answer(f"Выпало: {result}\nТы выиграл {bet} монет! 🎉")
    else:
        update_balance(user_id, -bet)
        await message.answer(f"Выпало: {result}\nТы проиграл {bet} монет. 😢")

    new_bal = get_balance(user_id)
    await message.answer(f"Твой новый баланс: {new_bal}", reply_markup=casino_menu())
    await state.clear()

async def main():
    init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
