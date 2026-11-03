import asyncio
import sqlite3
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9156237384:AAH2amnFF_edJXhXoY3GNmrlG_N9bHRzhFE" # Твой токен
ADMIN_ID = 8907438590 # Поставь свой ID

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- БД ---
def init_db():
    conn = sqlite3.connect('test.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 1000)''')
    conn.commit(); conn.close()

def get_balance(user_id):
    conn = sqlite3.connect('test.db'); c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (1000,)
    conn.close(); return res[0]

# --- МЕНЮ ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return builder.as_markup()

# --- ХЭНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_balance(message.from_user.id)
    text = f"🌟 <b>Привет, {message.from_user.first_name}!</b>\n\nБот работает. Нажми на кнопку ниже, чтобы посмотреть профиль."
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    bal = get_balance(callback.from_user.id)
    text = f"👤 <b>Профиль</b>\n\n🆔 ID: <code>{callback.from_user.id}</code>\n💰 Баланс: <b>{bal}</b> монет."
    await callback.message.edit_text(text, parse_mode="HTML")

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    # Жесткий сброс вебхука при запуске
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
