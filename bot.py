import asyncio
import random
import sqlite3
import time
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9184406467:AAEDSYY0_lZa6xmCHTq__cBUsMBWKVi-nCA"
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
                 xp INTEGER DEFAULT 0,
                 level INTEGER DEFAULT 1,
                 messages INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS warns (user_id INTEGER, reason TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS antispam (user_id INTEGER PRIMARY KEY, last_msg REAL, count INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY AUTOINCREMENT, p1 INTEGER, p2 INTEGER, board TEXT, turn INTEGER)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT balance, xp, level, messages FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (100, 0, 1, 0)
    conn.close(); return res

def is_admin(user_id):
    return user_id == ADMIN_ID

# --- СЧЕТЧИК СООБЩЕНИЙ И АНТИСПАМ ---
@dp.message()
async def count_messages(message: types.Message):
    if message.text and not message.text.startswith('/'):
        user_id = message.from_user.id
        conn = sqlite3.connect('mod.db'); c = conn.cursor()
        now = time.time()
        
        # Антиспам (очень простой)
        c.execute("SELECT last_msg, count FROM antispam WHERE user_id = ?", (user_id,))
        spam_res = c.fetchone()
        if spam_res:
            last_msg, count = spam_res
            if now - last_msg < 2: # Если писал меньше 2 секунд назад
                count += 1
                if count >= 5:
                    try:
                        await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False))
                        await message.reply(f"🤐 {message.from_user.first_name} замучен за флуд!")
                        await asyncio.sleep(300) # 5 минут
                        await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=True))
                    except: pass
                    count = 0
            else:
                count = 1
            c.execute("UPDATE antispam SET last_msg = ?, count = ? WHERE user_id = ?", (now, count, user_id))
        else:
            c.execute("INSERT INTO antispam (user_id, last_msg, count) VALUES (?, ?, 1)", (user_id, now))
        
        # Начисление баланса и опыта
        c.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, balance = balance + 1, xp = xp + 5, username = ?", (user_id, message.from_user.username, message.from_user.username))
        c.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        xp, lvl = c.fetchone()
        if xp >= lvl * 100:
            c.execute("UPDATE users SET level = level + 1, xp = xp - ? WHERE user_id = ?", (lvl*100, user_id))
            await message.reply(f"🎉 {message.from_user.first_name} достиг {lvl+1} уровня!")
            
        conn.commit(); conn.close()

# --- ПРОФИЛЬ И ТОП ---
@dp.message(Command("profile"))
async def profile(message: types.Message):
    bal, xp, lvl, msgs = get_user(message.from_user.id)
    text = (f"👤 <b>Профиль {message.from_user.first_name}</b>\n\n"
            f"💰 Ириски: <b>{bal}</b>\n"
            f"📈 Уровень: <b>{lvl}</b> (XP: {xp}/{lvl*100})\n"
            f"💬 Сообщений: <b>{msgs}</b>")
    await message.reply(text, parse_mode="HTML")

@dp.message(Command("top"))
async def top(message: types.Message):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>Топ богачей:</b>\n\n"
    for i, (name, bal) in enumerate(top, 1):
        text += f"{i}. {name or 'Аноним'} — {bal} ирисок\n"
    await message.reply(text, parse_mode="HTML")

# --- МОДЕРАЦИЯ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    if not message.reply_to_message: await message.reply("Ответь на сообщение!"); return
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply("🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not is_admin(message.from_user.id): return
    if not message.reply_to_message: await message.reply("Ответь на сообщение!"); return
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False))
        await message.reply("🤐 Замучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not is_admin(message.from_user.id): return
    if not message.reply_to_message: await message.reply("Ответь на сообщение!"); return
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("INSERT INTO warns (user_id, reason) VALUES (?, ?)", (user_id, "Нарушение"))
    c.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.commit(); conn.close()
    await message.reply(f"⚠️ Варн {count}/3.")
    if count >= 3:
        try: await bot.ban_chat_member(message.chat.id, user_id); await message.reply("🔨 Забанен за 3 варна.")
        except: pass

@dp.message(Command("clear"))
async def clear(message: types.Message):
    if not is_admin(message.from_user.id): return
    try: count = int(message.text.split()[1])
    except: count = 10
    await message.delete()
    for i in range(count):
        try: await bot.delete_message(message.chat.id, message.message_id - i)
        except: pass

# --- РАЗВЛЕЧЕНИЯ ---
@dp.message(Command("coin"))
async def coin(message: types.Message):
    await message.reply(f"Монетка: <b>{random.choice(['Орел 🦅', 'Решка 🪙'])}</b>", parse_mode="HTML")

@dp.message(Command("dice"))
async def dice(message: types.Message):
    await message.reply(f"🎲 Выпало: <b>{random.randint(1, 6)}</b>", parse_mode="HTML")

# --- ДУЭЛИ (КРЕСТИКИ-НОЛИКИ) ---
@dp.message(Command("duel"))
async def duel_start(message: types.Message):
    if not message.reply_to_message: await message.reply("Ответь на сообщение друга!"); return
    opponent = message.reply_to_message.from_user
    if opponent.id == message.from_user.id: return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"dacc_{message.from_user.id}_{opponent.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="ddec")
    )
    await message.reply(f"⚔️ {opponent.first_name}, тебя вызывает {message.from_user.first_name}!", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("dacc_"))
async def duel_accept(callback: types.CallbackQuery):
    _, p1, p2 = callback.data.split("_")
    p1, p2 = int(p1), int(p2)
    if callback.from_user.id != p2: await callback.answer("Не тебя вызвали!"); return
    
    board = "_________"
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (p1, p2, board, turn) VALUES (?, ?, ?, ?)", (p1, p2, board, p1))
    d_id = c.lastrowid; conn.commit(); conn.close()
    
    await callback.message.edit_text("Игра началась! Ждите хода.")
    try: await bot.send_message(p1, "⚔️ Твой ход (❌):", reply_markup=get_duel_kb(board, d_id))
    except: pass

@dp.callback_query(F.data == "ddec")
async def duel_decline(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Дуэль отклонена.")

def get_duel_kb(board, d_id):
    builder = InlineKeyboardBuilder()
    for i in range(9):
        builder.button(text=board[i] if board[i] != "_" else "⬜", callback_data=f"dc_{d_id}_{i}")
    builder.adjust(3)
    return builder.as_markup()

@dp.callback_query(F.data.startswith("dc_"))
async def duel_move(callback: types.CallbackQuery):
    _, d_id, idx = callback.data.split("_")
    d_id, idx = int(d_id), int(idx)
    
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT p1, p2, board, turn FROM duels WHERE id = ?", (d_id,))
    d = c.fetchone()
    if not d: await callback.answer("Игра не найдена."); conn.close(); return
    p1, p2, board, turn = d
    
    if callback.from_user.id != turn: await callback.answer("❌ Не твой ход!"); conn.close(); return
    if board[idx] != "_": await callback.answer("❌ Занято!"); conn.close(); return
    
    sym = "❌" if callback.from_user.id == p1 else "⭕"
    nb = list(board); nb[idx] = sym; nbs = "".join(nb)
    
    # Проверка победы
    winner = None
    for a,b,c_i in [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]:
        if nbs[a] == nbs[b] == nbs[c_i] != "_": winner = nbs[a]; break
        
    if winner or "_" not in nbs:
        if winner:
            await callback.message.edit_text(f"🏆 Победа! ({winner})")
            await bot.send_message(p2 if winner == "❌" else p1, f"🏆 Соперник победил ({winner}).")
        else:
            await callback.message.edit_text("🤝 Ничья!")
        conn.close(); return
        
    nturn = p2 if turn == p1 else p1
    c.execute("UPDATE duels SET board = ?, turn = ? WHERE id = ?", (nbs, nturn, d_id))
    conn.commit(); conn.close()
    
    await callback.message.edit_text("Ход сделан. Жди...")
    try: await bot.send_message(nturn, "⚔️ Твой ход:", reply_markup=get_duel_kb(nbs, d_id))
    except: pass

# --- ПРИВЕТСТВИЕ ---
@dp.message(F.new_chat_members)
async def welcome(message: types.Message):
    for member in message.new_chat_members:
        await message.answer(f"👋 Добро пожаловать, {member.first_name}!")

# --- ЗАГЛУШКА ДЛЯ RENDER ---
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
