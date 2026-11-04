import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9209660223:AAG94hAlU6rv76KHxWzoB1jgU6e76P4zfHw"
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ФЛАСК ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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
    c.execute('''CREATE TABLE IF NOT EXISTS muted_bots (
                 chat_id INTEGER, 
                 bot_id INTEGER, 
                 PRIMARY KEY (chat_id, bot_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS clans (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT UNIQUE,
                 owner_id INTEGER,
                 members TEXT)''')
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
    conn = sqlite3.connect('bot.db')
    conn.execute(
        "INSERT INTO users (user_id, username, first_name) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
        (user_id, username, first_name))
    conn.commit(); conn.close()

# --- ПРОВЕРКА (ТОЛЬКО ДЛЯ ТЕБЯ) ---
async def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID

# --- ГЛУШИЛКА БОТОВ ---
@dp.message(lambda message: message.from_user and message.from_user.is_bot)
async def check_muted_bots(message: types.Message):
    if message.chat.type == "private": return
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT 1 FROM muted_bots WHERE chat_id = ? AND (bot_id = ? OR bot_id = 0)", (message.chat.id, message.from_user.id))
    if c.fetchone():
        try: await message.delete()
        except: pass
    conn.close()

@dp.message(Command("mute_bot"))
async def mute_bot(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message or not message.reply_to_message.from_user.is_bot:
        return await message.reply("❌ Ответь на сообщение бота.")
    target = message.reply_to_message.from_user
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, ?)", (message.chat.id, target.id))
    conn.commit(); conn.close()
    await message.reply(f"🤐 Бот {target.first_name} заглушен.")

@dp.message(Command("mute_all_bots"))
async def mute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO muted_bots (chat_id, bot_id) VALUES (?, 0)", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🤐 Все боты в этом чате заглушены.")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🔊 Все боты разглушены.")

# --- МУТЫ И БАНЫ ДЛЯ ЛЮДЕЙ ---
@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение нарушителя.")
    try:
        await bot.restrict_chat_member(
            message.chat.id, 
            message.reply_to_message.from_user.id, 
            ChatPermissions(can_send_messages=False),
            until_date=int(time.time()) + 3600
        )
        await message.reply(f"🤐 {message.reply_to_message.from_user.first_name} замучен на 1 час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(
            message.chat.id, 
            message.reply_to_message.from_user.id, 
            ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        )
        await message.reply(f"🔊 {message.reply_to_message.from_user.first_name} размучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение нарушителя.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 {message.reply_to_message.from_user.first_name} забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение нарушителя.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"👢 {message.reply_to_message.from_user.first_name} кикнут.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ Введи ID: /unban 123456789")
    try:
        await bot.unban_chat_member(message.chat.id, int(args[1]))
        await message.reply(f"🔓 Пользователь {args[1]} разбанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

# --- УПРАВЛЕНИЕ ЧАТОМ ---
@dp.message(Command("close_chat"))
async def close_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
        await message.reply("🔒 Чат закрыт.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("open_chat"))
async def open_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply("🔓 Чат открыт.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

# --- КЛАНЫ ---
@dp.message(Command("clan_create"))
async def clan_create(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("Используй: /clan_create [Название]")
    
    clan_name = args[1]
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    try:
        c.execute("INSERT INTO clans (name, owner_id, members) VALUES (?, ?, ?)", (clan_name, message.from_user.id, str(message.from_user.id)))
        conn.commit()
        await message.reply(f"🛡 Клан <b>{clan_name}</b> создан! Ты лидер.", parse_mode="HTML")
    except sqlite3.IntegrityError:
        await message.reply("❌ Клан с таким названием уже существует.")
    conn.close()

@dp.message(Command("clan_info"))
async def clan_info(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return await message.reply("Используй: /clan_info [Название]")
    
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT owner_id, members FROM clans WHERE name = ?", (args[1],))
    res = c.fetchone()
    conn.close()
    
    if not res: return await message.reply("❌ Клан не найден.")
    owner, members = res
    members_list = members.split(",")
    await message.reply(f"🛡 <b>Клан {args[1]}</b>\n👑 Лидер: <code>{owner}</code>\n👥 Участников: {len(members_list)}", parse_mode="HTML")

# --- ДУЭЛИ ---
@dp.message(Command("duel"))
async def duel_start(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение соперника.")
    opponent = message.reply_to_message.from_user
    if opponent.id == message.from_user.id: return await message.reply("❌ Нельзя играть с собой.")
    
    bet = 100 
    coins, _, _, _, _ = get_user(message.from_user.id)
    if coins < bet: return await message.reply("❌ У тебя недостаточно монет для ставки 100.")
    
    await message.reply(f"⚔️ {message.from_user.first_name} вызывает {opponent.first_name} в крестики-нолики на {bet} монет!\n\n{opponent.first_name}, напиши /accept_duel чтобы принять.")

@dp.message(Command("accept_duel"))
async def duel_accept(message: types.Message):
    await message.reply("✅ Дуэль принята! Игра начинается.\nДоска:\n1 2 3\n4 5 6\n7 8 9\n\nХоди цифрой от 1 до 9.")

# --- СТАРТ И ПРОФИЛЬ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"🎴 .карточка\n"
            f"👤 /profile\n"
            f"🏆 /top\n"
            f"📊 /stats\n"
            f"🛡 /clan_create [Название]\n"
            f"⚔️ /duel\n\n"
            f"<b>Модерация (только для тебя):</b>\n"
            f"/mute, /unmute, /ban, /kick, /unban\n"
            f"/mute_bot, /mute_all_bots, /unmute_all_bots\n"
            f"/close_chat, /open_chat")
    await message.answer(text, parse_mode="HTML")

# --- СЧЕТЧИК (В КОНЦЕ) ---
@dp.message(lambda m: m.text and not m.text.startswith("/"))
async def track_stats(message: types.Message):
    if message.chat.type == "private" or message.from_user.is_bot: return
    update_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)

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
