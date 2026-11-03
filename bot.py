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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9156237384:AAHXpy6VJ0JHAkajM4154rMyZY-XIolvAhc"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Хранилище игр
games = {}
night_actions = {}

class MafiaStates(StatesGroup):
    night_action = State()

# --- МЕНЮ ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.row(InlineKeyboardButton(text="🎭 Создать Мафию", callback_data="mafia_create"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🌟 <b>Добро пожаловать!</b>\nВыбери действие:", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    await callback.message.edit_text("👤 <b>Профиль</b>\n💰 Баланс: 1000", parse_mode="HTML")

# --- ЛОББИ ---
@dp.callback_query(F.data == "mafia_create")
async def mafia_create(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in games:
        await callback.answer("Игра уже создана!", show_alert=True); return
        
    games[chat_id] = {"players": [], "host": callback.from_user.id, "state": "lobby"}
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Присоединиться", callback_data="mafia_join"))
    builder.row(InlineKeyboardButton(text="▶️ Начать игру", callback_data="mafia_start"))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="mafia_cancel"))
    
    await callback.message.edit_text("🎭 <b>МАФИЯ</b>\n\nНажмите «Присоединиться». Минимум 4 игрока.", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "mafia_join")
async def mafia_join(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in games or games[chat_id]["state"] != "lobby": return
    
    uid = callback.from_user.id
    if uid in games[chat_id]["players"]:
        await callback.answer("Ты уже в игре!"); return
    if len(games[chat_id]["players"]) >= 10:
        await callback.answer("Максимум 10 игроков!"); return
        
    games[chat_id]["players"].append(uid)
    await callback.answer(f"Ты в игре! (Игроков: {len(games[chat_id]['players'])})", show_alert=True)

@dp.callback_query(F.data == "mafia_cancel")
async def mafia_cancel(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in games:
        del games[chat_id]
    await callback.message.edit_text("❌ Игра отменена.")

# --- СТАРТ ИГРЫ И РАЗДАЧА РОЛЕЙ ---
@dp.callback_query(F.data == "mafia_start")
async def mafia_start(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    game = games.get(chat_id)
    
    if not game or callback.from_user.id != game["host"]: return
    if len(game["players"]) < 4:
        await callback.answer("Нужно минимум 4 игрока!", show_alert=True); return
        
    players = game["players"]
    random.shuffle(players)
    
    # Роли: 1 Мафия, 1 Дон, 1 Комиссар, 1 Доктор, остальные Мирные
    roles = ["Мафия", "Дон", "Комиссар", "Доктор"] + ["Мирный"] * (len(players) - 4)
    random.shuffle(roles)
    
    game["roles"] = dict(zip(players, roles))
    game["state"] = "night"
    
    for p_id, role in game["roles"].items():
        try:
            await bot.send_message(p_id, f"🎭 Твоя роль: <b>{role}</b>", parse_mode="HTML")
        except: pass
        
    await callback.message.edit_text("🌙 <b>НОЧЬ.</b>\nВсе роли разосланы в личку.\n\nМафия, Дон, Комиссар и Доктор — проверяйте личку!", parse_mode="HTML")
    
    # Запускаем ночную фазу
    await night_phase(chat_id)

async def night_phase(chat_id):
    game = games[chat_id]
    night_actions[chat_id] = {"kill": None, "heal": None, "check": None, "don_check": None}
    
    # Отправляем действия в личку
    for p_id, role in game["roles"].items():
        builder = InlineKeyboardBuilder()
        if role == "Мафия":
            for target in game["players"]:
                if target != p_id and game["roles"][target] != "Мафия":
                    builder.row(InlineKeyboardButton(text=f"Убить {target}", callback_data=f"act_kill_{chat_id}_{target}"))
        elif role == "Дон":
            for target in game["players"]:
                if target != p_id:
                    builder.row(InlineKeyboardButton(text=f"Проверить {target}", callback_data=f"act_don_{chat_id}_{target}"))
        elif role == "Комиссар":
            for target in game["players"]:
                if target != p_id:
                    builder.row(InlineKeyboardButton(text=f"Проверить {target}", callback_data=f"act_check_{chat_id}_{target}"))
        elif role == "Доктор":
            for target in game["players"]:
                builder.row(InlineKeyboardButton(text=f"Лечить {target}", callback_data=f"act_heal_{chat_id}_{target}"))
                
        if role in ["Мафия", "Дон", "Комиссар", "Доктор"]:
            try: await bot.send_message(p_id, f"🌙 Ночь. Твое действие ({role}):", reply_markup=builder.as_markup())
            except: pass

# --- НОЧНЫЕ ДЕЙСТВИЯ ---
@dp.callback_query(F.data.startswith("act_"))
async def night_action(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    action, chat_id, target = parts[1], int(parts[2]), int(parts[3])
    
    if chat_id not in night_actions: await callback.answer("Ошибка."); return
    
    night_actions[chat_id][action] = target
    await callback.answer("✅ Действие принято!", show_alert=True)
    await callback.message.delete()
    
    # Проверяем, все ли действия сделаны (упрощенно: ждем 15 секунд)
    if all(v is not None for v in night_actions[chat_id].values() if v != "skip"):
        pass # Тут можно ускорить, но для простоты ждем таймер

async def process_night_end(chat_id):
    if chat_id not in games: return
    game = games[chat_id]
    acts = night_actions.get(chat_id, {})
    
    killed = acts.get("kill")
    healed = acts.get("heal")
    
    # Если доктор вылечил убитого - никто не умирает
    if killed and killed != healed:
        game["players"].remove(killed)
        victim_role = game["roles"][killed]
        msg = f"🌅 <b>УТРО.</b>\nНочью был убит игрок {killed} ({victim_role})."
    else:
        msg = "🌅 <b>УТРО.</b>\nЭтой ночью никто не погиб!"
        
    # Проверка победы
    alive_mafia = sum(1 for p in game["players"] if game["roles"][p] in ["Мафия", "Дон"])
    alive_peace = len(game["players"]) - alive_mafia
    
    if alive_mafia == 0:
        await bot.send_message(chat_id, "🎉 <b>МИРНЫЕ ПОБЕДИЛИ!</b> Мафия уничтожена.")
        del games[chat_id]; return
    elif alive_mafia >= alive_peace:
        await bot.send_message(chat_id, "🔪 <b>МАФИЯ ПОБЕДИЛА!</b>")
        del games[chat_id]; return
        
    await bot.send_message(chat_id, msg + "\n\nНачинается голосование!", parse_mode="HTML")
    game["state"] = "voting"
    
    builder = InlineKeyboardBuilder()
    for p in game["players"]:
        builder.row(InlineKeyboardButton(text=f"Казнить {p}", callback_data=f"vote_{chat_id}_{p}"))
    await bot.send_message(chat_id, "🗳 Голосуйте, кого казнить:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("vote_"))
async def vote(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    chat_id, target = int(parts[1]), int(parts[2])
    if chat_id not in games: return
    
    game = games[chat_id]
    if target in game["players"]:
        game["players"].remove(target)
        role = game["roles"][target]
        await callback.message.edit_text(f"⚖️ Казнен {target} ({role}).\n\nНаступает ночь...", parse_mode="HTML")
        game["state"] = "night"
        await asyncio.sleep(3)
        await night_phase(chat_id)

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
