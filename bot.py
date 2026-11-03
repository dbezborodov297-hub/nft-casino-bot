import asyncio
import sqlite3
import time
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ChatPermissions, ChatMemberAdministrator
from datetime import datetime, timedelta

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9156237384:AAEb_VEzPIwnG4MEi0rmLSJQWzPaUAOx43c" 
ADMIN_ID = 8907438590 # ОБЯЗАТЕЛЬНО ПОСТАВЬ СВОЙ ID (узнать у @userinfobot)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

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

# Проверка: админ ли тот, кто пишет (в чате или в ЛС)
async def is_admin(message: types.Message) -> bool:
    if message.chat.type == "private": 
        return message.from_user.id == ADMIN_ID
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, ChatMemberAdministrator) or member.status == "creator"
    except: return False

# --- АНТИСПАМ И СЧЕТЧИК ---
@dp.message()
async def filter_messages(message: types.Message):
    if message.chat.type == "private" or not message.text or message.text.startswith('/'): return
    if message.from_user.is_bot: return

    user_id = message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    now = time.time()
    
    # Антиспам
    c.execute("SELECT last_msg, count FROM antispam WHERE user_id = ?", (user_id,))
    spam_res = c.fetchone()
    if spam_res:
        last_msg, count = spam_res
        if now - last_msg < 3:
            count += 1
            if count >= 5:
                try:
                    await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(minutes=10))
                    await message.reply(f"🤐 {message.from_user.first_name} замучен на 10 минут за флуд.")
                except: pass
                count = 0
        else: count = 1
        c.execute("UPDATE antispam SET last_msg = ?, count = ? WHERE user_id = ?", (now, count, user_id))
    else:
        c.execute("INSERT INTO antispam (user_id, last_msg, count) VALUES (?, ?, 1)", (user_id, now))
    
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, balance = balance + 1, username = ?", (user_id, message.from_user.username, message.from_user.username))
    conn.commit(); conn.close()

# --- КОМАНДЫ МОДЕРАЦИИ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ У тебя нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 {message.reply_to_message.from_user.first_name} забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ У тебя нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
        await message.reply(f"🤐 {message.reply_to_message.from_user.first_name} замучен на час.")
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
    await message.reply(f"⚠️ Варн {warns}/3 для {message.reply_to_message.from_user.first_name}.")
    if warns >= 3:
        try: await bot.ban_chat_member(message.chat.id, user_id); await message.reply("🔨 Забанен за 3 варна.")
        except: pass

# --- ПРОФИЛЬ И ЭКОНОМИКА ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    bal, msgs, warns, _ = get_user(target.id)
    
    text = (f"<b>📋 АНКЕТА ИГРОКА</b>\n"
            f"<blockquote>"
            f"🆔 <b>ID:</b> <code>{target.id}</code>\n"
            f"🏷 <b>Имя:</b> {target.first_name}\n"
            f"</blockquote>\n"
            f"<b>📊 Статистика:</b>\n"
            f"💬 Написано сообщений: <b>{msgs}</b>\n"
            f"💰 Ириски: <b>{bal}</b>\n"
            f"⚠️ Варны: <b>{warns}/3</b>")
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("bonus"))
async def bonus(message: types.Message):
    user_id = message.from_user.id
    bal, msgs, warns, last_bonus = get_user(user_id)
    now = time.time()
    
    if now - last_bonus < 86400: # 24 часа
        left = 86400 - (now - last_bonus)
        hours = left // 3600
        mins = (left % 3600) // 60
        return await message.reply(f"⏳ Бонус уже получен! Жди: {int(hours)}ч {int(mins)}м.")
        
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + 50, last_bonus = ? WHERE user_id = ?", (now, user_id))
    conn.commit(); conn.close()
    await message.reply("🎁 Ты получил ежедневный бонус: +50 ирисок!")

@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>Топ богачей:</b>\n\n"
    for i, (name, bal) in enumerate(top, 1):
        text += f"{i}. {name or 'Аноним'} — {bal} ирисок\n"
    await message.reply(text, parse_mode="HTML")

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    if message.chat.type == "private":
        await message.answer("👋 Привет! Я бот-модератор.\nДобавь меня в группу и сделай админом, чтобы я следил за порядком.")
    else:
        await message.answer("👋 Бот на связи! Я слежу за порядком. Пиши /profile, чтобы посмотреть анкету.")

@dp.message(F.new_chat_members)
async def welcome(message: types.Message):
    for member in message.new_chat_members:
        await message.answer(f"👋 Добро пожаловать, {member.first_name}!\nПрочитай правила чата.")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
