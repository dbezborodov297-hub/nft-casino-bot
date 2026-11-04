import asyncio
import sqlite3
import time
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ChatPermissions, ChatMemberAdministrator
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9156237384:AAGyTDnXFsS6byW9Jj2P1X8GIFjQ4FxperA" 
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ЗАГЛУШКА ДЛЯ RENDER (ЧТОБЫ НЕ БЫЛО ОШИБКИ ПОРТОВ) ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- БД ---
def init_db():
    conn = sqlite3.connect('mod.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT, 
                 balance INTEGER DEFAULT 100, 
                 messages INTEGER DEFAULT 0,
                 warns INTEGER DEFAULT 0,
                 last_bonus REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS antispam (user_id INTEGER PRIMARY KEY, last_msg REAL, count INTEGER)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT balance, messages, warns, last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (100, 0, 0, 0)
    conn.close(); return res

async def is_admin(message: types.Message) -> bool:
    if message.chat.type == "private": return message.from_user.id == ADMIN_ID
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, ChatMemberAdministrator) or member.status == "creator"
    except: return False

# --- АНТИСПАМ ---
@dp.message()
async def filter_messages(message: types.Message):
    if message.chat.type == "private" or not message.text or message.text.startswith('/'): return
    if message.from_user.is_bot: return
    user_id = message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    now = time.time()
    
    c.execute("SELECT last_msg, count FROM antispam WHERE user_id = ?", (user_id,))
    spam_res = c.fetchone()
    if spam_res:
        last_msg, count = spam_res
        if now - last_msg < 3:
            count += 1
            if count >= 5:
                try:
                    await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(minutes=10))
                    await message.reply(f"🤐 {message.from_user.first_name} замучен за флуд.")
                except: pass
                count = 0
        else: count = 1
        c.execute("UPDATE antispam SET last_msg = ?, count = ? WHERE user_id = ?", (now, count, user_id))
    else: c.execute("INSERT INTO antispam (user_id, last_msg, count) VALUES (?, ?, 1)", (user_id, now))
    
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, balance = balance + 1, username = ?", (user_id, message.from_user.username, message.from_user.username))
    conn.commit(); conn.close()

# --- МОДЕРАЦИЯ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try: await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id); await message.reply("🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
        await message.reply("🤐 Замучен на час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not await is_admin(message): return
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (user_id,))
    c.execute("SELECT warns FROM users WHERE user_id = ?", (user_id,))
    warns = c.fetchone()[0]
    conn.commit(); conn.close()
    await message.reply(f"⚠️ Варн {warns}/3.")
    if warns >= 3:
        try: await bot.ban_chat_member(message.chat.id, user_id); await message.reply("🔨 Забанен за 3 варна.")
        except: pass

# --- ПРОФИЛЬ И БОНУС ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    bal, msgs, warns, _ = get_user(target.id)
    text = (f"📋 <b>АНКЕТА</b>\n<blockquote>🆔 {target.id}\n🏷 {target.first_name}</blockquote>\n"
            f"💬 Сообщений: <b>{msgs}</b>\n💰 Ириски: <b>{bal}</b>\n⚠️ Варны: <b>{warns}/3</b>")
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("bonus"))
async def bonus(message: types.Message):
    user_id = message.from_user.id
    bal, msgs, warns, last_bonus = get_user(user_id)
    now = time.time()
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        return await message.reply(f"⏳ Жди: {int(left//3600)}ч {int((left%3600)//60)}м.")
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + 50, last_bonus = ? WHERE user_id = ?", (now, user_id))
    conn.commit(); conn.close()
    await message.reply("🎁 +50 ирисок!")

@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>Топ богачей:</b>\n\n"
    for i, (name, bal) in enumerate(top, 1): text += f"{i}. {name or 'Аноним'} — {bal}\n"
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("start"))
async def start(message: types.Message):
    if message.chat.type == "private": await message.answer("👋 Привет! Добавь меня в группу и сделай админом.")
    else: await message.answer("👋 Бот на связи!")

@dp.message(F.new_chat_members)
async def welcome(message: types.Message):
    for member in message.new_chat_members: await message.answer(f"👋 Добро пожаловать, {member.first_name}!")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    print("Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
