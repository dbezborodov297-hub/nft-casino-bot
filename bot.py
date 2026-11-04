import asyncio
import random
import sqlite3
import os
import threading
import time
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- ТОКЕН ---
BOT_TOKEN = "9253824362:AAHXX7SNI9T3cfvqvUsbTqOyXIojHwSNbS0"
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ФЛАСК ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- БАЗА ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT,
                 coins INTEGER DEFAULT 0, 
                 iris INTEGER DEFAULT 0,
                 xp INTEGER DEFAULT 0,
                 level INTEGER DEFAULT 1,
                 last_card REAL DEFAULT 0)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, iris, xp, level, last_card FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (0, 0, 0, 1, 0)
    conn.close(); return res

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"🎴 Каждые 10 минут ты можешь открывать карточку командой <b>.карточка</b> и получать монеты или ириски!\n\n"
            f"👤 /profile — посмотреть профиль")
    await message.answer(text, parse_mode="HTML")

# --- .КАРТОЧКА ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card = get_user(user_id)
    now = time.time()
    
    if now - last_card < 600:
        left = 600 - (now - last_card)
        mins = int(left // 60)
        secs = int(left % 60)
        return await message.reply(f"⏳ Ты уже открывал карточку! Жди: {mins}м {secs}с.")
    
    if random.choice([True, False]):
        amount = random.randint(1, 15)
        reward = f"🪙 Тебе выпало <b>{amount}</b> монет!"
        new_coins, new_iris = coins + amount, iris
    else:
        amount = random.randint(1, 5)
        reward = f"🍬 Тебе выпало <b>{amount}</b> ирисок!"
        new_coins, new_iris = coins, iris + amount

    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = ?, iris = ?, xp = xp + 5, last_card = ? WHERE user_id = ?", 
              (new_coins, new_iris, now, user_id))
    conn.commit(); conn.close()
    
    await message.reply(f"🎴 <b>Открываем карточку...</b>\n\n{reward}", parse_mode="HTML")

# --- ПРОФИЛЬ ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    coins, iris, xp, level, last_card = get_user(target.id)
    
    needed_xp = level * 5000
    progress = min(int((xp / needed_xp) * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    
    text = (f"👤 <b>ПРОФИЛЬ {target.first_name}</b>\n\n"
            f"🆔 <code>{target.id}</code>\n"
            f"📈 Уровень: <b>{level}</b>\n"
            f"✨ Опыт: <b>{xp}</b> / {needed_xp}\n"
            f"[{bar}]\n\n"
            f"🪙 Монеты: <b>{coins}</b>\n"
            f"🍬 Ириски: <b>{iris}</b>")
    await message.answer(text, parse_mode="HTML")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    print("Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
