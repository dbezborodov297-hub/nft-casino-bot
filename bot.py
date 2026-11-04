import asyncio
import sqlite3
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- ТОКЕН ---
BOT_TOKEN = "9156237384:AAE2mOmIuRRbIZ0bGxr0f50Zewhfb8SxFAU"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ФЛАСК ДЛЯ RENDER (чтобы не ругался на порты) ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- БАЗА ---
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

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_balance(message.from_user.id)
    await message.answer(f"👋 Привет, {message.from_user.first_name}!\nБот работает.\n\nНапиши /profile, чтобы проверить профиль.")

@dp.message(Command("profile"))
async def profile(message: types.Message):
    bal = get_balance(message.from_user.id)
    text = (f"👤 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"💰 Баланс: <b>{bal}</b> монет.")
    await message.answer(text, parse_mode="HTML")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    print("Тестовый бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
