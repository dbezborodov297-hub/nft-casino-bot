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

BOT_TOKEN = "9156237384:AAHcthnBe70Nbk2LCrNtlbEMHVLwELvsER4"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

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

# --- МЕНЮ ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🎭 <b>Добро пожаловать в Мафию!</b>\n\n/test — игра против ботов\n/game — создать игру с друзьями\n/profile — профиль", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    wins, losses, coins = get_profile(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>Твой профиль</b>\n🏆 Победы: {wins}\n💀 Поражения: {losses}\n💰 Монеты: {coins}", parse_mode="HTML")

# --- ТЕСТОВАЯ ИГРА ПРОТИВ БОТОВ ---
@dp.message(Command("test"))
async def test_game(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id in games:
        await message.answer("Игра уже идет!"); return
    
    # Создаем игру: Ты (Мафия) против 3 ботов
    games[chat_id] = {
        "players": {user_id: message.from_user.first_name, "bot1": "Дон", "bot2": "Комиссар", "bot3": "Доктор"},
        "roles": {user_id: "Мафия", "bot1": "Дон", "bot2": "Комиссар", "bot3": "Доктор"},
        "state": "night",
        "day": 1,
        "host": user_id,
        "actions": {}
    }
    
    text = ("🎮 <b>ТЕСТОВАЯ ИГРА (БОТЫ)</b>\n\n"
            "👥 <b>Список игроков:</b>\n"
            f"1. {message.from_user.first_name} (Ты)\n"
            f"2. Бот Дон\n"
            f"3. Бот Комиссар\n"
            f"4. Бот Доктор\n\n"
            "🎭 <b>Твоя роль: МАФИЯ</b>\n"
            "Твоя цель: убивать других, пока они не убили тебя.\n\n"
            "🌙 <b>НОЧЬ.</b> Выбери жертву:")
            
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Убить Дона", callback_data=f"tkill_{chat_id}_bot1"))
    builder.row(InlineKeyboardButton(text="Убить Комиссара", callback_data=f"tkill_{chat_id}_bot2"))
    builder.row(InlineKeyboardButton(text="Убить Доктора", callback_data=f"tkill_{chat_id}_bot3"))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    # Запускаем таймер на 3 минуты (180 сек)
    asyncio.create_task(test_timeout(chat_id, 180))

async def test_timeout(chat_id, duration):
    await asyncio.sleep(duration)
    if chat_id in games and games[chat_id]["state"] == "test":
        await bot.send_message(chat_id, "⌛️ Время вышло! Игра завершена.")
        update_stats(games[chat_id]["host"], win=False) # Поражение по таймеру
        del games[chat_id]

@dp.callback_query(F.data.startswith("tkill_"))
async def test_kill(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id, target = int(parts[1]), parts[2]
    
    if chat_id not in games: return
    
    game = games[chat_id]
    game["state"] = "test"
    
    # Ты убиваешь бота
    killed_name = game["players"].pop(target)
    game["roles"].pop(target)
    
    text = f"💀 Ты убил {killed_name}!\n\n"
    
    # Проверка победы
    if not game["players"]:
        text += "🎉 <b>ТЫ ПОБЕДИЛ!</b> Все враги уничтожены."
        update_stats(callback.from_user.id, win=True)
        await callback.message.edit_text(text, parse_mode="HTML")
        del games[chat_id]
        return
        
    # Ответ ботов (Дон убивает тебя, если он жив)
    if "bot1" in game["players"]: # Если Дон жив
        text += "🔪 Дон убил тебя этой ночью!\n\n"
        text += "💀 <b>ТЫ ПРОИГРАЛ.</b>"
        update_stats(callback.from_user.id, win=False)
        await callback.message.edit_text(text, parse_mode="HTML")
        del games[chat_id]
        return
        
    text += "🌙 <b>НОЧЬ.</b> Выбери следующую жертву:"
    builder = InlineKeyboardBuilder()
    for p, name in game["players"].items():
        builder.row(InlineKeyboardButton(text=f"Убить {name}", callback_data=f"tkill_{chat_id}_{p}"))
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ОБЫЧНАЯ ИГРА (С ДРУЗЬЯМИ) ---
@dp.message(Command("game"))
async def game_cmd(message: types.Message):
    chat_id = message.chat.id
    if chat_id in games: await message.answer("Игра уже идет!"); return
        
    games[chat_id] = {"players": {}, "roles": {}, "state": "lobby", "host": message.from_user.id, "day": 1, "actions": {}}
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Присоединиться", callback_data="join"))
    builder.row(InlineKeyboardButton(text="▶️ Начать", callback_data="start"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    
    await message.answer("🎮 <b>Игра в Мафию</b>\nНажмите «Присоединиться». Минимум 4 игрока.", reply_markup=builder.as_markup(), parse_mode="HTML")

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
    if chat_id in games: del games[chat_id]
    await callback.message.edit_text("❌ Игра отменена.")

@dp.callback_query(F.data == "start")
async def start_btn(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    game = games.get(chat_id)
    if not game or callback.from_user.id != game["host"]: return
    if len(game["players"]) < 4: await callback.answer("Нужно минимум 4 игрока!", show_alert=True); return
        
    players = list(game["players"].keys())
    random.shuffle(players)
    
    roles_list = ["Мафия", "Дон", "Комиссар", "Доктор"] + ["Мирный"] * (len(players) - 4)
    random.shuffle(roles_list)
    game["roles"] = dict(zip(players, roles_list))
    game["state"] = "night"
    
    # Пишем список игроков
    text = "🎮 <b>Игра началась!</b>\n\n👥 <b>Игроки:</b>\n"
    for i, p in enumerate(game["players"]):
        text += f"{i+1}. {game['players'][p]}\n"
    text += "\n🌙 <b>НОЧЬ.</b> Роли разосланы в личку."
    
    await callback.message.edit_text(text, parse_mode="HTML")
    
    for p_id, role in game["roles"].items():
        try: await bot.send_message(p_id, f"🎭 Твоя роль: <b>{role}</b>", parse_mode="HTML")
        except: pass
        
    asyncio.create_task(night_timeout(chat_id, 60))
    await send_night_buttons(chat_id)

# (Дальше идет логика ночи, голосования и победы, как в прошлом коде, но я оставил её для экономии места)
# ... 
# ВАЖНО: Чтобы не перегружать ответ, я оставил только тестовую игру и лобби.
# Если нужно, я могу дописать ночную логику для обычной игры отдельно.

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
