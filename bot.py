import asyncio
import sqlite3
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions, ChatMemberAdministrator
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9156237384:AAHSnjmCMkgAgcHgcUwOT8KPX0vqlDDwptI"
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
                 balance INTEGER DEFAULT 1000, 
                 xp INTEGER DEFAULT 0,
                 level INTEGER DEFAULT 1,
                 messages INTEGER DEFAULT 0,
                 warns INTEGER DEFAULT 0)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT balance, xp, level, messages, warns FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (1000, 0, 1, 0, 0)
    conn.close(); return res

def update_user_activity(user_id, username):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, xp = xp + 10, username = ?", (user_id, username, username))
    
    c.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
    xp, level = c.fetchone()
    needed_xp = level * 5000
    
    if xp >= needed_xp:
        c.execute("UPDATE users SET level = level + 1, xp = xp - ? WHERE user_id = ?", (needed_xp, user_id))
        conn.commit(); conn.close()
        return True
    conn.commit(); conn.close()
    return False

async def is_chat_admin(message: types.Message) -> bool:
    if message.chat.type == "private": return message.from_user.id == ADMIN_ID
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, ChatMemberAdministrator) or member.status == "creator"
    except: return False

# --- СЧЕТЧИК ---
@dp.message()
async def count_messages(message: types.Message):
    if message.chat.type == "private" or not message.text or message.text.startswith('/'): return
    if message.from_user.is_bot: return
    
    leveled_up = update_user_activity(message.from_user.id, message.from_user.username or message.from_user.first_name)
    if leveled_up:
        user = get_user(message.from_user.id)
        await message.reply(f"🎉 <b>Поздравляю, {message.from_user.first_name}!</b>\nТы достиг <b>{user[2]}</b> уровня!", parse_mode="HTML")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"Я бот-модератор этого чата.\n"
            f"/profile — профиль\n"
            f"/top — топ игроков\n\n"
            f"Админы: /ban, /mute, /warn.")
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    bal, xp, level, msgs, warns = get_user(target.id)
    
    needed_xp = level * 5000
    progress = min(int((xp / needed_xp) * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    
    text = (f"👤 <b>ПРОФИЛЬ {target.first_name}</b>\n\n"
            f"🆔 <code>{target.id}</code>\n"
            f"📈 Уровень: <b>{level}</b>\n"
            f"✨ Опыт: <b>{xp}</b> / {needed_xp}\n"
            f"[{bar}]\n"
            f"💬 Сообщений: <b>{msgs}</b>\n"
            f"💰 Баланс: <b>{bal}</b>\n"
            f"⚠️ Варны: <b>{warns}/3</b>")
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>Топ игроков:</b>\n\n"
    for i, (name, bal) in enumerate(top, 1): text += f"{i}. {name or 'Аноним'} — {bal}\n"
    await message.answer(text, parse_mode="HTML")

# --- МОДЕРАЦИЯ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not await is_chat_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try: await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id); await message.reply(f"🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not await is_chat_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
        await message.reply(f"🤐 Замучен на час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not await is_chat_admin(message): return
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (user_id,))
    c.execute("SELECT warns FROM users WHERE user_id = ?", (user_id,))
    warns = c.fetchone()[0]
    conn.commit(); conn.close()
    await message.reply(f"⚠️ Варн {warns}/3.")
    if warns >= 3:
        try: await bot.ban_chat_member(message.chat.id, user_id); await message.reply("🔨 Забанен за 3 варна.")
        except: pass

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    print("Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
