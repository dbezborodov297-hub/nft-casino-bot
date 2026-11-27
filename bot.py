import asyncio, random, sqlite3, os, time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "9022493828:AAF7mGAL942aYO-m9DhtfzimuVCLIJXGZOI"
ADMIN_ID = 8907438590
BOT_USERNAME = "Darkgram20sk_bot"  # <--- ЗАМЕНИ НА ЮЗЕРНЕЙМ ТВОЕГО БОТА

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
    # Добавляем XP за оборот звёзд (получение или трата)
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
    """Добавляет XP и проверяет левелап"""
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ?", (uid,))
    level, xp = c.fetchone()
    
    xp += amount
    
    # Проверка левелапа (максимум 20 уровень)
    while level < 20:
        needed_xp = level * 5000  # Прогрессивная шкала
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

# --- КЛАВИАТУРА ---
def get_main_kb(uid):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus"))
    builder.row(InlineKeyboardButton(text="📦 Открыть кейс (5⭐)", callback_data="open_case"))
    builder.row(InlineKeyboardButton(text="🧊 Льдины (Игра)", callback_data="ice_game_menu"))
    builder.row(InlineKeyboardButton(text="👥 Пригласить друга", callback_data=f"ref_link_{uid}"))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except:
            pass

    user = get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if referrer_id and referrer_id != message.from_user.id:
        is_new_ref = set_referrer(message.from_user.id, referrer_id)
        if is_new_ref:
            update_coins(referrer_id, 5)
            try:
                # ИСПРАВЛЕНО: убран лишний </b>
                await bot.send_message(referrer_id, f"🎉 <b>Новый реферал!</b>\nПользователь {message.from_user.first_name} перешел по твоей ссылке.\n💰 +5 Звёзд на баланс!")
            except:
                pass
            await message.answer(f"👋 <b>Привет!</b>\nТы перешел по приглашению. Тебе начислен приветственный бонус!", parse_mode="HTML")
            update_coins(message.from_user.id, 5)

    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Забирай ежедневные бонусы, открывай кейсы и играй в Льдины!"
    )
    await message.answer(text, reply_markup=get_main_kb(message.from_user.id), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_data = get_or_create_user(callback.from_user.id)
    # (uid, coins, tokens, last_daily, ref_id, level, xp)
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
    await callback.message.edit_text(text, reply_markup=get_main_kb(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("ref_link_"))
async def send_ref_link(callback: types.CallbackQuery):
    uid = callback.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    text = (
        f"🔗 <b>ТВОЯ РЕФЕРАЛЬНАЯ ССЫЛКА</b>\n\n"
        f"Отправь эту ссылку друзьям:\n"
        f"<code>{link}</code>\n\n"
        f"💰 За каждого друга ты получишь <b>+5 Звёзд</b>!\n"
        f"🎁 Друг тоже получит бонус."
    )
    await callback.message.edit_text(text, reply_markup=get_main_kb(uid), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "daily_bonus")
async def claim_bonus(callback: types.CallbackQuery):
    user_data = get_or_create_user(callback.from_user.id)
    last_daily = user_data[3]
    current_time = time.time()
    cooldown = 12 * 60 * 60 
    
    time_passed = current_time - last_daily
    if time_passed < cooldown:
        time_left = int(cooldown - time_passed)
        hours = time_left // 3600
        minutes = (time_left % 3600) // 60
        return await callback.answer(f"⏳ Бонус через {hours} ч. {minutes} мин.", show_alert=True)
    
    reward = random.randint(5, 20)
    update_coins(callback.from_user.id, reward)
    update_last_daily(callback.from_user.id)
    
    await callback.message.edit_text(
        f"🎉 <b>БОНУС ПОЛУЧЕН!</b>\n⭐️ +{reward} Звёзд", 
        reply_markup=get_main_kb(callback.from_user.id), 
        parse_mode="HTML"
    )

# --- КЕЙС С АНИМАЦИЕЙ ---
CASE_ITEMS = [
    {"name": "+18 Звёзд", "chance": 5.8, "type": "coins", "val": 18},
    {"name": "+11 Звёзд", "chance": 9.8, "type": "coins", "val": 11},
    {"name": "+6 Звёзд",  "chance": 11.3, "type": "coins", "val": 6},
    {"name": "2 Токена",  "chance": 34.7, "type": "tokens", "val": 2},
    {"name": "Пусто...",   "chance": 38.4, "type": "none", "val": 0},
]

@dp.callback_query(lambda c: c.data == "open_case")
async def open_case_start(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user = get_or_create_user(uid)
    balance = user[1]
    
    if balance < 5:
        return await callback.answer("❌ Недостаточно звёзд! Нужно 5 ⭐", show_alert=True)
    
    update_coins(uid, -5)
    
    anim_texts = ["📦 Открываем кейс...", "📦 Крутим рулетку...", "📦 Ищем приз...", "✨ Почти готово..."]
    msg = await callback.message.edit_text("📦 Открываем кейс...")
    
    for txt in anim_texts:
        await asyncio.sleep(0.6)
        try:
            await msg.edit_text(txt)
        except:
            pass
            
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
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Ещё раз (5⭐)", callback_data="open_case"))
    b.row(InlineKeyboardButton(text="🔙 В меню", callback_data="profile"))
    
    await msg.edit_text(final_text, reply_markup=b.as_markup(), parse_mode="HTML")

# --- ИГРА "ЛЬДИНЫ" ---
ICE_DIFFICULTIES = {
    "easy": {"name": "🟢 Легко", "reward_min": 2, "reward_max": 5, "success_rate": 0.8, "fail_penalty": 0},
    "medium": {"name": "🟡 Средне", "reward_min": 5, "reward_max": 10, "success_rate": 0.6, "fail_penalty": 0},
    "hard": {"name": "🔴 Сложно", "reward_min": 10, "reward_max": 20, "success_rate": 0.4, "fail_penalty": 0},
}

@dp.callback_query(lambda c: c.data == "ice_game_menu")
async def ice_game_menu(callback: types.CallbackQuery):
    text = (
        f"🧊 <b>ИГРА: ЛЬДИНЫ</b>\n\n"
        f"Прыгай по льдинам и собирай награды!\n"
        f"Чем сложнее уровень, тем больше приз.\n"
        f"Но будь осторожен — можно упасть в воду!\n\n"
        f"Выбери сложность:"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🟢 Легко (2-5⭐)", callback_data="ice_start_easy"))
    b.row(InlineKeyboardButton(text="🟡 Средне (5-10⭐)", callback_data="ice_start_medium"))
    b.row(InlineKeyboardButton(text="🔴 Сложно (10-20⭐)", callback_data="ice_start_hard"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("ice_start_"))
async def ice_start(callback: types.CallbackQuery, state: FSMContext):
    diff = callback.data.replace("ice_start_", "")
    if diff not in ICE_DIFFICULTIES:
        return await callback.answer("❌ Неверная сложность", show_alert=True)
    
    await state.update_data(difficulty=diff, current_reward=0, jumps=0)
    await state.set_state(St.playing_ice)
    
    diff_data = ICE_DIFFICULTIES[diff]
    text = (
        f"🧊 <b>НАЧАЛО ИГРЫ</b>\n\n"
        f"Сложность: {diff_data['name']}\n"
        f"Шанс успеха: {int(diff_data['success_rate'] * 100)}%\n\n"
        f"Ты стоишь на первой льдине.\n"
        f"Нажми «Прыгнуть», чтобы продолжить!"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🦘 Прыгнуть", callback_data="ice_jump"))
    b.row(InlineKeyboardButton(text="🏁 Забрать приз", callback_data="ice_take"))
    b.row(InlineKeyboardButton(text="🏳️ Выйти", callback_data="ice_quit"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "ice_jump", St.playing_ice)
async def ice_jump(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    diff = data['difficulty']
    diff_data = ICE_DIFFICULTIES[diff]
    current_reward = data['current_reward']
    jumps = data['jumps']
    
    # Проверка успеха
    if random.random() < diff_data['success_rate']:
        # Успех! Добавляем награду
        reward = random.randint(diff_data['reward_min'], diff_data['reward_max'])
        current_reward += reward
        jumps += 1
        
        await state.update_data(current_reward=current_reward, jumps=jumps)
        
        text = (
            f"✅ <b>УСПЕХ!</b>\n\n"
            f"Ты успешно прыгнул на следующую льдину!\n"
            f"🎁 Текущий приз: <b>+{current_reward} ⭐</b>\n"
            f"🦘 Прыжков: {jumps}\n\n"
            f"Продолжить или забрать приз?"
        )
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🦘 Прыгнуть", callback_data="ice_jump"))
        b.row(InlineKeyboardButton(text="🏁 Забрать приз", callback_data="ice_take"))
        b.row(InlineKeyboardButton(text="🏳️ Выйти", callback_data="ice_quit"))
        await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")
    else:
        # Провал!
        await state.clear()
        text = (
            f"💦 <b>ПРОВАЛ!</b>\n\n"
            f"Ты упал в воду...\n"
            f"Приз потерян: {current_reward} ⭐\n\n"
            f"Попробуй еще раз!"
        )
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔙 В меню", callback_data="ice_game_menu"))
        b.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
        await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "ice_take", St.playing_ice)
async def ice_take(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    reward = data['current_reward']
    jumps = data['jumps']
    
    if reward > 0:
        update_coins(callback.from_user.id, reward)
        text = (
            f"🏆 <b>ПОБЕДА!</b>\n\n"
            f"Ты успешно завершил игру!\n"
            f"🎁 Приз: <b>+{reward} ⭐</b>\n"
            f"🦘 Прыжков: {jumps}"
        )
    else:
        text = "😔 Ты не успел собрать награду."
    
    await state.clear()
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Играть снова", callback_data="ice_game_menu"))
    b.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    await callback.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "ice_quit", St.playing_ice)
async def ice_quit(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏳️ Ты вышел из игры.", reply_markup=get_main_kb(callback.from_user.id))

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
