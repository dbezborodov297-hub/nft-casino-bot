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
BOT_TOKEN = "9022493828:AAFDZ03KgRXYmiIGOd7BytjqJua-R8eYH08"
ADMIN_ID = 8907438590 # ID админа для рассылки

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Состояние для хранения данных рассылки (если нужно будет расширить)
class St(StatesGroup):
    waiting_for_broadcast = State()

# --- FLASK (Для поддержки активности на хостинге) ---
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    # Упрощенная таблица: только профиль и время последнего бонуса
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        first_name TEXT, 
        coins INTEGER DEFAULT 0,
        last_daily REAL DEFAULT 0
    )''')
    
    # Проверка наличия колонок для старых баз
    try:
        c.execute("ALTER TABLE users ADD COLUMN last_daily REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def get_or_create_user(uid, un=None, fn=None):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, coins, last_daily FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    
    if not res:
        c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (uid, un, fn))
        conn.commit()
        res = (uid, 0, 0)
    elif un or fn:
        # Обновляем имя, если оно изменилось
        c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (un, fn, uid))
        conn.commit()
        
    conn.close()
    return res

def update_coins(uid, amount):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, uid))
    conn.commit()
    conn.close()

def update_last_daily(uid):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (time.time(), uid))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

# --- КЛАВИАТУРА ---
def get_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Получить бонус", callback_data="daily_bonus"))
    builder.row(InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile"))
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Это бот-копилка. Забирай ежедневные бонусы и копи звёзды ⭐️.\n"
        f"Бонус доступен каждые 12 часов."
    )
    await message.answer(text, reply_markup=get_main_kb(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_data = get_or_create_user(callback.from_user.id)
    # user_data = (user_id, coins, last_daily)
    coins = user_data[1]
    
    text = (
        f"👤 <b>ТВОЙ ПРОФИЛЬ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐️ <b>Баланс:</b> {coins}\n"
        f"━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=get_main_kb(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "daily_bonus")
async def claim_bonus(callback: types.CallbackQuery):
    user_data = get_or_create_user(callback.from_user.id)
    last_daily = user_data[2]
    current_time = time.time()
    cooldown = 12 * 60 * 60  # 12 часов
    
    time_passed = current_time - last_daily
    
    if time_passed < cooldown:
        time_left = int(cooldown - time_passed)
        hours = time_left // 3600
        minutes = (time_left % 3600) // 60
        return await callback.answer(f"⏳ Бонус будет доступен через {hours} ч. {minutes} мин.", show_alert=True)
    
    # Выдача награды
    reward = random.randint(5, 20)
    update_coins(callback.from_user.id, reward)
    update_last_daily(callback.from_user.id)
    
    text = (
        f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
        f"Ты получил ежедневный бонус:\n"
        f"⭐️ <b>+{reward} Звёзд</b>\n\n"
        f"Приходи снова через 12 часов!"
    )
    await callback.message.edit_text(text, reply_markup=get_main_kb(), parse_mode="HTML")

# --- РАССЫЛКА ДЛЯ АДМИНА ---

@dp.message(Command("send"), lambda msg: msg.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message):
    # Проверяем, есть ли текст или фото/видео
    content_type = message.content_type
    
    if content_type == 'text':
        text_to_send = message.text.replace("/send", "").strip()
        if not text_to_send:
            return await message.reply("❌ Введите текст после команды /send")
    elif content_type in ['photo', 'video', 'document', 'sticker']:
        text_to_send = message.caption if message.caption else ""
    else:
        return await message.reply("❌ Поддерживается только текст, фото или видео.")

    users = get_all_users()
    total = len(users)
    
    if total == 0:
        return await message.reply("❌ В базе нет пользователей.")
        
    status_msg = await message.reply(f"🚀 Начинаю рассылку для {total} пользователей...")
    
    success = 0
    failed = 0
    
    for uid in users:
        try:
            if content_type == 'text':
                await bot.send_message(uid, text_to_send, parse_mode="HTML")
            elif content_type == 'photo':
                await bot.send_photo(uid, message.photo[-1].file_id, caption=text_to_send, parse_mode="HTML")
            elif content_type == 'video':
                await bot.send_video(uid, message.video.file_id, caption=text_to_send, parse_mode="HTML")
            elif content_type == 'document':
                await bot.send_document(uid, message.document.file_id, caption=text_to_send, parse_mode="HTML")
            elif content_type == 'sticker':
                await bot.send_sticker(uid, message.sticker.file_id)
            
            success += 1
        except Exception as e:
            failed += 1
            # Можно раскомментировать для отладки
            # print(f"Error sending to {uid}: {e}")
        
        # Небольшая задержка, чтобы не спамить API слишком быстро
        await asyncio.sleep(0.05)
        
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"📩 Доставлено: {success}\n"
        f"❌ Ошибок: {failed}"
    )

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем Flask в отдельном потоке
    Thread(target=run_flask, daemon=True).start()
    
    print("🚀 Бот запущен! Ожидаю сообщений...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
