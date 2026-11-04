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
BOT_TOKEN = "9209660223:AAHTLeX9YvoJaeB_7Yl1WPj4OjG8A2qXSzI"
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

async def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID

# --- ИНСТРУКЦИЯ ---
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        f"📖 <b>ИНСТРУКЦИЯ ПО КОМАНДАМ</b>\n\n"
        f"<b>👤 Экономика:</b>\n"
        f"• <b>.карточка</b> — открыть карточку (раз в 10 минут, падает 5-10 монет/ирисок)\n"
        f"• <b>/profile</b> — твой профиль (уровень, баланс, прогресс-бар)\n"
        f"• <b>/top</b> — таблица лидеров по монетам\n\n"
        f"<b>🛡 Кланы:</b>\n"
        f"• <b>/clan_create [Название]</b> — создать клан\n"
        f"• <b>/clan_info [Название]</b> — информация о клане\n\n"
        f"<b>📊 Аналитика:</b>\n"
        f"• <b>/stats</b> — статистика чата (сообщения за 5ч и 24ч)\n\n"
        f"<b>🔨 Модерация (только для владельца):</b>\n"
        f"• <b>/mute</b> — замутить (ответом на сообщение)\n"
        f"• <b>/unmute</b> — размутить\n"
        f"• <b>/ban</b> — забанить\n"
        f"• <b>/kick</b> — кикнуть\n"
        f"• <b>/unban [ID]</b> — разбанить по ID\n"
        f"• <b>/close_chat</b> — закрыть чат\n"
        f"• <b>/open_chat</b> — открыть чат\n\n"
        f"<b>🤖 Управление ботами:</b>\n"
        f"• <b>/mute_bot</b> — заглушить одного бота (ответом)\n"
        f"• <b>/mute_all_bots</b> — заглушить всех ботов\n"
        f"• <b>/unmute_all_bots</b> — разглушить всех ботов\n"
    )
    await message.answer(text, parse_mode="HTML")

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

# --- ТОП ---
@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 5")
    top_players = c.fetchall(); conn.close()
    if not top_players: return await message.answer("Пока нет игроков в топе.")
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b> 🏆\n\n<blockquote>"
    for i, (username, first_name, coins) in enumerate(top_players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        if username: display_name = f"@{username}"
        elif first_name: display_name = first_name
        else: display_name = "Игрок"
        text += f"{medal} {display_name} — <b>{coins}</b> 🪙\n"
    text += "</blockquote>"
    await message.answer(text, parse_mode="HTML")

# --- КАРТОЧКА (5-10) ---
@dp.message(lambda message: message.text and message.text.lower() == ".карточка")
async def open_card(message: types.Message):
    user_id = message.from_user.id
    coins, iris, xp, level, last_card = get_user(user_id)
    now = time.time()
    if now - last_card < 600:
        left = 600 - (now - last_card)
        return await message.reply(f"⏳ Жди: {int(left // 60)}м {int(left % 60)}с.")
    
    msg = await message.reply("🎴 <b>Открываем карточку...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("🔄 <b>Крутим барабаны...</b>", parse_mode="HTML")
    await asyncio.sleep(1)
    await msg.edit_text("✨ <b>Почти готово...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    if random.choice([True, False]):
        amount = random.randint(5, 10)
        reward = f"🪙 Тебе выпало <b>{amount}</b> монет!"
        new_coins, new_iris = coins + amount, iris
    else:
        amount = random.randint(5, 10)
        reward = f"🍬 Тебе выпало <b>{amount}</b> ирисок!"
        new_coins, new_iris = coins, iris + amount

    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = ?, iris = ?, xp = xp + 5, last_card = ? WHERE user_id = ?", 
              (new_coins, new_iris, now, user_id))
    conn.commit(); conn.close()
    await msg.edit_text(f"🎉 <b>Карточка открыта!</b>\n\n<blockquote>{reward}</blockquote>", parse_mode="HTML")

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
    res = c.fetchone(); conn.close()
    if not res: return await message.reply("❌ Клан не найден.")
    owner, members = res
    members_list = members.split(",")
    await message.reply(f"🛡 <b>Клан {args[1]}</b>\n👑 Лидер: <code>{owner}</code>\n👥 Участников: {len(members_list)}", parse_mode="HTML")

# --- СТАТИСТИКА ---
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.chat.type == "private": return await message.reply("Только в группах.")
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
    text = (f"📊 <b>АНАЛИТИКА ЧАТА</b>\n\n<blockquote>🕒 За 5 часов: <b>{count_5h}</b> сообщений\n📅 За 24 часа: <b>{count_24h}</b> сообщений</blockquote>")
    await message.reply(text, parse_mode="HTML")

# --- МОДЕРАЦИЯ ---
@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 3600)
        await message.reply(f"🤐 Замучен на час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply(f"🔊 Размучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply(f"👢 Кикнут.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ Введи ID: /unban 123456789")
    try:
        await bot.unban_chat_member(message.chat.id, int(args[1]))
        await message.reply(f"🔓 Разбанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

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
    await message.reply("🤐 Все боты заглушены.")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🔊 Все боты разглушены.")

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            f"Напиши /help, чтобы увидеть все команды бота.")
    await message.answer(text, parse_mode="HTML")

# ==========================================
# ⚠️ СЧЕТЧИК ИДЕТ САМЫМ ПОСЛЕДНИМ!
# ==========================================
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
