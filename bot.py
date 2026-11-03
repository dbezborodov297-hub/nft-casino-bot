import asyncio
import sqlite3
import time
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, ChatMemberAdministrator
from datetime import datetime, timedelta

BOT_TOKEN = "9156237384:AAF3R84YZYmKykRBjz6VyLWbuozcFBhDmWc"
# ADMIN_ID больше не нужен для проверки прав, но оставим для системных сообщений
ADMIN_ID = 8907438590

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
                 warns INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS antispam (user_id INTEGER PRIMARY KEY, last_msg REAL, count INTEGER)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT balance, messages, warns FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (100, 0, 0)
    conn.close(); return res

# --- ПРОВЕРКА ПРАВ В ГРУППЕ ---
async def is_chat_admin(message: types.Message) -> bool:
    """Проверяет, является ли автор сообщения админом в текущем чате."""
    if message.chat.type == "private":
        # В личке разрешаем только тебе (владельцу)
        return message.from_user.id == ADMIN_ID
        
    try:
        # Запрашиваем у Telegram инфу о юзере в этом чате
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, ChatMemberAdministrator) or member.status == "creator"
    except Exception:
        return False

# --- АНТИСПАМ И СЧЕТЧИК ---
@dp.message()
async def filter_messages(message: types.Message):
    if message.chat.type == "private" or not message.text or message.text.startswith('/'): return
    user_id = message.from_user.id
    if message.from_user.is_bot: return

    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    now = time.time()
    
    # Антиспам (Флуд)
    c.execute("SELECT last_msg, count FROM antispam WHERE user_id = ?", (user_id,))
    spam_res = c.fetchone()
    if spam_res:
        last_msg, count = spam_res
        if now - last_msg < 3:
            count += 1
            if count >= 5:
                try:
                    until = datetime.now() + timedelta(minutes=10)
                    await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False), until_date=until)
                    await message.reply(f"🤐 {message.from_user.first_name} замучен на 10 минут за флуд.")
                except: pass
                count = 0
        else:
            count = 1
        c.execute("UPDATE antispam SET last_msg = ?, count = ? WHERE user_id = ?", (now, count, user_id))
    else:
        c.execute("INSERT INTO antispam (user_id, last_msg, count) VALUES (?, ?, 1)", (user_id, now))
    
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, balance = balance + 1, username = ?", (user_id, message.from_user.username, message.from_user.username))
    conn.commit(); conn.close()

# --- КОМАНДЫ МОДЕРАЦИИ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not await is_chat_admin(message): 
        await message.reply("❌ У тебя нет прав администратора в этом чате.")
        return
    if not message.reply_to_message: 
        await message.reply("❌ Ответь на сообщение нарушителя."); return
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 {message.reply_to_message.from_user.first_name} забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("kick"))
async def kick(message: types.Message):
    if not await is_chat_admin(message): 
        await message.reply("❌ У тебя нет прав."); return
    if not message.reply_to_message: await message.reply("❌ Ответь на сообщение."); return
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"👢 {message.reply_to_message.from_user.first_name} кикнут.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message, command: CommandObject):
    if not await is_chat_admin(message): 
        await message.reply("❌ У тебя нет прав."); return
    if not message.reply_to_message: 
        await message.reply("❌ Ответь на сообщение того, кого хочешь замутить."); return
        
    time_str = command.args if command.args else "1h"
    try:
        if time_str.endswith('m'):
            mins = int(time_str[:-1]); until = datetime.now() + timedelta(minutes=mins); time_text = f"{mins} мин."
        elif time_str.endswith('h'):
            hours = int(time_str[:-1]); until = datetime.now() + timedelta(hours=hours); time_text = f"{hours} ч."
        elif time_str.endswith('d'):
            days = int(time_str[:-1]); until = datetime.now() + timedelta(days=days); time_text = f"{days} дн."
        else:
            until = datetime.now() + timedelta(hours=1); time_text = "1 час"
    except:
        until = datetime.now() + timedelta(hours=1); time_text = "1 час"
        
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=until)
        await message.reply(f"🤐 {message.reply_to_message.from_user.first_name} замучен на {time_text}.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not await is_chat_admin(message): return
    if not message.reply_to_message: await message.reply("❌ Ответь на сообщение."); return
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (user_id,))
    c.execute("SELECT warns FROM users WHERE user_id = ?", (user_id,))
    warns = c.fetchone()[0]
    conn.commit(); conn.close()
    await message.reply(f"⚠️ Варн {warns}/3 для {message.reply_to_message.from_user.first_name}.")
    if warns >= 3:
        try:
            await bot.ban_chat_member(message.chat.id, user_id)
            await message.reply("🔨 Забанен за 3 варна.")
        except: pass

@dp.message(Command("clear"))
async def clear(message: types.Message, command: CommandObject):
    if not await is_chat_admin(message): return
    count = int(command.args) if command.args and command.args.isdigit() else 10
    await message.delete()
    for i in range(count):
        try: await bot.delete_message(message.chat.id, message.message_id - i)
        except: pass

# --- ПРОФИЛЬ ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    bal, msgs, warns = get_user(target.id)
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

# --- ПРИВЕТСТВИЕ ---
@dp.message(F.new_chat_members)
async def welcome(message: types.Message):
    for member in message.new_chat_members:
        await message.answer(f"👋 Добро пожаловать, {member.first_name}!\nПрочитай правила чата.")

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
