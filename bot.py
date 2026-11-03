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
from datetime import datetime, timedelta

BOT_TOKEN = "9184406467:AAHlQY4UZSGXhewbMPo75uXmvVgulwPPU4g"
ADMIN_ID = 8907438590
BOT_NAME = "IrisClone"

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
    c.execute('''CREATE TABLE IF NOT EXISTS antispam (user_id INTEGER, last_msg REAL, count INTEGER)''')
    conn.commit(); conn.close()

def get_user(user_id):
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("SELECT balance, xp, level, messages FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (100, 0, 1, 0)
    conn.close(); return res

def is_admin(user_id, chat_id):
    if user_id == ADMIN_ID: return True
    # Можно добавить проверку через bot.get_chat_member для реальных админов, но пока так
    return False

# --- СЧЕТЧИК СООБЩЕНИЙ И АНТИСПАМ ---
@dp.message()
async def count_messages(message: types.Message):
    if message.text and not message.text.startswith('/'):
        user_id = message.from_user.id
        conn = sqlite3.connect('mod.db'); c = conn.cursor()
        
        # Антиспам проверка
        c.execute("SELECT last_msg, count FROM antispam WHERE user_id = ?", (user_id,))
        spam_res = c.fetchone()
        now = time.time()
        
        if spam_res:
            last_msg, count = spam_res
            if now - last_msg < 3: # Если меньше 3 секунд между сообщениями
                count += 1
                if count >= 5: # 5 сообщений за 3 секунды = мут
                    try:
                        await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False))
                        await message.reply(f"🤐 {message.from_user.first_name} замучен на 10 минут за флуд!")
                        await asyncio.sleep(600)
                        await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=True))
                    except: pass
                    count = 0
            else:
                count = 1
            c.execute("UPDATE antispam SET last_msg = ?, count = ? WHERE user_id = ?", (now, count, user_id))
        else:
            c.execute("INSERT INTO antispam (user_id, last_msg, count) VALUES (?, ?, 1)", (user_id, now))
        
        # Начисление ирисов и XP
        c.execute("UPDATE users SET messages = messages + 1, balance = balance + 1, xp = xp + 5 WHERE user_id = ?", (user_id,))
        # Проверка уровня
        c.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        xp, lvl = c.fetchone()
        if xp >= lvl * 100:
            c.execute("UPDATE users SET level = level + 1, xp = xp - ? WHERE user_id = ?", (lvl*100, user_id))
            await message.reply(f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг {lvl+1} уровня!")
            
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
    text = "🏆 <b>Топ богачей чата:</b>\n\n"
    for i, (name, bal) in enumerate(top, 1):
        text += f"{i}. {name or 'Аноним'} — {bal} ирисок\n"
    await message.reply(text, parse_mode="HTML")

# --- МОДЕРАЦИЯ ---
@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not is_admin(message.from_user.id, message.chat.id): return
    if not message.reply_to_message: await message.reply("Ответь на сообщение!"); return
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply("🔨 Забанен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not is_admin(message.from_user.id, message.chat.id): return
    if not message.reply_to_message: await message.reply("Ответь на сообщение!"); return
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False))
        await message.reply("🤐 Замучен.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not is_admin(message.from_user.id, message.chat.id): return
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
    if not is_admin(message.from_user.id, message.chat.id): return
    count = int(message.text.split()[1]) if len(message.text.split()) > 1 else 10
    await message.delete()
    for i in range(count):
        try: await bot.delete_message(message.chat.id, message.message_id - i)
        except: pass

# --- РАЗВЛЕЧЕНИЯ ---
@dp.message(Command("coin"))
async def coin(message: types.Message):
    res = random.choice(["Орел 🦅", "Решка 🪙"])
    await message.reply(f"Монетка подброшена: <b>{res}</b>", parse_mode="HTML")

@dp.message(Command("dice"))
async def dice(message: types.Message):
    res = random.randint(1, 6)
    await message.reply(f"🎲 Выпало число: <b>{res}</b>", parse_mode="HTML")

# --- ДУЭЛИ ---
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
    await message.reply(f"⚔️ {opponent.first_name}, тебя вызывает {message.from_user.first_name} на дуэль!", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("dacc_"))
async def duel_accept(callback: types.CallbackQuery):
    _, p1, p2 = callback.data.split("_")
    p1, p2 = int(p1), int(p2)
    if callback.from_user.id != p2: await callback.answer("Не тебя вызвали!"); return
    
    board = "_________"
    conn = sqlite3.connect('mod.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (p1, p2, board, turn) VALUES (?, ?, ?, ?)", (p1, p2, board, p1))
    d_id = c.lastrowid
    conn.commit(); conn.close()
    
    await callback.message.edit_text("Игра началась! Ждите хода.")
    await bot.send_message(p1, "Твой ход (❌):", reply_markup=get_duel_kb(board, d_id))

def get_duel_kb(board, d_id):
    builder = InlineKeyboardBuilder()
    for i in range(9):
        builder.button(text=board[i] if board[i] != "_" else "⬜", callback_data=f"dc_{d_id}_{i}")
    builder.adjust(3)
    return builder.as_markup()

@dp.callback_query(F.data.startswith("dc_"))
async def duel_move(callback: types.CallbackQuery):
    # Упрощенная логика хода (без БД, просто для демонстрации)
    await callback.answer("Ход сделан (упрощенно)")
