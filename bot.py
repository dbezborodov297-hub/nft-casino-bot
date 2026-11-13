import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9022493828:AAFdH-1-mMpdG-BnBpxj3higF_2ztZgqX0M"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- ФЛАСК ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 first_name TEXT,
                 hp INTEGER DEFAULT 100,
                 max_hp INTEGER DEFAULT 100,
                 coins INTEGER DEFAULT 0,
                 wins INTEGER DEFAULT 0,
                 losses INTEGER DEFAULT 0)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT hp, max_hp, coins, wins, losses FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (100, 100, 0, 0, 0)
    conn.close(); return res

def update_hp(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET hp = hp + ? WHERE user_id = ?", (amount, uid))
    c.execute("UPDATE users SET hp = 0 WHERE hp < 0 AND user_id = ?", (uid,))
    conn.commit(); conn.close()

def update_coins(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, uid))
    conn.commit(); conn.close()

def update_stats(uid, win=False):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    if win:
        c.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (uid,))
    else:
        c.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (uid,))
    conn.commit(); conn.close()

# --- БОССЫ ---
BOSSES = {
    "👹 Гоблин": {"hp": 50, "damage": 10, "reward": 50},
    "🐉 Дракон": {"hp": 150, "damage": 25, "reward": 200},
    "👾 Космический жук": {"hp": 100, "damage": 15, "reward": 100},
    "🦂 Скорпион": {"hp": 80, "damage": 20, "reward": 80},
    "🦇 Летучая мышь": {"hp": 40, "damage": 5, "reward": 30},
    "👻 Призрак": {"hp": 120, "damage": 18, "reward": 150},
    "🐙 Осьминог": {"hp": 90, "damage": 12, "reward": 90},
    "🦍 Горилла": {"hp": 200, "damage": 30, "reward": 300},
    "👑 Король": {"hp": 300, "damage": 40, "reward": 500},
}

# --- ПРОФИЛЬ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    hp, max_hp, coins, wins, losses = get_user(message.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ {message.from_user.first_name}</b>\n\n"
            f"❤️ HP: <b>{hp}/{max_hp}</b>\n"
            f"💰 Монеты: <b>{coins}</b>\n"
            f"🏆 Победы: <b>{wins}</b> | 💀 Поражения: <b>{losses}</b>\n\n"
            f"Выбери действие:")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Дуэль 1 на 1", callback_data="duel_1v1"))
    builder.row(InlineKeyboardButton(text="🤝 Дуэль 2 на 2", callback_data="duel_2v2"))
    builder.row(InlineKeyboardButton(text="👹 Боссы", callback_data="bosses"))
    builder.row(InlineKeyboardButton(text="🏆 Топ побед", callback_data="top_wins"))
    builder.row(InlineKeyboardButton(text="💀 Топ поражений", callback_data="top_losses"))
    builder.row(InlineKeyboardButton(text="🩹 Лечение (10 монет)", callback_data="heal"))
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: types.CallbackQuery):
    hp, max_hp, coins, wins, losses = get_user(callback.from_user.id)
    text = (f"👤 <b>ПРОФИЛЬ {callback.from_user.first_name}</b>\n\n"
            f"❤️ HP: <b>{hp}/{max_hp}</b>\n"
            f"💰 Монеты: <b>{coins}</b>\n"
            f"🏆 Победы: <b>{wins}</b> | 💀 Поражения: <b>{losses}</b>\n\n"
            f"Выбери действие:")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Дуэль 1 на 1", callback_data="duel_1v1"))
    builder.row(InlineKeyboardButton(text="🤝 Дуэль 2 на 2", callback_data="duel_2v2"))
    builder.row(InlineKeyboardButton(text="👹 Боссы", callback_data="bosses"))
    builder.row(InlineKeyboardButton(text="🏆 Топ побед", callback_data="top_wins"))
    builder.row(InlineKeyboardButton(text="💀 Топ поражений", callback_data="top_losses"))
    builder.row(InlineKeyboardButton(text="🩹 Лечение (10 монет)", callback_data="heal"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ТАБЛИЦА ЛИДЕРОВ ПО ПОБЕДАМ ---
@dp.callback_query(lambda c: c.data == "top_wins")
async def top_wins(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, wins FROM users ORDER BY wins DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    
    if not top:
        return await callback.answer("Пока нет игроков.", show_alert=True)
    
    text = "🏆 <b>ТОП ПО ПОБЕДАМ</b>\n\n<blockquote>"
    for i, (username, first_name, wins) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{username}" if username else first_name
        text += f"{medal} {name} — <b>{wins}</b> побед\n"
    text += "</blockquote>"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ТАБЛИЦА ЛИДЕРОВ ПО ПОРАЖЕНИЯМ ---
@dp.callback_query(lambda c: c.data == "top_losses")
async def top_losses(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, losses FROM users ORDER BY losses DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    
    if not top:
        return await callback.answer("Пока нет игроков.", show_alert=True)
    
    text = "💀 <b>ТОП ПО ПОРАЖЕНИЯМ (худшие)</b>\n\n<blockquote>"
    for i, (username, first_name, losses) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{username}" if username else first_name
        text += f"{medal} {name} — <b>{losses}</b> поражений\n"
    text += "</blockquote>"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ЛЕЧЕНИЕ ---
@dp.callback_query(lambda c: c.data == "heal")
async def heal(callback: types.CallbackQuery):
    hp, max_hp, coins, _, _ = get_user(callback.from_user.id)
    if coins < 10:
        return await callback.answer("❌ Не хватает монет! Нужно 10.", show_alert=True)
    if hp >= max_hp:
        return await callback.answer("❤️ У тебя полное HP!", show_alert=True)
    update_coins(callback.from_user.id, -10)
    update_hp(callback.from_user.id, 20)
    hp, max_hp, coins, _, _ = get_user(callback.from_user.id)
    await callback.answer(f"🩹 Ты вылечился на 20 HP! Теперь: {hp}/{max_hp}", show_alert=True)

# --- БОССЫ ---
@dp.callback_query(lambda c: c.data == "bosses")
async def bosses_menu(callback: types.CallbackQuery):
    text = "👹 <b>БОССЫ</b>\nВыбери, с кем сразиться:\n\n"
    builder = InlineKeyboardBuilder()
    for boss_name, boss_data in BOSSES.items():
        text += f"{boss_name} — HP: {boss_data['hp']}, Урон: {boss_data['damage']}, Награда: {boss_data['reward']} монет\n"
        builder.row(InlineKeyboardButton(text=f"⚔️ Атаковать {boss_name}", callback_data=f"fight_boss_{boss_name}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("fight_boss_"))
async def fight_boss(callback: types.CallbackQuery):
    boss_name = callback.data.replace("fight_boss_", "")
    boss_data = BOSSES.get(boss_name)
    if not boss_data:
        return await callback.answer("❌ Босс не найден.", show_alert=True)
    
    hp, max_hp, coins, wins, losses = get_user(callback.from_user.id)
    if hp <= 0:
        return await callback.answer("💀 Ты мертв! Вылечись сначала.", show_alert=True)
    
    boss_hp = boss_data["hp"]
    player_hp = hp
    log = []
    
    while boss_hp > 0 and player_hp > 0:
        player_damage = random.randint(10, 25)
        boss_hp -= player_damage
        log.append(f"⚔️ Ты нанес {player_damage} урона. У босса осталось {max(0, boss_hp)} HP.")
        
        if boss_hp <= 0:
            break
        
        boss_damage = random.randint(5, boss_data["damage"])
        player_hp -= boss_damage
        log.append(f"👹 Босс нанес {boss_damage} урона. У тебя осталось {max(0, player_hp)} HP.")
    
    if boss_hp <= 0:
        update_coins(callback.from_user.id, boss_data["reward"])
        update_stats(callback.from_user.id, win=True)
        update_hp(callback.from_user.id, player_hp - hp)
        text = f"🎉 <b>ТЫ ПОБЕДИЛ {boss_name}!</b>\n\n" + "\n".join(log[-5:]) + f"\n\n💰 Награда: {boss_data['reward']} монет!"
    else:
        update_stats(callback.from_user.id, win=False)
        update_hp(callback.from_user.id, -hp)
        text = f"💀 <b>ТЫ ПРОИГРАЛ {boss_name}.</b>\n\n" + "\n".join(log[-5:])
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ДУЭЛИ (ЗАГЛУШКА) ---
@dp.callback_query(lambda c: c.data == "duel_1v1")
async def duel_1v1(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚔️ <b>ДУЭЛЬ 1 на 1</b>\n\nЭта механика в разработке. Пока ты можешь сражаться с боссами.",
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "duel_2v2")
async def duel_2v2(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🤝 <b>ДУЭЛЬ 2 на 2</b>\n\nЭта механика в разработке. Пока ты можешь сражаться с боссами.",
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup(),
        parse_mode="HTML"
    )

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(5)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
