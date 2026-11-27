import asyncio, random, sqlite3, os, time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "9022493828:AAEGVlX0QZRhuZwDm6HcihFLG3Q5lDWalDo"
ADMIN_ID = 8907438590
BOT_USERNAME = "Darkgram20sk_bot" # ЗАМЕНИ НА ЮЗЕРНЕЙМ ТВОЕГО БОТА

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class St(StatesGroup):
    playing_ice = State()

# --- FLASK ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        first_name TEXT, 
        coins INTEGER DEFAULT 0,
        tokens INTEGER DEFAULT 0,
        last_daily REAL DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0
    )''')
    try:
        c.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
        c.execute("ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit(); conn.close()

def get_or_create_user(uid, un=None, fn=None):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT user_id, coins, tokens, last_daily, referrer_id, level, xp FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (uid, un, fn))
        conn.commit()
        res = (uid, 0, 0, 0, 0, 1, 0)
    elif un or fn:
        c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (un, fn, uid))
        conn.commit()
    conn.close()
    return res

def update_coins(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, uid))
    c.execute("UPDATE users SET coins = 0 WHERE coins < 0 AND user_id = ?", (uid,))
    if amount > 0:
        add_xp(uid, amount)
    conn.commit(); conn.close()

def update_tokens(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, uid))
    conn.commit(); conn.close()

def update_last_daily(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (time.time(), uid))
    conn.commit(); conn.close()

def add_xp(uid, amount):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ?", (uid,))
    level, xp = c.fetchone()
    xp += amount
    while level < 20:
        needed_xp = level * 5000
        if xp >= needed_xp:
            xp -= needed_xp
            level += 1
        else:
            break
    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ?", (level, xp, uid))
    conn.commit(); conn.close()
    return level

def set_referrer(uid, ref_uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (uid,))
    current_ref = c.fetchone()[0]
    if current_ref == 0 and uid != ref_uid:
        c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref_uid, uid))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_all_users():
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def get_top_coins(limit=10):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT username, first_name, coins FROM users ORDER BY coins DESC LIMIT ?", (limit,))
    top = c.fetchall()
    conn.close()
    return top

# --- КОМАНДЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    init_db()
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except:
            pass

    get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if referrer_id and referrer_id != message.from_user.id:
        is_new_ref = set_referrer(message.from_user.id, referrer_id)
        if is_new_ref:
            update_coins(referrer_id, 5)
            try:
                await bot.send_message(referrer_id, 
                    f"🎉 <b>Новый реферал!</b>\n"
                    f"Пользователь {message.from_user.first_name} перешел по твоей ссылке.\n"
                    f"💰 +5 Звёзд на баланс!")
            except:
                pass
            await message.answer(f"👋 <b>Привет!</b>\nТы перешел по приглашению. Тебе начислен приветственный бонус!", parse_mode="HTML")
            update_coins(message.from_user.id, 5)

    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"<b>Команды бота:</b>\n"
        f"/profile - Твой профиль\n"
        f"/bonus - Ежедневный бонус\n"
        f"/case - Открыть кейс (5⭐)\n"
        f"/ice - Игра Льдины\n"
        f"/top - Таблица лидеров\n"
        f"/ref - Твоя реферальная ссылка"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    await state.clear()
    user_data = get_or_create_user(message.from_user.id)
    coins = user_data[1]
    tokens = user_data[2]
    level = user_data[5]
    xp = user_data[6]
    
    needed_xp = level * 5000 if level < 20 else 0
    progress = int((xp / needed_xp) * 10) if needed_xp > 0 else 10
    bar = "█" * progress + "░" * (10 - progress)
    
    text = (
        f"👤 <b>ТВОЙ ПРОФИЛЬ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 <b>Уровень:</b> {level}/20\n"
        f"✨ <b>XP:</b> {xp}/{needed_xp if needed_xp > 0 else 'MAX'}\n"
        f"[{bar}]\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ <b>Звёзды:</b> {coins}\n"
        f"🪙 <b>Токены:</b> {tokens}\n"
        f"━━━━━━━━━━━━━━"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("bonus"))
async def cmd_bonus(message: types.Message, state: FSMContext):
    await state.clear()
    user_data = get_or_create_user(message.from_user.id)
    last_daily = user_data[3]
    current_time = time.time()
    cooldown = 12 * 60 * 60 
    
    time_passed = current_time - last_daily
    if time_passed < cooldown:
        time_left = int(cooldown - time_passed)
        hours = time_left // 3600
        minutes = (time_left % 3600) // 60
        return await message.answer(f"⏳ Бонус будет доступен через {hours} ч. {minutes} мин.")
    
    reward = random.randint(5, 20)
    update_coins(message.from_user.id, reward)
    update_last_daily(message.from_user.id)
    
    await message.answer(
        f"🎉 <b>БОНУС ПОЛУЧЕН!</b>\n⭐️ +{reward} Звёзд", 
        parse_mode="HTML"
    )

@dp.message(Command("case"))
async def cmd_case(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    user = get_or_create_user(uid)
    balance = user[1]
    
    if balance < 5:
        return await message.answer("❌ Недостаточно звёзд! Нужно 5 ⭐")
    
    update_coins(uid, -5)
    
    await message.answer("📦 Открываем кейс...")
    await asyncio.sleep(0.6)
    await message.answer("📦 Крутим рулетку...")
    await asyncio.sleep(0.6)
    await message.answer("📦 Ищем приз...")
    await asyncio.sleep(0.6)
    await message.answer("✨ Почти готово...")
    await asyncio.sleep(0.6)
    
    CASE_ITEMS = [
        {"name": "+18 Звёзд", "chance": 5.8, "type": "coins", "val": 18},
        {"name": "+11 Звёзд", "chance": 9.8, "type": "coins", "val": 11},
        {"name": "+6 Звёзд",  "chance": 11.3, "type": "coins", "val": 6},
        {"name": "2 Токена",  "chance": 34.7, "type": "tokens", "val": 2},
        {"name": "Пусто...",   "chance": 38.4, "type": "none", "val": 0},
    ]
    
    rand = random.uniform(0, 100)
    cumulative = 0
    prize = CASE_ITEMS[-1]
    
    for item in CASE_ITEMS:
        cumulative += item['chance']
        if rand <= cumulative:
            prize = item
            break
    
    win_text = ""
    if prize['type'] == 'coins':
        update_coins(uid, prize['val'])
        win_text = f"⭐️ +{prize['val']} Звёзд"
    elif prize['type'] == 'tokens':
        update_tokens(uid, prize['val'])
        win_text = f"🪙 +{prize['val']} Токена"
    else:
        win_text = "😔 Ничего..."

    final_text = (
        f"🎰 <b>РЕЗУЛЬТАТ ОТКРЫТИЯ</b>\n\n"
        f"Тебе выпало:\n"
        f"🎁 <b>{prize['name']}</b>\n\n"
        f"{win_text}"
    )
    
    await message.answer(final_text, parse_mode="HTML")

@dp.message(Command("ice"))
async def cmd_ice(message: types.Message, state: FSMContext):
    await state.clear()
    user = get_or_create_user(message.from_user.id)
    balance = user[1]
    
    text = (
        f"🧊 <b>ИГРА: ЛЬДИНЫ</b>\n\n"
        f"💰 Твой баланс: <b>{balance} ⭐</b>\n\n"
        f"<b>Как играть:</b>\n"
        f"/ice easy - Легко (x0.5, 80% успеха)\n"
        f"/ice medium - Средне (x1.0, 60% успеха)\n"
        f"/ice hard - Сложно (x2.0, 40% успеха)\n\n"
        f"<b>Пример:</b> /ice hard 3\n"
        f"Это значит: сложная игра со ставкой 3⭐"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ice"))
async def cmd_ice_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    
    if len(args) < 2:
        return await message.answer("❌ Укажи сложность: /ice easy|medium|hard [ставка]")
    
    diff = args[1].lower()
    if diff not in ["easy", "medium", "hard"]:
        return await message.answer("❌ Неверная сложность. Используй: easy, medium или hard")
    
    bet = 1
    if len(args) > 2:
        try:
            bet = int(args[2])
            if bet < 1 or bet > 5:
                return await message.answer("❌ Ставка должна быть от 1 до 5")
        except:
            return await message.answer("❌ Неверная ставка")
    
    user = get_or_create_user(message.from_user.id)
    balance = user[1]
    
    if balance < bet:
        return await message.answer(f"❌ Недостаточно звёзд! Нужно {bet} ⭐")
    
    ICE_DIFFICULTIES = {
        "easy": {"name": "🟢 Легко", "reward_mult": 0.5, "success_rate": 0.8},
        "medium": {"name": "🟡 Средне", "reward_mult": 1.0, "success_rate": 0.6},
        "hard": {"name": "🔴 Сложно", "reward_mult": 2.0, "success_rate": 0.4},
    }
    
    update_coins(message.from_user.id, -bet)
    
    await state.update_data(difficulty=diff, bet=bet, current_reward=0, jumps=0)
    await state.set_state(St.playing_ice)
    
    diff_data = ICE_DIFFICULTIES[diff]
    text = (
        f"🧊 <b>НАЧАЛО ИГРЫ</b>\n\n"
        f"Сложность: {diff_data['name']}\n"
        f"💰 Ставка: <b>{bet} ⭐</b>\n"
        f"🎯 Шанс успеха: <b>{int(diff_data['success_rate'] * 100)}%</b>\n\n"
        f"<b>Команды:</b>\n"
        f"/jump - Прыгнуть на следующую льдину\n"
        f"/take - Забрать текущий приз\n"
        f"/quit - Сдаться (потерять ставку)"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != St.playing_ice:
        return await message.answer("❌ Ты не в игре. Используй /ice")
    
    data = await state.get_data()
    diff = data['difficulty']
    bet = data['bet']
    current_reward = data['current_reward']
    jumps = data['jumps']
    
    ICE_DIFFICULTIES = {
        "easy": {"name": "🟢 Легко", "reward_mult": 0.5, "success_rate": 0.8},
        "medium": {"name": "🟡 Средне", "reward_mult": 1.0, "success_rate": 0.6},
        "hard": {"name": "🔴 Сложно", "reward_mult": 2.0, "success_rate": 0.4},
    }
    
    diff_data = ICE_DIFFICULTIES[diff]
    
    if random.random() < diff_data['success_rate']:
        reward_this_jump = max(1, int(bet * diff_data['reward_mult']))
        current_reward += reward_this_jump
        jumps += 1
        
        await state.update_data(current_reward=current_reward, jumps=jumps)
        
        text = (
            f"✅ <b>УСПЕХ!</b>\n\n"
            f"Ты прыгнул на следующую льдину!\n"
            f"💎 +{reward_this_jump} ⭐ к призу\n"
            f"🎁 Текущий приз: <b>{current_reward} ⭐</b>\n"
            f"🦘 Прыжков: {jumps}\n\n"
            f"/jump - Прыгнуть ещё\n"
            f"/take - Забрать приз\n"
            f"/quit - Сдаться"
        )
        await message.answer(text, parse_mode="HTML")
    else:
        await state.clear()
        text = (
            f"💦 <b>ПРОВАЛ!</b>\n\n"
            f"Ты упал в воду...\n"
            f"💸 Ставка <b>{bet} ⭐</b> потеряна.\n\n"
            f"Попробуй ещё раз: /ice"
        )
        await message.answer(text, parse_mode="HTML")

@dp.message(Command("take"))
async def cmd_take(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != St.playing_ice:
        return await message.answer("❌ Ты не в игре. Используй /ice")
    
    data = await state.get_data()
    reward = data['current_reward']
    jumps = data['jumps']
    bet = data['bet']
    
    await state.clear()
    
    if reward > 0:
        update_coins(message.from_user.id, reward)
        profit = reward - bet
        profit_str = f"+{profit}" if profit >= 0 else str(profit)
        text = (
            f"🏆 <b>ПОБЕДА!</b>\n\n"
            f"🎁 Выигрыш: <b>{reward} ⭐</b>\n"
            f"💰 Ставка была: {bet} ⭐\n"
            f"📈 Итого: <b>{profit_str} ⭐</b>\n"
            f"🦘 Прыжков: {jumps}"
        )
    else:
        text = (
            f"😔 Ты забрал 0⭐\n"
            f"💸 Ставка {bet} ⭐ потеряна."
        )
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("quit"))
async def cmd_quit(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != St.playing_ice:
        return await message.answer("❌ Ты не в игре.")
    
    data = await state.get_data()
    bet = data.get('bet', 0)
    await state.clear()
    
    text = (
        f"🏳️ <b>ТЫ СДАЛСЯ</b>\n\n"
        f"💸 Ставка <b>{bet} ⭐</b> потеряна.\n\n"
        f"В следующий раз будь смелее!"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: types.Message, state: FSMContext):
    await state.clear()
    top = get_top_coins(10)
    
    if not top:
        return await message.answer("Пока нет игроков.")
    
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ ПО ЗВЁЗДАМ</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (un, fn, coins) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"<b>{i}.</b>"
        name = f"@{un}" if un else (fn if fn else "Игрок")
        text += f"{medal} {name} — <b>{coins} ⭐</b>\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ref"))
async def cmd_ref(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    text = (
        f"🔗 <b>ТВОЯ РЕФЕРАЛЬНАЯ ССЫЛКА</b>\n\n"
        f"Отправь эту ссылку друзьям:\n"
        f"<code>{link}</code>\n\n"
        f"💰 За каждого друга ты получишь <b>+5 Звёзд</b>!\n"
        f"🎁 Друг тоже получит бонус."
    )
    await message.answer(text, parse_mode="HTML")

# --- РАССЫЛКА ДЛЯ АДМИНА ---
@dp.message(Command("send"), lambda msg: msg.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message):
    content_type = message.content_type
    if content_type == 'text':
        text_to_send = message.text.replace("/send", "").strip()
    elif content_type in ['photo', 'video']:
        text_to_send = message.caption if message.caption else ""
    else:
        return await message.reply("❌ Только текст или фото/видео.")

    users = get_all_users()
    status_msg = await message.reply(f"🚀 Рассылка для {len(users)} пользователей...")
    
    success = 0
    for uid in users:
        try:
            if content_type == 'text':
                await bot.send_message(uid, text_to_send, parse_mode="HTML")
            elif content_type == 'photo':
                await bot.send_photo(uid, message.photo[-1].file_id, caption=text_to_send, parse_mode="HTML")
            elif content_type == 'video':
                await bot.send_video(uid, message.video.file_id, caption=text_to_send, parse_mode="HTML")
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
        
    await status_msg.edit_text(f"✅ Готово! Доставлено: {success}/{len(users)}")

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
