import asyncio
import random
import sqlite3
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9156237384:AAHZZen7uD6p0R3kQpOo0KRZceIbncnTuNw"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ХРАНИЛИЩЕ ИГР ---
games = {}

# --- БД ---
def init_db():
    conn = sqlite3.connect('mafia.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)''')
    conn.commit(); conn.close()

def get_profile(user_id):
    conn = sqlite3.connect('mafia.db'); c = conn.cursor()
    c.execute("SELECT wins, losses, coins FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit(); res = (0, 0, 0)
    conn.close(); return res

def update_stats(user_id, win=False):
    conn = sqlite3.connect('mafia.db'); c = conn.cursor()
    if win:
        c.execute("UPDATE users SET wins = wins + 1, coins = coins + 10 WHERE user_id = ?", (user_id,))
    else:
        c.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
    conn.commit(); conn.close()

# --- ТАЙМЕРЫ ---
async def night_timeout(chat_id, duration=60):
    await asyncio.sleep(duration)
    if chat_id in games and games[chat_id]["state"] == "night":
        await resolve_night(chat_id, timeout=True)

async def day_timeout(chat_id, duration=120):
    await asyncio.sleep(duration)
    if chat_id in games and games[chat_id]["state"] == "day":
        await start_voting(chat_id)

# --- МЕНЮ ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🎭 <b>Добро пожаловать в Мафию!</b>\n\nДобавь меня в группу и напиши /game, чтобы начать.", reply_markup=main_menu(), parse_mode="HTML")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer("📖 <b>Команды:</b>\n/game — создать игру\n/startgame — начать\n/profile — профиль\n/cancel — отменить", parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    wins, losses, coins = get_profile(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>Твой профиль</b>\n\n🏆 Победы: {wins}\n💀 Поражения: {losses}\n💰 Монеты: {coins}", parse_mode="HTML")

# --- ЛОББИ ---
@dp.message(Command("game"))
async def game_cmd(message: types.Message):
    chat_id = message.chat.id
    if chat_id in games:
        await message.answer("❌ Игра уже идет!"); return
        
    games[chat_id] = {"players": {}, "roles": {}, "state": "lobby", "host": message.from_user.id, "day": 1, "actions": {}}
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Присоединиться", callback_data="join"))
    builder.row(InlineKeyboardButton(text="▶️ Начать", callback_data="start"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    
    await message.answer(f"🎮 <b>Игра в Мафию</b>\nСоздатель: {message.from_user.first_name}\n\nЖдем игроков (минимум 4):", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "join")
async def join(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in games or games[chat_id]["state"] != "lobby": return
    
    if callback.from_user.id in games[chat_id]["players"]:
        await callback.answer("Ты уже в игре!"); return
        
    games[chat_id]["players"][callback.from_user.id] = callback.from_user.first_name
    await callback.answer(f"✅ Ты в игре! Игроков: {len(games[chat_id]['players'])}", show_alert=True)

@dp.callback_query(F.data == "cancel")
async def cancel(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in games and callback.from_user.id == games[chat_id]["host"]:
        del games[chat_id]
        await callback.message.edit_text("❌ Игра отменена.")
    else:
        await callback.answer("Только создатель может отменить.")

# --- СТАРТ ИГРЫ ---
@dp.message(Command("startgame"))
async def startgame_cmd(message: types.Message):
    await start_game_logic(message.chat.id, message.from_user.id, message)

@dp.callback_query(F.data == "start")
async def start_btn(callback: types.CallbackQuery):
    await start_game_logic(callback.message.chat.id, callback.from_user.id, callback.message)

async def start_game_logic(chat_id, user_id, message):
    if chat_id not in games or games[chat_id]["host"] != user_id: return
    if len(games[chat_id]["players"]) < 4:
        await message.answer("❌ Нужно минимум 4 игрока!"); return
        
    game = games[chat_id]
    players = list(game["players"].keys())
    random.shuffle(players)
    
    roles_list = ["Мафия", "Дон", "Комиссар", "Доктор"] + ["Мирный"] * (len(players) - 4)
    random.shuffle(roles_list)
    game["roles"] = dict(zip(players, roles_list))
    game["state"] = "night"
    
    for p_id, role in game["roles"].items():
        try: await bot.send_message(p_id, f"🎭 Твоя роль: <b>{role}</b>", parse_mode="HTML")
        except: pass
        
    await bot.send_message(chat_id, "🌙 <b>НОЧЬ 1.</b>\nРоли разосланы. У ролей есть 60 секунд на действие.", parse_mode="HTML")
    asyncio.create_task(night_timeout(chat_id, 60))
    await send_night_buttons(chat_id)

async def send_night_buttons(chat_id):
    game = games[chat_id]
    for p_id, role in game["roles"].items():
        builder = InlineKeyboardBuilder()
        targets = [t for t in game["players"] if t != p_id]
        
        if role in ["Мафия", "Дон"]:
            for t in targets:
                if game["roles"][t] not in ["Мафия", "Дон"]:
                    builder.row(InlineKeyboardButton(text=f"🔪 {game['players'][t]}", callback_data=f"act_kill_{chat_id}_{t}"))
        elif role == "Комиссар":
            for t in targets:
                builder.row(InlineKeyboardButton(text=f"🔍 {game['players'][t]}", callback_data=f"act_check_{chat_id}_{t}"))
        elif role == "Доктор":
            for t in targets:
                builder.row(InlineKeyboardButton(text=f"💉 {game['players'][t]}", callback_data=f"act_heal_{chat_id}_{t}"))
                
        if role in ["Мафия", "Дон", "Комиссар", "Доктор"]:
            try: await bot.send_message(p_id, "Выбери цель:", reply_markup=builder.as_markup())
            except: pass

# --- ДЕЙСТВИЯ НОЧИ ---
@dp.callback_query(F.data.startswith("act_"))
async def night_action(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    action, chat_id, target = parts[1], int(parts[2]), int(parts[3])
    
    if chat_id not in games: return
    games[chat_id]["actions"][callback.from_user.id] = {"type": action, "target": target}
    await callback.answer("✅ Принято!")
    await callback.message.delete()

async def resolve_night(chat_id, timeout=False):
    if chat_id not in games or games[chat_id]["state"] != "night": return
    game = games[chat_id]
    acts = game["actions"]
    
    killed = None
    healed = None
    
    for uid, act in acts.items():
        if act["type"] == "kill": killed = act["target"]
        if act["type"] == "heal": healed = act["target"]
        if act["type"] == "check":
            role = game["roles"].get(act["target"], "?")
            try: await bot.send_message(uid, f"🔍 Проверка: {game['players'][act['target']]} — <b>{role}</b>", parse_mode="HTML")
            except: pass

    if killed and killed != healed:
        dead_name = game["players"].pop(killed)
        dead_role = game["roles"].pop(killed)
        msg = f"☀️ <b>ДЕНЬ {game['day']}.</b>\n💀 Убит: {dead_name} ({dead_role})."
    else:
        msg = f"☀️ <b>ДЕНЬ {game['day']}.</b>\nНикто не погиб."
        
    game["actions"].clear()
    
    # Победа
    alive_mafia = sum(1 for r in game["roles"].values() if r in ["Мафия", "Дон"])
    alive_peace = len(game["roles"]) - alive_mafia
    
    if alive_mafia == 0:
        await bot.send_message(chat_id, msg + "\n\n🎉 <b>МИРНЫЕ ПОБЕДИЛИ!</b>", parse_mode="HTML")
        for p, r in game["roles"].items():
            if r not in ["Мафия", "Дон"]: update_stats(p, win=True)
        del games[chat_id]; return
    elif alive_mafia >= alive_peace:
        await bot.send_message(chat_id, msg + "\n\n🔪 <b>МАФИЯ ПОБЕДИЛА!</b>", parse_mode="HTML")
        for p, r in game["roles"].items():
            if r in ["Мафия", "Дон"]: update_stats(p, win=True)
        del games[chat_id]; return
        
    await bot.send_message(chat_id, msg + "\n\n🗳 Голосование (у вас 60 сек):", parse_mode="HTML")
    game["state"] = "voting"
    asyncio.create_task(vote_timeout(chat_id, 60))
    await send_voting_buttons(chat_id)

async def send_voting_buttons(chat_id):
    game = games[chat_id]
    builder = InlineKeyboardBuilder()
    for p, name in game["players"].items():
        builder.row(InlineKeyboardButton(text=f"Казнить {name}", callback_data=f"vote_{chat_id}_{p}"))
    await bot.send_message(chat_id, "Выбери, кого изгнать:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("vote_"))
async def vote(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id, target = int(parts[1]), int(parts[2])
    if chat_id not in games or games[chat_id]["state"] != "voting": return
    
    game = games[chat_id]
    if target in game["players"]:
        name = game["players"].pop(target)
        role = game["roles"].pop(target)
        await callback.message.edit_text(f"⚖️ {name} изгнан. Его роль: {role}.\n\nНаступает ночь...", parse_mode="HTML")
        game["day"] += 1
        game["state"] = "night"
        await asyncio.sleep(3)
        asyncio.create_task(night_timeout(chat_id, 60))
        await send_night_buttons(chat_id)

async def vote_timeout(chat_id, duration):
    await asyncio.sleep(duration)
    if chat_id in games and games[chat_id]["state"] == "voting":
        await bot.send_message(chat_id, "⌛️ Время вышло! Никто не изгнан.")
        games[chat_id]["day"] += 1
        games[chat_id]["state"] = "night"
        asyncio.create_task(night_timeout(chat_id, 60))
        await send_night_buttons(chat_id)

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
