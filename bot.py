import asyncio
import random
import sqlite3
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9209660223:AAHdxlNRtvVsrAcC8Q4qIUrHsOy8nocZshk"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

games = {}
LOBBY_TIMEOUT = 300
MIN_PLAYERS = 3
MAX_PLAYERS = 25

CREWMATE_TASKS = [
    "Напиши в чат слово «Электрика»",
    "Отправь в чат любой стикер",
    "Напиши в чат «Я не предатель»",
    "Отправь в чат эмодзи 🔧",
    "Напиши в чат имя любого игрока",
    "Отправь в чат 3 любых смайлика",
    "Напиши в чат «Где предатель?»",
    "Напиши в чат «Я делаю задания»",
    "Отправь в чат эмодзи 🚀",
    "Напиши в чат «Подозреваю...»",
    "Отправь в чат «Я чист»",
    "Напиши в чат любой цвет",
    "Отправь в чат эмодзи 🔍",
    "Напиши в чат «Я на задании»",
    "Отправь в чат эмодзи 🧑‍🚀",
    "Напиши в чат «Кто убийца?»",
    "Отправь в чат «Я видел(а) что-то»",
    "Напиши в чат «Не я!»",
    "Отправь в чат эмодзи ⚡",
]

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, coins INTEGER DEFAULT 0)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0,)
    conn.close(); return res[0]

def add_coins(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, uid))
    conn.commit(); conn.close()

@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚀 Начать Амонг Ас", callback_data="au_create"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🏆 Топ монет", callback_data="top"))
    await message.answer("👋 Привет! Выбери действие:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    coins = get_user(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>ПРОФИЛЬ</b>\n\n🪙 Монеты: <b>{coins}</b>", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "top")
async def top(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    if not top: return await callback.answer("Пусто.", show_alert=True)
    text = "🏆 <b>ТОП МОНЕТ</b>\n\n<blockquote>" + "".join([f"{'🥇' if i==1 else '🥈' if i==2 else '🥉' if i==3 else f'{i}.'} {f'@{u}' if u else f} — <b>{c}</b> 🪙\n" for i, (u, f, c) in enumerate(top, 1)]) + "</blockquote>"
    await callback.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "au_create")
async def create_game(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in games:
        return await callback.answer("❌ Игра уже создана!", show_alert=True)
    
    games[chat_id] = {
        "players": {},
        "host": callback.from_user.id,
        "state": "lobby",
        "roles": {},
        "tasks": {},
        "alive": [],
        "end_time": asyncio.get_event_loop().time() + LOBBY_TIMEOUT,
        "message_id": None
    }
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Присоединиться", callback_data="au_join"))
    builder.row(InlineKeyboardButton(text="▶️ Начать сейчас (хост)", callback_data="au_start"))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="au_cancel"))
    
    msg = await callback.message.edit_text(
        f"🚀 <b>АМОНГ АС</b>\n\n"
        f"👑 <b>Создатель:</b> {callback.from_user.first_name}\n"
        f"👥 <b>Игроков:</b> 0/{MAX_PLAYERS}\n"
        f"⏳ <b>До старта:</b> 5:00\n\n"
        f"<blockquote>Пока никого...</blockquote>\n"
        f"<i>Минимум {MIN_PLAYERS} игрока.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    games[chat_id]["message_id"] = msg.message_id
    
    asyncio.create_task(lobby_timer(chat_id, msg))

async def update_lobby_message(chat_id, msg):
    if chat_id not in games: return
    game = games[chat_id]
    now = asyncio.get_event_loop().time()
    left = max(0, int(game["end_time"] - now))
    mins = left // 60
    secs = left % 60
    
    players_list = ""
    if not game["players"]:
        players_list = "Пока никого..."
    else:
        for i, (uid, name) in enumerate(game["players"].items(), 1):
            players_list += f"{i}. {name}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Присоединиться", callback_data="au_join"))
    builder.row(InlineKeyboardButton(text="▶️ Начать сейчас (хост)", callback_data="au_start"))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="au_cancel"))
    
    try:
        await msg.edit_text(
            f"🚀 <b>АМОНГ АС</b>\n\n"
            f"👑 <b>Создатель:</b> {game['players'].get(game['host'], 'Хост')}\n"
            f"👥 <b>Игроков:</b> {len(game['players'])}/{MAX_PLAYERS}\n"
            f"⏳ <b>До старта:</b> {mins}:{secs:02d}\n\n"
            f"<blockquote>{players_list}</blockquote>\n"
            f"<i>Минимум {MIN_PLAYERS} игрока.</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except: pass

async def lobby_timer(chat_id, msg):
    while chat_id in games and games[chat_id]["state"] == "lobby":
        await asyncio.sleep(5)
        if chat_id not in games: return
        game = games[chat_id]
        now = asyncio.get_event_loop().time()
        
        if now >= game["end_time"]:
            if len(game["players"]) >= MIN_PLAYERS:
                await launch_game(chat_id, msg)
            else:
                await msg.edit_text(
                    f"❌ <b>ИГРА ОТМЕНЕНА</b>\n\n"
                    f"Не набралось {MIN_PLAYERS} игроков за 5 минут.\n"
                    f"Было: {len(game['players'])} чел.",
                    parse_mode="HTML"
                )
                del games[chat_id]
            return
        else:
            await update_lobby_message(chat_id, msg)

@dp.callback_query(lambda c: c.data == "au_join")
async def join_game(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in games or games[chat_id]["state"] != "lobby":
        return await callback.answer("❌ Игра не в лобби!", show_alert=True)
    
    uid = callback.from_user.id
    game = games[chat_id]
    if uid in game["players"]:
        return await callback.answer("Ты уже в игре!", show_alert=True)
    
    if len(game["players"]) >= MAX_PLAYERS:
        return await callback.answer(f"❌ Максимум {MAX_PLAYERS} игроков!", show_alert=True)
    
    game["players"][uid] = callback.from_user.first_name
    await callback.answer(f"✅ Ты в игре! (Игроков: {len(game['players'])})", show_alert=True)
    await update_lobby_message(chat_id, callback.message)

@dp.callback_query(lambda c: c.data == "au_cancel")
async def cancel_game(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in games:
        del games[chat_id]
    await callback.message.edit_text("❌ Игра отменена.")

@dp.callback_query(lambda c: c.data == "au_start")
async def start_game(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in games: return await callback.answer("❌ Игра не найдена!")
    
    game = games[chat_id]
    if callback.from_user.id != game["host"]:
        return await callback.answer("❌ Только создатель может начать!", show_alert=True)
    
    if len(game["players"]) < MIN_PLAYERS:
        return await callback.answer(f"❌ Нужно минимум {MIN_PLAYERS} игрока!", show_alert=True)
    
    await launch_game(chat_id, callback.message)

async def launch_game(chat_id, msg):
    game = games[chat_id]
    game["state"] = "playing"
    
    players = list(game["players"].keys())
    random.shuffle(players)
    
    impostor_count = max(1, len(players) // 5)
    impostors = players[:impostor_count]
    
    for p in players:
        if p in impostors:
            game["roles"][p] = "Предатель"
        else:
            game["roles"][p] = "Мирный"
            game["tasks"][p] = random.choice(CREWMATE_TASKS)
    
    game["alive"] = players.copy()
    
    for p_id, role in game["roles"].items():
        try:
            if role == "Предатель":
                await bot.send_message(p_id, f"🔪 <b>Ты — ПРЕДАТЕЛЬ!</b>\n\nТвоя цель: убивать мирных и не попасться.", parse_mode="HTML")
            else:
                task = game["tasks"][p_id]
                await bot.send_message(p_id, f"🧑‍🚀 <b>Ты — МИРНЫЙ!</b>\n\nТвое задание: {task}\n\nВыполни его в чате и получи монеты!", parse_mode="HTML")
        except:
            pass
    
    await msg.edit_text(
        f"🚀 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"👥 Игроков: {len(players)}\n"
        f"🔪 Предателей: {impostor_count}\n\n"
        f"Роли разосланы в ЛС. Проверьте личку!",
        parse_mode="HTML"
    )
    
    await asyncio.sleep(60)
    if chat_id in games and games[chat_id]["state"] == "playing":
        await start_voting(chat_id)

async def start_voting(chat_id):
    game = games[chat_id]
    if not game["alive"]: return
    
    builder = InlineKeyboardBuilder()
    for uid in game["alive"]:
        name = game["players"][uid]
        builder.row(InlineKeyboardButton(text=f"Изгнать {name}", callback_data=f"vote_{chat_id}_{uid}"))
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data=f"skip_{chat_id}"))
    
    await bot.send_message(chat_id, "🗳 <b>ГОЛОСОВАНИЕ!</b>\n\nКого изгнать?", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def vote(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id = int(parts[1])
    target_id = int(parts[2])
    
    if chat_id not in games: return await callback.answer("❌ Игра не найдена!")
    game = games[chat_id]
    if target_id not in game["alive"]: return await callback.answer("❌ Игрок уже мертв!")
    
    game["alive"].remove(target_id)
    role = game["roles"].get(target_id, "Мирный")
    name = game["players"].get(target_id, "Неизвестно")
    
    await callback.message.edit_text(
        f"🗳 <b>ГОЛОСОВАНИЕ ЗАВЕРШЕНО!</b>\n\nИзгнан: {name}\nРоль: {role}\n\n{'🎉 Мирные победили!' if role == 'Предатель' else '😢 Мирные ошиблись!'}",
        parse_mode="HTML"
    )
    
    alive_impostors = [p for p in game["alive"] if game["roles"][p] == "Предатель"]
    alive_crewmates = [p for p in game["alive"] if game["roles"][p] == "Мирный"]
    
    if not alive_impostors:
        await callback.message.answer("🎉 <b>МИРНЫЕ ПОБЕДИЛИ!</b> Все предатели изгнаны!")
        del games[chat_id]
    elif len(alive_impostors) >= len(alive_crewmates):
        await callback.message.answer("🔪 <b>ПРЕДАТЕЛИ ПОБЕДИЛИ!</b>")
        del games[chat_id]
    else:
        await callback.message.answer("🔄 Игра продолжается... Предатели еще живы!")
        await asyncio.sleep(60)
        if chat_id in games:
            await start_voting(chat_id)

@dp.callback_query(lambda c: c.data.startswith("skip_"))
async def skip_vote(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id = int(parts[1])
    if chat_id not in games: return await callback.answer("❌ Игра не найдена!")
    await callback.message.edit_text("🗳 Голосование пропущено. Никто не изгнан.")
    await asyncio.sleep(60)
    if chat_id in games:
        await start_voting(chat_id)

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Амонг Ас бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
