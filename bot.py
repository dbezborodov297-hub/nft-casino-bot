import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9253824362:AAH8CjRLaM74vR9rgv2ElDLGffj4iW-b-yQ" 
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
                 first_name TEXT,
                 coins INTEGER DEFAULT 0, 
                 iris INTEGER DEFAULT 0,
                 xp INTEGER DEFAULT 0,
                 level INTEGER DEFAULT 1,
                 last_card REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_stats (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 chat_id INTEGER,
                 user_id INTEGER,
                 timestamp REAL)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins, iris, xp, level, last_card FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (0, 0, 0, 1, 0)
    conn.close(); return res

def update_user_info(user_id, username, first_name):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET username = ?, first_name = ?", 
              (user_id, username, first_name, username, first_name))
    conn.commit(); conn.close()

# --- СЧЕТЧИК ---
@dp.message(lambda message: message.text is not None)
async def track_stats(message: types.Message):
    if message.chat.type == "private" or message.text.startswith('/'): return
    if message.from_user.is_bot: return
    
    update_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO chat_stats (chat_id, user_id, timestamp) VALUES (?, ?, ?)", 
              (message.chat.id, message.from_user.id, time.time()))
    conn.commit(); conn.close()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"🎴 Карточка: <b>.карточка</b>\n"
            f"👤 Профиль: /profile\n"
            f"🏆 Топ: /top\n"
            f"📊 Статистика: /stats")
    await message.answer(text, parse_mode="HTML")

# --- КАРТОЧКА ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card = get_user(user_id)
    now = time.time()
    
    if now - last_card < 600:
        left = 600 - (now - last_card)
        mins = int(left // 60)
        secs = int(left % 60)
        return await message.reply(f"⏳ Жди: {mins}м {secs}с.")
    
    msg = await message.reply("🎴 <b>Открываем карточку...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🔄 <b>Крутим барабаны...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("✨ <b>Почти готово...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

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
    
    await msg.edit_text(f"🎉 <b>Карточка открыта!</b>\n\n<blockquote>{reward}</blockquote>", parse_mode="HTML")

# --- ТОП ---
@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 5")
    top_players = c.fetchall(); conn.close()
    
    if not top_players:
        return await message.answer("Пока нет игроков в топе.")
    
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b> 🏆\n\n<blockquote>"
    for i, (username, first_name, coins) in enumerate(top_players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        if username: display_name = f"@{username}"
        elif first_name: display_name = first_name
        else: display_name = "Игрок"
        text += f"{medal} {display_name} — <b>{coins}</b> 🪙\n"
    text += "</blockquote>"
    await message.answer(text, parse_mode="HTML")

# --- СТАТИСТИКА ---
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.chat.type == "private":
        return await message.reply("Статистика доступна только в группах.")
    
    chat_id = message.chat.id
    now = time.time()
    five_hours_ago = now - (5 * 3600)
    one_day_ago = now - (24 * 3600)
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, five_hours_ago))
    count_5h = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_stats WHERE chat_id = ? AND timestamp > ?", (chat_id, one_day_ago))
    count_24h = c.fetchone()[0]
    conn.close()
    
    text = (f"📊 <b>СТАТИСТИКА ЧАТА</b>\n\n"
            f"<blockquote>"
            f"🕒 За 5 часов: <b>{count_5h}</b> сообщений\n"
            f"📅 За 24 часа: <b>{count_24h}</b> сообщений"
            f"</blockquote>")
    await message.reply(text, parse_mode="HTML")

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
    
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
