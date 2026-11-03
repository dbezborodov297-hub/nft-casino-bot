import asyncio
import random
import sqlite3
import time
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions
from datetime import datetime, timedelta

BOT_TOKEN = "9156237384:AAHiR1wMTi_mgEgQcbxQMtiHMDE9KNHuW0M"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

BAD_WORDS = ["мат", "хуй", "бля", "пизда", "ебать"]

# --- БД ---
def init_db():
    conn = sqlite3.connect('mod.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT, 
                 balance INTEGER DEFAULT 100, 
                 xp INTEGER DEFAULT 0, 
                 level INTEGER DEFAULT 1, 
                 messages INTEGER DEFAULT 0, 
                 warns INTEGER DEFAULT 0,
                 marry_id INTEGER DEFAULT NULL)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT balance, xp, level, messages, warns, marry_id FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (100, 0, 1, 0, 0, None)
    conn.close(); return res

def is_admin(user_id):
    return user_id == ADMIN_ID

# --- АНТИСПАМ И ЭКОНОМИКА ---
@dp.message()
async def filter_messages(message: types.Message):
    if message.chat.type == "private" or not message.text or message.text.startswith('/'): return
    user_id = message.from_user.id

    if any(word in message.text.lower() for word in BAD_WORDS):
        try:
            await message.delete()
            await message.answer(f"🤬 {message.from_user.first_name}, не матерись!")
            return
        except: pass

    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, balance = balance + 2, xp = xp + 10, username = ?", (user_id, message.from_user.username, message.from_user.username))
    c.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
    xp, lvl = c.fetchone()
    if xp >= lvl * 100:
        c.execute("UPDATE users SET level = level + 1, xp = xp - ? WHERE user_id = ?", (lvl * 100, user_id))
        await message.reply(f"🎉 {message.from_user.first_name} достиг {lvl + 1} уровня!")
    conn.commit(); conn.close()

# --- МОДЕРАЦИЯ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not is_admin(message.from_user.id) or not message.reply_to_message: return
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message, command: CommandObject):
    if not is_admin(message.from_user.id) or not message.reply_to_message: return
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
        await message.reply("🤐 Замучен на час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not is_admin(message.from_user.id) or not message.reply_to_message: return
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (user_id,))
    c.execute("SELECT warns FROM users WHERE user_id = ?", (user_id,))
    warns = c.fetchone()[0]
    conn.commit(); conn.close()
    await message.reply(f"⚠️ Варн {warns}/3.")
    if warns >= 3:
        try: await bot.ban_chat_member(message.chat.id, user_id)
        except: pass

# --- БРАКИ ---
@dp.message(Command("marry"))
async def marry(message: types.Message):
    if not message.reply_to_message: return
    target_id = message.reply_to_message.from_user.id
    if target_id == message.from_user.id: return
    
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET marry_id = ? WHERE user_id = ?", (target_id, message.from_user.id))
    conn.commit(); conn.close()
    await message.reply(f"💍 {message.from_user.first_name} и {message.reply_to_message.from_user.first_name} теперь в браке!")

@dp.message(Command("divorce"))
async def divorce(message: types.Message):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET marry_id = NULL WHERE user_id = ?", (message.from_user.id,))
    conn.commit(); conn.close()
    await message.reply("💔 Ты развелся(ась).")

# --- РП-КОМАНДЫ ---
@dp.message(Command("hug"))
async def hug(message: types.Message):
    if message.reply_to_message:
        await message.reply(f"🫂 {message.from_user.first_name} обнял(а) {message.reply_to_message.from_user.first_name}!")

@dp.message(Command("kill"))
async def kill(message: types.Message):
    if message.reply_to_message:
        await message.reply(f"🔪 {message.from_user.first_name} убил(а) {message.reply_to_message.from_user.first_name}!")

# --- ПРОФИЛЬ ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    bal, xp, lvl, msgs, warns, marry = get_user(message.from_user.id)
    text = (f"👤 <b>Профиль {message.from_user.first_name}</b>\n\n"
            f"💰 Ириски: <b>{bal}</b>\n"
            f"📈 Уровень: <b>{lvl}</b> (XP: {xp}/{lvl*100})\n"
            f"💬 Сообщений: <b>{msgs}</b>\n"
            f"⚠️ Варны: <b>{warns}/3</b>\n"
            f"💍 В браке с: <b>{marry if marry else 'Никем'}</b>")
    await message.reply(text, parse_mode="HTML")

# --- ЗАГЛУШКА ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
