import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions, ChatMemberAdministrator, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9253824362:AAHBagHx7GURwpe371KLaj2QxMKNURDTjtk"
ADMIN_ID = 8907438590 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Хранилище активных дуэлей
active_duels = {}

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
    if message.from_user.id == ADMIN_ID: return True
    if message.chat.type == "private": return False
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, ChatMemberAdministrator) or member.status == "creator"
    except: return False

# --- ГЛУШИЛКА БОТОВ ---
@dp.message(lambda message: message.from_user and message.from_user.is_bot)
async def check_muted_bots(message: types.Message):
    if message.chat.type == "private": return
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    # Проверка на конкретного бота ИЛИ на всех ботов (bot_id = 0)
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
    await message.reply("🤐 Все боты в этом чате заглушены (кроме меня!).")

@dp.message(Command("unmute_all_bots"))
async def unmute_all_bots(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("DELETE FROM muted_bots WHERE chat_id = ? AND bot_id = 0", (message.chat.id,))
    conn.commit(); conn.close()
    await message.reply("🔊 Все боты разглушены.")

# --- УПРАВЛЕНИЕ ЧАТОМ ---
@dp.message(Command("close_chat"))
async def close_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
        await message.reply("🔒 Чат закрыт. Никто не может писать.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("open_chat"))
async def open_chat(message: types.Message):
    if not await is_admin(message): return await message.reply("❌ Нет прав.")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await message.reply("🔓 Чат открыт. Можно писать.")
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
    
    await message.reply(f"⚔️ <b>Дуэль!</b>\n\n{message.from_user.first_name} вызывает {opponent.first_name} в крестики-нолики.\n\nВведи ставку (монеты):")
    await asyncio.sleep(1)
    bet = 100 
    coins, _, _ = get_user(message.from_user.id)
    if coins < bet: return await message.reply("❌ У тебя недостаточно монет для ставки.")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"duel_accept_{message.from_user.id}_{opponent.id}_{bet}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="duel_decline")
    )
    
    try:
        await bot.send_message(opponent.id, f"⚔️ {message.from_user.first_name} вызывает тебя на дуэль!\nСтавка: {bet} монет.", reply_markup=builder.as_markup())
        await message.reply("✅ Вызов отправлен в ЛС сопернику.")
    except:
        await message.reply("❌ Не удалось отправить в ЛС. Соперник должен сначала нажать /start у бота.")

@dp.callback_query(lambda c: c.data.startswith("duel_accept_"))
async def duel_accept(callback: types.CallbackQuery):
    _, _, p1, p2, bet = callback.data.split("_")
    p1, p2, bet = int(p1), int(p2), int(bet)
    
    board = "_________"
    active_duels[f"{p1}_{p2}"] = {"board": board, "p1": p1, "p2": p2, "turn": p1, "bet": bet}
    
    await callback.message.edit_text("✅ Дуэль принята! Игра началась в чате.")
    await bot.send_message(p1, f"⚔️ Дуэль началась! Твой ход (❌):\nИграй в чате.", reply_markup=create_board(p1, p2, board))

def create_board(p1, p2, board):
    builder = InlineKeyboardBuilder()
    for i in range(9):
        text = board[i] if board[i] != "_" else "⬜"
        builder.button(text=text, callback_data=f"duel_move_{p1}_{p2}_{i}")
    builder.adjust(3)
    return builder.as_markup()

@dp.callback_query(lambda c: c.data.startswith("duel_move_"))
async def duel_move(callback: types.CallbackQuery):
    _, _, p1, p2, idx = callback.data.split("_")
    p1, p2, idx = int(p1), int(p2), int(idx)
    key = f"{p1}_{p2}"
    
    if key not in active_duels: return await callback.answer("Игра окончена.")
    game = active_duels[key]
    
    if callback.from_user.id != game["turn"]: return await callback.answer("❌ Не твой ход!")
    if game["board"][idx] != "_": return await callback.answer("❌ Занято!")
    
    symbol = "❌" if callback.from_user.id == p1 else "⭕"
    new_board = list(game["board"])
    new_board[idx] = symbol
    game["board"] = "".join(new_board)
    game["turn"] = p2 if game["turn"] == p1 else p1
    
    win_lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    winner = None
    for a,b,c_i in win_lines:
        if game["board"][a] == game["board"][b] == game["board"][c_i] != "_":
            winner = game["board"][a]
            break
            
    if winner:
        winner_id = p1 if winner == "❌" else p2
        conn = sqlite3.connect('bot.db'); c = conn.cursor()
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (game["bet"], winner_id))
        c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (game["bet"], p1 if winner_id == p2 else p2))
        conn.commit(); conn.close()
        
        await callback.message.edit_text(f"🏆 Победа! {winner} выиграл {game['bet']} монет.")
        del active_duels[key]
    elif "_" not in game["board"]:
        await callback.message.edit_text("🤝 Ничья!")
        del active_duels[key]
    else:
        await callback.message.edit_reply_markup(reply_markup=create_board(p1, p2, game["board"]))
        await callback.answer("Ход сделан. Передай ход сопернику.")

@dp.callback_query(lambda c: c.data == "duel_decline")
async def duel_decline(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Дуэль отклонена.")

# --- СТАРТ И ПРОФИЛЬ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer("👋 Привет! Пиши /admin для админ-панели, /clan_create для клана.")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Стата", callback_data="admin_stats"))
    await message.answer("⚙️ Админка (тест).", reply_markup=builder.as_markup())

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
