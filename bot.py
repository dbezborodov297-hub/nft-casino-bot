import asyncio
import random
import sqlite3
import time
import os
import threading
import uuid
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = "9184406467:AAEUtA1w5ibpUdN28uVeayBF-MJ4lSqNF3s"
ADMIN_ID = 8907438590

# Твой юзернейм для связи по выводам
SUPPORT_USERNAME = "@твой_ник" 

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {
    "🚀 Ракета": {"price": 50, "income": 5},
    "💎 Алмаз": {"price": 100, "income": 10},
    "🗽 Статуя Свободы": {"price": 1200, "income": 50},
    "🕶️ Очки": {"price": 2300, "income": 100}
}
DAILY_BONUS = 50
REFERRAL_REWARD = 0.5 # 0.5 алмаза за реферала
STARS_GOAL = 150 # Нужно алмазов
STARS_REWARD = 1500 # Сколько звезд даем

class AdminStates(StatesGroup):
    waiting_give_coins = State()
    waiting_take_coins = State()
    waiting_broadcast = State()
    waiting_partner_name = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    # Добавили поле referrer_id и diamonds
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY, 
                 balance INTEGER DEFAULT 1000, 
                 last_bonus INTEGER DEFAULT 0,
                 referrer_id INTEGER DEFAULT NULL,
                 diamonds REAL DEFAULT 0.0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS partners (id TEXT PRIMARY KEY, owner_id INTEGER, bot_name TEXT, api_key TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount_diamonds REAL, stars INTEGER)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus, referrer_id, diamonds FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        res = (1000, 0, None, 0.0)
    conn.close()
    return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_diamonds(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return [item[0] for item in items]

def calculate_passive_income(user_id):
    items = get_inventory(user_id)
    total = 0
    for name in items:
        if name in SHOP_ITEMS:
            total += SHOP_ITEMS[name]["income"]
    return total

# --- КЛАВИАТУРЫ ---
def main_menu(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino"))
    builder.row(
        InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop"), 
        InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory")
    )
    builder.row(
        InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard"), 
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"),
        InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="ref_menu")
    )
    builder.row(InlineKeyboardButton(text="🤝 ПАРТНЁРСКИЙ БОТ", callback_data="partner_menu"))
    
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin_panel"))
    return builder.as_markup()

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(message: types.Message, command: Command):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # Обработка реферальной ссылки
    if command.args and not user[2]: # Если есть аргумент и у юзера еще нет реферера
        try:
            referrer_id = int(command.args)
            if referrer_id != user_id:
                conn = sqlite3.connect('game.db')
                c = conn.cursor()
                c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                # Начисляем алмаз рефереру
                c.execute("UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?", (REFERRAL_REWARD, referrer_id))
                conn.commit()
                conn.close()
                try: await bot.send_message(referrer_id, f"🎉 По твоей ссылке зашел новый реферал! +{REFERRAL_REWARD} 💎")
                except: pass
        except ValueError:
            pass

    await message.answer("🌟 <b>Добро пожаловать в NFT КАЗИНО!</b>\n\nТвой баланс: 1000 монет.", reply_markup=main_menu(user_id), parse_mode="HTML")

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    bal, _, _, diamonds = user
    items = get_inventory(callback.from_user.id)
    income = calculate_passive_income(callback.from_user.id)
    user_link = f"<a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a>"
    text = (f"👤 <b>ПРОФИЛЬ</b>\n\n🆔 Игрок: {user_link}\n💰 Баланс: <b>{bal}</b>\n"
            f"💎 Алмазы: <b>{diamonds}</b>\n🎒 NFT: <b>{len(items)}</b>\n📈 Доход: <b>+{income}</b>")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- РЕФЕРАЛЬНЫЙ КАБИНЕТ ---
@dp.callback_query(F.data == "ref_menu")
async def cb_ref_menu(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    diamonds = user[3]
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    
    text = (f"👥 <b>РЕФЕРАЛЬНЫЙ КАБИНЕТ</b>\n\n"
            f"💎 Твои алмазы: <b>{diamonds}</b>\n"
            f"🎯 Цель: набрать <b>{STARS_GOAL} 💎</b> для вывода <b>{STARS_REWARD} ⭐</b>\n\n"
            f"За каждого приглашенного друга ты получаешь <b>+{REFERRAL_REWARD} 💎</b>.\n\n"
            f"🔗 Твоя ссылка:\n<code>{ref_link}</code>")
            
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Вывести звезды", callback_data="ref_withdraw"))
    builder.row(InlineKeyboardButton(text="🔒 Конфиденциальность", callback_data="privacy"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "ref_withdraw")
async def cb_ref_withdraw(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    diamonds = user[3]
    
    if diamonds < STARS_GOAL:
        await callback.answer(f"❌ Недостаточно алмазов! Нужно {STARS_GOAL} 💎, у тебя {diamonds} 💎", show_alert=True)
        return
        
    # Создаем заявку
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    # Списываем алмазы
    c.execute("UPDATE users SET diamonds = diamonds - ? WHERE user_id = ?", (STARS_GOAL, callback.from_user.id))
    # Записываем заявку
    c.execute("INSERT INTO withdraw_requests (user_id, amount_diamonds, stars) VALUES (?, ?, ?)", (callback.from_user.id, STARS_GOAL, STARS_REWARD))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"✅ <b>Заявка на вывод создана!</b>\n\n"
        f"Списано: {STARS_GOAL} 💎\n"
        f"К выводу: {STARS_REWARD} ⭐\n\n"
        f"Заявка отправлена администрации. Ожидай перевода звезд на аккаунт.", 
        reply_markup=main_menu(callback.from_user.id), parse_mode="HTML"
    )
    # Уведомляем админа
    try:
        await bot.send_message(ADMIN_ID, f"💰 Новая заявка на вывод!\nЮзер: {callback.from_user.id}\nЗвезды: {STARS_REWARD} ⭐\n\nПроверь в админке.")
    except: pass

@dp.callback_query(F.data == "privacy")
async def cb_privacy(callback: types.CallbackQuery):
    text = (f"🔒 <b>КОНФИДЕНЦИАЛЬНОСТЬ</b>\n\n"
            f"1. Мы не собираем твои личные данные (номера телефонов, адреса).\n"
            f"2. Твой Telegram ID используется только для синхронизации баланса.\n"
            f"3. Алмазы и средства нельзя передать другому пользователю.\n"
            f"4. По всем вопросам вывода пиши: {SUPPORT_USERNAME}")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="ref_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ОСТАЛЬНЫЕ ХЭНДЛЕРЫ (Магазин, Казино, Бонус) ---
@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    now = int(time.time())
    if now - user[1] < 86400:
        left = 86400 - (now - user[1])
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True); return
    total = DAILY_BONUS + calculate_passive_income(callback.from_user.id)
    update_balance(callback.from_user.id, total)
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now, callback.from_user.id))
    conn.commit(); conn.close()
    await callback.answer(f"🎉 Получено {total} монет!", show_alert=True)

@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН NFT</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, data in SHOP_ITEMS.items():
        text += f"{name} — <b>{data['price']}</b>\n└ Доход: +{data['income']}\n\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    if item in SHOP_ITEMS:
        bal = get_user(callback.from_user.id)[0]
        if bal < SHOP_ITEMS[item]["price"]:
            await callback.answer("❌ Не хватает монет!", show_alert=True); return
        update_balance(callback.from_user.id, -SHOP_ITEMS[item]["price"])
        conn = sqlite3.connect('game.db'); c = conn.cursor()
        c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item))
        conn.commit(); conn.close()
        await callback.answer(f"✅ Куплено!", show_alert=True)

@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    text = "🎒 <b>ИНВЕНТАРЬ</b>\n\n" + ("Пусто." if not items else "\n".join(f"• {name}" for name in items))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall(); conn.close()
    text = "🏆 <b>ТОП-10</b>\n\n"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} Игрок {uid} — <b>{bal}</b>\n"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"))
    builder.row(InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_"))
async def cb_game(callback: types.CallbackQuery):
    game = callback.data.split("_")[1]
    if get_user(callback.from_user.id)[0] < 100:
        await callback.answer("❌ Не хватает монет!", show_alert=True); return
    if game == "coin":
        if random.choice([True, False]): update_balance(callback.from_user.id, 100); res = "🪙 ОРЕЛ! +100"
        else: update_balance(callback.from_user.id, -100); res = "🪙 РЕШКА. -100"
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(callback.from_user.id, 100); res = f"🎲 {u} vs {b}. Победа! +100"
        elif u < b: update_balance(callback.from_user.id, -100); res = f"🎲 {u} vs {b}. Поражение. -100"
        else: res = f"🎲 {u} vs {b}. Ничья."
    await callback.message.edit_text(f"{res}\n\n💰 Баланс: <b>{get_user(callback.from_user.id)[0]}</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")

# --- ПАРТНЁРСКИЕ БОТЫ ---
@dp.callback_query(F.data == "partner_menu")
async def cb_partner_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать бота", callback_data="create_partner"))
    builder.row(InlineKeyboardButton(text="🤖 Мои боты", callback_data="my_partners"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text("🤝 <b>ПАРТНЁРКА</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "create_partner")
async def cb_create_partner(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи название для бота:")
    await state.set_state(AdminStates.waiting_partner_name)

@dp.message(AdminStates.waiting_partner_name)
async def process_partner_name(message: types.Message, state: FSMContext):
    api_key = str(uuid.uuid4())
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("INSERT INTO partners (id, owner_id, bot_name, api_key) VALUES (?, ?, ?, ?)", 
              (f"bot_{random.randint(1000, 9999)}", message.from_user.id, message.text.strip(), api_key))
    conn.commit(); conn.close()
    await message.answer(f"✅ Бот создан!\n\n🔑 API: <code>{api_key}</code>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True); return
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); users_count = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users"); total_money = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM withdraw_requests"); withdraws = c.fetchone()[0]
    conn.close()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"💸 Заявки на вывод ({withdraws})", callback_data="adm_withdraws"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    builder.row(InlineKeyboardButton(text="💸 Выдать монеты", callback_data="adm_give"))
    builder.row(InlineKeyboardButton(text="📉 Забрать монеты", callback_data="adm_take"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    
    text = f"⚙️ <b>АДМИНКА</b>\n\n👥 Игроков: <b>{users_count}</b>\n💰 Монет: <b>{total_money}</b>"
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_withdraws")
async def adm_withdraws(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT id, user_id, stars FROM withdraw_requests")
    reqs = c.fetchall(); conn.close()
    if not reqs:
        await callback.answer("Нет активных заявок.", show_alert=True); return
        
    text = "💸 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n"
    for rid, uid, stars in reqs:
        text += f"ID заявки: {rid}\nЮзер: {uid}\nЗвезды: {stars} ⭐\n\n"
    
    text += "<i>Выдай звезды вручную через @PremiumBot и удали заявку командой ниже.</i>"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🗑 Удалить все заявки", callback_data="adm_clear_withdraws"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_panel"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_clear_withdraws")
async def adm_clear_withdraws(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("DELETE FROM withdraw_requests")
    conn.commit(); conn.close()
    await callback.answer("✅ Все заявки удалены (звезды выданы).", show_alert=True)
    await admin_panel(callback)

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💸 Введи <b>ID</b> и <b>сумму</b> через пробел:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_give_coins)

@dp.message(AdminStates.waiting_give_coins)
async def process_give(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amount = message.text.split()
        update_balance(int(uid), int(amount))
        await message.answer(f"✅ Выдано {amount} монет пользователю {uid}.", reply_markup=main_menu(message.from_user.id))
    except: await message.answer("❌ Ошибка формата.")
    await state.clear()

@dp.callback_query(F.data == "adm_take")
async def adm_take(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📉 Введи <b>ID</b> и <b>сумму</b> для списания:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_take_coins)

@dp.message(AdminStates.waiting_take_coins)
async def process_take(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amount = message.text.split()
        update_balance(int(uid), -int(amount))
        await message.answer(f"✅ Списано {amount} монет у {uid}.", reply_markup=main_menu(message.from_user.id))
    except: await message.answer("❌ Ошибка формата.")
    await state.clear()

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введи текст рассылки:")
    await state.set_state(AdminStates.waiting_broadcast)

@dp.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('game.db'); c = conn.cursor()
    c.execute("SELECT user_id FROM users"); users = c.fetchall(); conn.close()
    count = 0
    for (uid,) in users:
        try: await bot.send_message(uid, f"📢 <b>Сообщение:</b>\n\n{message.text}", parse_mode="HTML"); count += 1; await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {count}", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ЗАГЛУШКА ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is running", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
