import asyncio, random, sqlite3, os, time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9022493828:AAHQa69O9lHEMZtIW3YDx01LXbcj0c6dG20"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class St(StatesGroup):
    in_battle = State()
    in_duel = State()

# --- FLASK ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- DB ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, hp INTEGER DEFAULT 100, max_hp INTEGER DEFAULT 100, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, coins INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY AUTOINCREMENT, ch_id INTEGER, op_id INTEGER, status TEXT DEFAULT 'pending', created_at REAL, ch_hp INTEGER DEFAULT 100, op_hp INTEGER DEFAULT 100, turn_id INTEGER)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT hp, max_hp, level, xp, coins, wins, losses, username, first_name FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (100, 100, 1, 0, 0, 0, 0, None, None)
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
    if win: c.execute("UPDATE users SET wins = wins + 1, xp = xp + 20 WHERE user_id = ?", (uid,))
    else: c.execute("UPDATE users SET losses = losses + 1, xp = xp + 5 WHERE user_id = ?", (uid,))
    c.execute("SELECT xp, level FROM users WHERE user_id = ?", (uid,))
    xp, lvl = c.fetchone()
    if xp >= lvl * 100: c.execute("UPDATE users SET level = level + 1, xp = xp - ? WHERE user_id = ?", (lvl * 100, uid))
    conn.commit(); conn.close()

def save_user_info(uid, uname, fname):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (uname, fname, uid))
    conn.commit(); conn.close()

# --- BOSSES ---
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

# --- PROFILE ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    hp, max_hp, lvl, xp, coins, wins, losses, _, _ = get_user(message.from_user.id)
    needed = lvl * 100
    progress = min(int((xp / needed) * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    text = (f"👤 <b>ПРОФИЛЬ {message.from_user.first_name}</b>\n\n❤️ HP: <b>{hp}/{max_hp}</b>\n📈 Уровень: <b>{lvl}</b>\n[{bar}] {xp}/{needed}\n\n💰 Монеты: <b>{coins}</b>\n🏆 Победы: <b>{wins}</b> | 💀 Поражения: <b>{losses}</b>\n\nВыбери действие:")
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👹 Боссы", callback_data="bosses"))
    b.row(InlineKeyboardButton(text="⚔️ Дуэль 1 на 1", callback_data="duel_menu"))
    b.row(InlineKeyboardButton(text="🏆 Топ побед", callback_data="top_wins"))
    b.row(InlineKeyboardButton(text="💀 Топ поражений", callback_data="top_losses"))
    b.row(InlineKeyboardButton(text="🩹 Лечение (10 монет)", callback_data="heal"))
    await message.answer(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: types.CallbackQuery):
    hp, max_hp, lvl, xp, coins, wins, losses, _, _ = get_user(callback.from_user.id)
    needed = lvl * 100
    progress = min(int((xp / needed) * 10), 10)
    bar = "█" * progress + "░" * (10 - progress)
    text = (f"👤 <b>ПРОФИЛЬ {callback.from_user.first_name}</b>\n\n❤️ HP: <b>{hp}/{max_hp}</b>\n📈 Уровень: <b>{lvl}</b>\n[{bar}] {xp}/{needed}\n\n💰 Монеты: <b>{coins}</b>\n🏆 Победы: <b>{wins}</b> | 💀 Поражения: <b>{losses}</b>\n\nВыбери действие:")
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👹 Боссы", callback_data="bosses"))
    b.row(InlineKeyboardButton(text="⚔️ Дуэль 1 на 1", callback_data="duel_menu"))
    b.row(InlineKeyboardButton(text="🏆 Топ побед", callback_data="top_wins"))
    b.row(InlineKeyboardButton(text="💀 Топ поражений", callback_data="top_losses"))
    b.row(InlineKeyboardButton(text="🩹 Лечение (10 монет)", callback_data="heal"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

# --- TOPS ---
@dp.callback_query(lambda c: c.data == "top_wins")
async def top_wins(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, wins FROM users ORDER BY wins DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    if not top: return await callback.answer("Пока нет игроков.", show_alert=True)
    text = "🏆 <b>ТОП ПО ПОБЕДАМ</b>\n\n<blockquote>"
    for i, (un, fn, w) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{un}" if un else (fn if fn else "Игрок")
        text += f"{medal} {name} — <b>{w}</b> побед\n"
    text += "</blockquote>"
    b = InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "top_losses")
async def top_losses(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, losses FROM users ORDER BY losses DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    if not top: return await callback.answer("Пока нет игроков.", show_alert=True)
    text = "💀 <b>ТОП ПО ПОРАЖЕНИЯМ</b>\n\n<blockquote>"
    for i, (un, fn, l) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = f"@{un}" if un else (fn if fn else "Игрок")
        text += f"{medal} {name} — <b>{l}</b> поражений\n"
    text += "</blockquote>"
    b = InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

# --- HEAL ---
@dp.callback_query(lambda c: c.data == "heal")
async def heal(callback: types.CallbackQuery):
    hp, max_hp, _, _, coins, _, _, _, _ = get_user(callback.from_user.id)
    if coins < 10: return await callback.answer("❌ Нужно 10 монет.", show_alert=True)
    if hp >= max_hp: return await callback.answer("❤️ У тебя полное HP!", show_alert=True)
    update_coins(callback.from_user.id, -10)
    update_hp(callback.from_user.id, 20)
    hp, max_hp, _, _, coins, _, _, _, _ = get_user(callback.from_user.id)
    await callback.answer(f"🩹 +20 HP! Теперь: {hp}/{max_hp}", show_alert=True)

# --- BOSSES ---
@dp.callback_query(lambda c: c.data == "bosses")
async def bosses_menu(callback: types.CallbackQuery):
    text = "👹 <b>БОССЫ</b>\n\n"
    b = InlineKeyboardBuilder()
    for name, data in BOSSES.items():
        text += f"{name} — HP: {data['hp']}, Урон: {data['damage']}, Награда: {data['reward']} монет\n"
        b.row(InlineKeyboardButton(text=f"⚔️ {name}", callback_data=f"boss_start_{name}"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("boss_start_"))
async def boss_start(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.replace("boss_start_", "")
    data = BOSSES.get(name)
    if not data: return await callback.answer("❌ Нет босса.", show_alert=True)
    hp, _, _, _, _, _, _, _, _ = get_user(callback.from_user.id)
    if hp <= 0: return await callback.answer("💀 Ты мертв!", show_alert=True)
    await state.update_data(boss_name=name, boss_hp=data["hp"], player_hp=hp, boss_data=data, aimed=False, blinded=False)
    await state.set_state(St.in_battle)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎯 Прицелиться", callback_data="boss_aim"), InlineKeyboardButton(text="🔫 Стрелять", callback_data="boss_shoot"))
    b.row(InlineKeyboardButton(text="💥 Ослепить", callback_data="boss_blind"), InlineKeyboardButton(text="💨 Уклониться", callback_data="boss_dodge"))
    b.row(InlineKeyboardButton(text="🏳️ Сдаться", callback_data="boss_surrender"))
    await callback.message.edit_text(f"⚔️ <b>Бой с {name}</b>\n\n👹 HP босса: {data['hp']}\n❤️ Твое HP: {hp}\n\nВыбери действие:", reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("boss_"), St.in_battle)
async def boss_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.replace("boss_", "")
    data = await state.get_data()
    name, bhp, php, bdata, aimed, blinded = data['boss_name'], data['boss_hp'], data['player_hp'], data['boss_data'], data.get('aimed', False), data.get('blinded', False)
    if not bdata or bhp <= 0 or php <= 0: await state.clear(); return await callback.answer("Бой окончен.", show_alert=True)
    msg = ""
    if action == "aim": aimed = True; msg = "🎯 Ты прицелился! Шанс попасть 90%."
    elif action == "shoot":
        hit = 0.9 if aimed else 0.5; aimed = False
        if random.random() < hit: dmg = random.randint(20, 35) * 2; bhp -= dmg; msg = f"🔫 <b>КРИТ!</b> {dmg} урона."
        else: msg = "🔫 <b>Промах!</b>"; dmg = random.randint(5, bdata['damage']); php -= dmg; msg += f"\n👹 Босс нанес {dmg} урона."
    elif action == "blind":
        if random.random() < 0.5: blinded = True; msg = "💥 Ты ослепил босса!"
        else: msg = "💥 Не вышло."; dmg = random.randint(5, bdata['damage']) * 2; php -= dmg; msg += f"\n👹 Босс нанес {dmg} урона (x2)."
    elif action == "dodge": msg = "💨 Ты уклонился!"; dmg = random.randint(5, bdata['damage']) // 2; php -= dmg; msg += f"\n👹 Босс нанес {dmg} урона."
    elif action == "surrender": await state.clear(); update_stats(callback.from_user.id, win=False); return await callback.message.edit_text("🏳️ Сдался.", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup())
    if bhp <= 0:
        update_stats(callback.from_user.id, win=True); update_coins(callback.from_user.id, bdata['reward']); update_hp(callback.from_user.id, php - data['player_hp']); await state.clear()
        return await callback.message.edit_text(f"🎉 <b>Победа!</b>\n💰 +{bdata['reward']} монет!", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup(), parse_mode="HTML")
    elif php <= 0:
        update_stats(callback.from_user.id, win=False); update_hp(callback.from_user.id, -data['player_hp']); await state.clear()
        return await callback.message.edit_text(f"💀 <b>Поражение.</b>", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup(), parse_mode="HTML")
    await state.update_data(boss_hp=bhp, player_hp=php, aimed=aimed, blinded=blinded)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎯 Прицелиться", callback_data="boss_aim"), InlineKeyboardButton(text="🔫 Стрелять", callback_data="boss_shoot"))
    b.row(InlineKeyboardButton(text="💥 Ослепить", callback_data="boss_blind"), InlineKeyboardButton(text="💨 Уклониться", callback_data="boss_dodge"))
    b.row(InlineKeyboardButton(text="🏳️ Сдаться", callback_data="boss_surrender"))
    await callback.message.edit_text(f"⚔️ <b>Бой с {name}</b>\n\n👹 HP босса: {bhp}\n❤️ Твое HP: {php}\n\n{msg}\n\nВыбери действие:", reply_markup=b.as_markup(), parse_mode="HTML")

# --- DUELS (PvP) ---
@dp.callback_query(lambda c: c.data == "duel_menu")
async def duel_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("⚔️ <b>ДУЭЛЬ 1 НА 1</b>\n\nОтветь на сообщение игрока командой /duel, чтобы вызвать его на бой.", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")).as_markup(), parse_mode="HTML")

@dp.message(Command("duel"))
async def duel_cmd(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение игрока.")
    op = message.reply_to_message.from_user
    if op.id == message.from_user.id: return await message.reply("❌ Нельзя с собой.")
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("INSERT INTO duels (ch_id, op_id, created_at) VALUES (?, ?, ?)", (message.from_user.id, op.id, time.time()))
    did = c.lastrowid; conn.commit(); conn.close()
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_duel_{did}"), InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_duel_{did}"))
    try:
        await bot.send_message(op.id, f"⚔️ {message.from_user.first_name} вызывает тебя на дуэль!\n5 минут на ответ.", reply_markup=b.as_markup())
        await message.reply("✅ Вызов отправлен!")
    except: await message.reply("❌ Не удалось отправить.")
    async def timer():
        await asyncio.sleep(300)
        conn = sqlite3.connect('bot.db'); c = conn.cursor()
        c.execute("SELECT status FROM duels WHERE id = ?", (did,))
        if c.fetchone()[0] == "pending":
            c.execute("UPDATE duels SET status = 'expired' WHERE id = ?", (did,)); conn.commit()
            try: await bot.send_message(message.from_user.id, "⌛️ Вызов истек.")
            except: pass
        conn.close()
    asyncio.create_task(timer())

@dp.callback_query(lambda c: c.data.startswith("accept_duel_"))
async def accept_duel(callback: types.CallbackQuery):
    did = int(callback.data.split("_")[2])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT ch_id, op_id, status FROM duels WHERE id = ?", (did,))
    res = c.fetchone()
    if not res or res[2] != "pending": conn.close(); return await callback.answer("❌ Неактивна.", show_alert=True)
    ch_id, op_id, _ = res
    if callback.from_user.id != op_id: conn.close(); return await callback.answer("❌ Не твой вызов.", show_alert=True)
    c.execute("UPDATE duels SET status = 'active', turn_id = ? WHERE id = ?", (ch_id, did)); conn.commit(); conn.close()
    await callback.message.edit_text("✅ Ты принял дуэль! Жди своего хода.")
    b = InlineKeyboardBuilder().row(InlineKeyboardButton(text="⚔️ Атаковать", callback_data=f"atk_{did}"))
    await bot.send_message(ch_id, "⚔️ Дуэль началась! Твой ход:", reply_markup=b.as_markup())

@dp.callback_query(lambda c: c.data.startswith("decline_duel_"))
async def decline_duel(callback: types.CallbackQuery):
    did = int(callback.data.split("_")[2])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE duels SET status = 'declined' WHERE id = ?", (did,)); conn.commit(); conn.close()
    await callback.message.edit_text("❌ Отклонено.")

@dp.callback_query(lambda c: c.data.startswith("atk_"))
async def atk(callback: types.CallbackQuery):
    did = int(callback.data.split("_")[1])
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT ch_id, op_id, ch_hp, op_hp, turn_id FROM duels WHERE id = ? AND status = 'active'", (did,))
    res = c.fetchone()
    if not res: conn.close(); return await callback.answer("❌ Не найдена.", show_alert=True)
    ch, op, chp, opp, turn = res
    if callback.from_user.id != turn: conn.close(); return await callback.answer("❌ Не твой ход.", show_alert=True)
    dmg = random.randint(10, 25)
    if turn == ch: opp -= dmg; nturn = op
    else: chp -= dmg; nturn = ch
    if opp <= 0 or chp <= 0:
        c.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (did,)); conn.commit(); conn.close()
        win, lose = (ch, op) if opp <= 0 else (op, ch)
        update_stats(win, win=True); update_stats(lose, win=False); update_coins(win, 50)
        try:
            await bot.send_message(win, "🏆 Ты победил! +50 монет.")
            await bot.send_message(lose, "💀 Ты проиграл.")
        except: pass
        return await callback.message.edit_text("🏆 Дуэль окончена!")
    c.execute("UPDATE duels SET ch_hp = ?, op_hp = ?, turn_id = ? WHERE id = ?", (chp, opp, nturn, did)); conn.commit(); conn.close()
    await callback.message.edit_text(f"⚔️ Ты нанес {dmg} урона! Соперник: {max(0, opp if turn == ch else chp)} HP.")
    b = InlineKeyboardBuilder().row(InlineKeyboardButton(text="⚔️ Атаковать", callback_data=f"atk_{did}"))
    try: await bot.send_message(nturn, "⚔️ Твой ход:", reply_markup=b.as_markup())
    except: pass

# --- START ---
async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start(); await asyncio.sleep(5)
    print("🚀 Бот запущен!"); await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__": asyncio.run(main())
