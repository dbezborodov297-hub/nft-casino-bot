import asyncio
import random
import sqlite3
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ButtonStyle # Импортируем стили для кнопок

BOT_TOKEN = "9020652959:AAGGcPweccJehB-r2169P0QoKD_j-1z9K1I"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "🗽 Статуя Свободы": 1200}
DAILY_BONUS = 50

class GameStates(StatesGroup):
    waiting_for_bet = State()
    minefield_bet = State()
    minefield_play = State()
    selling_price = State()
    offer_amount = State()

# --- БД (добавил поле market_earnings для учета заработка на рынке) ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER, market_earnings INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_name TEXT, price INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY AUTOINCREMENT, market_id INTEGER, buyer_id INTEGER, amount INTEGER)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus, market_earnings FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance, last_bonus, market_earnings) VALUES (?, 1000, 0, 0)", (user_id,))
        conn.commit()
        res = (1000, 0, 0)
    conn.close()
    return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_market_earnings(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET market_earnings = market_earnings + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_bonus_time(user_id, timestamp):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT id, item_name FROM inventory WHERE user_id = ?", (user_id,))
    items = c.fetchall()
    conn.close()
    return items

def buy_item(user_id, item_name, price):
    bal, _, _ = get_user(user_id)
    if bal < price: return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit()
    conn.close()
    return True

# --- Клавиатуры (ТЕПЕРЬ С ЦВЕТАМИ) ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino", style=ButtonStyle.PRIMARY))
    builder.row(
        InlineKeyboardButton(text="🛒 МАГАЗИН", callback_data="shop", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="🎒 ИНВЕНТАРЬ", callback_data="inventory", style=ButtonStyle.SUCCESS)
    )
    builder.row(
        InlineKeyboardButton(text="🏆 ТОП", callback_data="leaderboard", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile", style=ButtonStyle.SUCCESS)
    )
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily", style=ButtonStyle.SUCCESS))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin", style=ButtonStyle.PRIMARY),
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice", style=ButtonStyle.PRIMARY)
    )
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС", callback_data="game_darts", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mine", style=ButtonStyle.DANGER))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    return builder.as_markup()

def market_menu():
    builder = InlineKeyboardBuilder()
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT id, seller_id, item_name, price FROM market")
    lots = c.fetchall()
    conn.close()
    
    if not lots:
        builder.row(InlineKeyboardButton(text="😕 Рынок пуст", callback_data="noop", style=ButtonStyle.DANGER))
    else:
        for lot in lots:
            lot_id, seller_id, item_name, price = lot
            if seller_id != 0: 
                builder.row(InlineKeyboardButton(text=f"Купить {item_name} за {price}", callback_data=f"market_buy_{lot_id}", style=ButtonStyle.SUCCESS))
    
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    return builder.as_markup()

# --- Хэндлеры ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"🌟 <b>NFT CASINO</b> 🌟\n\n"
            f"👋 Привет, <b>{message.from_user.first_name}</b>!\n"
            f"💳 Баланс: <b>1000 монет</b>.\n\n"
            f"<i>Все кнопки теперь цветные!</i>")
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(), parse_mode="HTML")

# --- ТАБЛИЦЫ ЛИДЕРОВ ---
@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance", style=ButtonStyle.SUCCESS),
        InlineKeyboardButton(text="📈 По рынку", callback_data="top_market", style=ButtonStyle.PRIMARY)
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text("🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\nВыбери категорию:", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "top_balance")
async def cb_top_balance(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    
    text = "🏆 <b>ТОП ПО БАЛАНСУ</b>\n\n"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        # Пытаемся получить юзернейм
        try:
            user = await bot.get_chat(uid)
            name = f"@{user.username}" if user.username else user.first_name
        except:
            name = f"ID {uid}"
        text += f"{medal} {name} — <b>{bal}</b> монет\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="leaderboard", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "top_market")
async def cb_top_market(callback: types.CallbackQuery):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, market_earnings FROM users WHERE market_earnings > 0 ORDER BY market_earnings DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    
    if not top:
        await callback.answer("Пока никто ничего не продал на рынке!", show_alert=True)
        return

    text = "📈 <b>ТОП ПО ЗАРАБОТКУ НА РЫНКЕ</b>\n\n"
    for i, (uid, earnings) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        try:
            user = await bot.get_chat(uid)
            name = f"@{user.username}" if user.username else user.first_name
        except:
            name = f"ID {uid}"
        text += f"{medal} {name} — <b>{earnings}</b> монет\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="leaderboard", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _, earnings = get_user(callback.from_user.id)
    items = get_inventory(callback.from_user.id)
    text = (f"╔══════════════════╗\n"
            f"   👤 <b>ПРОФИЛЬ</b>\n"
            f"╚══════════════════╝\n\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n"
            f"💰 Баланс: <b>{bal}</b> монет\n"
            f"🎒 NFT в инвентаре: <b>{len(items)}</b> шт.\n"
            f"📈 Заработано на рынке: <b>{earnings}</b> монет\n\n"
            f"🏆 Статус: <i>{'Новичок' if bal < 2000 else 'Любитель' if bal < 5000 else 'Профи' if bal < 10000 else 'Магнат'}</i>")
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, last_bonus, _ = get_user(user_id)
    now = int(time.time())
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True)
        return
    update_balance(user_id, DAILY_BONUS)
    update_bonus_time(user_id, now)
    await callback.answer(f"🎉 +{DAILY_BONUS} монет!", show_alert=True)
    await callback.message.edit_text("🎁 Бонус получен!", reply_markup=main_menu(), parse_mode="HTML")

# --- ИНВЕНТАРЬ И ПРОДАЖА ---
@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: types.CallbackQuery):
    items = get_inventory(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    text = "🎒 <b>ТВОЙ ИНВЕНТАРЬ</b>\n\n"
    if not items:
        text += "<i>Пусто. Купи NFT в магазине.</i>"
    else:
        for item_id, name in items:
            text += f"🔸 {name}\n"
            builder.row(InlineKeyboardButton(text=f"💰 Продать {name}", callback_data=f"sell_{item_id}", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("sell_"))
async def cb_sell_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[1])
    await state.update_data(sell_item_id=item_id)
    await callback.message.edit_text("💵 Введи цену, за которую хочешь продать этот NFT на рынке (целое число):")
    await state.set_state(GameStates.selling_price)

@dp.message(GameStates.selling_price)
async def process_sell_price(message: types.Message, state: FSMContext):
    try: price = int(message.text)
    except: return
    data = await state.get_data()
    item_id = data['sell_item_id']
    
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, item_name FROM inventory WHERE id = ?", (item_id,))
    res = c.fetchone()
    if not res or res[0] != message.from_user.id:
        await message.answer("❌ Ошибка: этот NFT не твой.")
        await state.clear(); return
    
    item_name = res[1]
    c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    c.execute("INSERT INTO market (seller_id, item_name, price) VALUES (?, ?, ?)", (message.from_user.id, item_name, price))
    conn.commit(); conn.close()
    
    await message.answer(f"✅ NFT <b>{item_name}</b> выставлен на рынок за <b>{price}</b> монет!", reply_markup=main_menu(), parse_mode="HTML")
    await state.clear()

# --- Магазин и Рынок ---
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН (Официальный)</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, price in SHOP_ITEMS.items():
        text += f"🔹 {name} — <b>{price}</b> монет\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="🏪 РЫНОК ИГРОКОВ", callback_data="market", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main", style=ButtonStyle.DANGER))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "market")
async def cb_market(callback: types.CallbackQuery):
    await callback.message.edit_text("🏪 <b>РЫНОК NFT</b>\n\nВыбери лот для покупки или предложи свою цену:", reply_markup=market_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy_shop(callback: types.CallbackQuery):
    item = callback.data.replace("buy_", "")
    price = SHOP_ITEMS.get(item)
    if price and buy_item(callback.from_user.id, item, price):
        await callback.answer(f"✅ Куплено: {item}", show_alert=True)
    else:
        await callback.answer("❌ Не хватает монет!", show_alert=True)

@dp.callback_query(F.data.startswith("market_buy_"))
async def cb_market_buy(callback: types.CallbackQuery):
    lot_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT seller_id, item_name, price FROM market WHERE id = ?", (lot_id,))
    res = c.fetchone()
    
    if not res:
        conn.close()
        await callback.answer("Лот уже продан!", show_alert=True)
        return
    
    seller_id, item_name, price = res
    bal, _, _ = get_user(callback.from_user.id)
    
    if bal < price:
        conn.close()
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🤝 Предложить цену", callback_data=f"offer_start_{lot_id}", style=ButtonStyle.SUCCESS))
        builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="market", style=ButtonStyle.DANGER))
        await callback.message.edit_text(f"У тебя не хватает монет (нужно {price}).\nНо ты можешь предложить продавцу свою цену!", reply_markup=builder.as_markup())
        return

    update_balance(callback.from_user.id, -price)
    update_balance(seller_id, price)
    update_market_earnings(seller_id, price) # Записываем заработок продавцу
    
    c.execute("DELETE FROM market WHERE id = ?", (lot_id,))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item_name))
    conn.commit(); conn.close()
    
    await callback.answer(f"✅ Куплено: {item_name}", show_alert=True)
    await callback.message.edit_text("🏪 Рынок обновлен.", reply_markup=market_menu())

# --- ПРЕДЛОЖЕНИЯ ---
@dp.callback_query(F.data.startswith("offer_start_"))
async def cb_offer_start(callback: types.CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split("_")[2])
    await state.update_data(offer_lot_id=lot_id)
    await callback.message.edit_text("💵 Введи сумму, которую ты предлагаешь за этот NFT:")
    await state.set_state(GameStates.offer_amount)

@dp.message(GameStates.offer_amount)
async def process_offer(message: types.Message, state: FSMContext):
    try: amount = int(message.text)
    except: return
    data = await state.get_data()
    lot_id = data['offer_lot_id']
    
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT seller_id, item_name FROM market WHERE id = ?", (lot_id,))
    res = c.fetchone()
    if not res:
        conn.close()
        await message.answer("Лот уже неактуален.")
        await state.clear(); return
    
    seller_id, item_name = res
    c.execute("INSERT INTO offers (market_id, buyer_id, amount) VALUES (?, ?, ?)", (lot_id, message.from_user.id, amount))
    conn.commit(); conn.close()
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"offer_accept_{lot_id}_{message.from_user.id}_{amount}", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"offer_decline_{lot_id}", style=ButtonStyle.DANGER))
    
    try:
        await bot.send_message(seller_id, f"💰 <b>Новое предложение!</b>\n\nПокупатель предлагает <b>{amount}</b> монет за твой NFT <b>{item_name}</b>.", reply_markup=builder.as_markup(), parse_mode="HTML")
    except: pass
        
    await message.answer(f"✅ Предложение отправлено продавцу!", reply_markup=main_menu(), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("offer_accept_"))
async def cb_offer_accept(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    lot_id, buyer_id, amount = int(parts[2]), int(parts[3]), int(parts[4])
    
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT seller_id, item_name FROM market WHERE id = ?", (lot_id,))
    res = c.fetchone()
    if not res:
        conn.close(); await callback.answer("Лот уже продан или удален.", show_alert=True); return
    seller_id, item_name = res
    
    buyer_bal, _, _ = get_user(buyer_id)
    if buyer_bal < amount:
        conn.close(); await callback.answer("У покупателя уже не хватает денег.", show_alert=True); return

    update_balance(buyer_id, -amount)
    update_balance(seller_id, amount)
    update_market_earnings(seller_id, amount) # Записываем заработок
    
    c.execute("DELETE FROM market WHERE id = ?", (lot_id,))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (buyer_id, item_name))
    conn.commit(); conn.close()
    
    await callback.message.edit_text(f"✅ Сделка совершена! Ты продал {item_name} за {amount} монет.")
    try: await bot.send_message(buyer_id, f"✅ Твое предложение принято! Ты купил {item_name} за {amount}.")
    except: pass

@dp.callback_query(F.data.startswith("offer_decline_"))
async def cb_offer_decline(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Предложение отклонено.")
    await callback.answer()

# --- Казино (Монетка, Кубик, Дартс) ---
@dp.callback_query(F.data == "casino")
async def cb_casino(callback: types.CallbackQuery):
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>\n\nВыбери игру:", reply_markup=casino_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("game_") & ~F.data.contains("mine"))
async def cb_game(callback: types.CallbackQuery, state: FSMContext):
    game = callback.data.replace("game_", "")
    await state.update_data(game=game)
    await callback.message.edit_text(f"💵 Введи сумму ставки для игры {game.upper()}:")
    await state.set_state(GameStates.waiting_for_bet)

@dp.message(GameStates.waiting_for_bet)
async def process_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: return
    bal, _, _ = get_user(message.from_user.id)
    if bal < bet:
        await message.answer(f"❌ Мало монет (баланс {bal})")
        await state.clear(); return

    data = await state.get_data()
    game = data['game']
    res_text = ""
    if game == "coin":
        if random.choice([True, False]):
            update_balance(message.from_user.id, bet); res_text = f"🪙 ОРЕЛ! +{bet} монет."
        else:
            update_balance(message.from_user.id, -bet); res_text = f"🪙 РЕШКА. -{bet} монет."
    elif game == "dice":
        u, b = random.randint(1,6), random.randint(1,6)
        if u > b: update_balance(message.from_user.id, bet); res_text = f"🎲 {u} vs {b}. Победа! +{bet}"
        elif u < b: update_balance(message.from_user.id, -bet); res_text = f"🎲 {u} vs {b}. Поражение. -{bet}"
        else: res_text = f"🎲 {u} vs {b}. Ничья."
    elif game == "darts":
        if random.random() < 0.4:
            win = int(bet*2.5); update_balance(message.from_user.id, win); res_text = f"🎯 В яблочко! +{win}"
        else:
            update_balance(message.from_user.id, -bet); res_text = f"🎯 Мимо. -{bet}"
            
    new_bal, _, _ = get_user(message.from_user.id)
    await message.answer(f"{res_text}\n💰 Баланс: {new_bal}", reply_markup=casino_menu(), parse_mode="HTML")
    await state.clear()

# --- Минное поле (Сетка 5x5) ---
@dp.callback_query(F.data == "game_mine")
async def cb_mine_start(callback: types.CallbackQuery, state: FSMContext):
    text = ("💣 <b>МИННОЕ ПОЛЕ</b>\n\n"
            "Правила: на поле 25 клеток, 5 из них — мины.\n"
            "Открывай безопасные клетки, чтобы повысить множитель.\n"
            "В любой момент можешь забрать выигрыш. Наступишь на мину — потеряешь всё!\n\n"
            "💵 Введи сумму ставки:")
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(GameStates.minefield_bet)

@dp.message(GameStates.minefield_bet)
async def mine_bet(message: types.Message, state: FSMContext):
    try: bet = int(message.text)
    except: return
    bal, _, _ = get_user(message.from_user.id)
    if bal < bet:
        await message.answer(f"❌ Мало монет.")
        await state.clear(); return

    update_balance(message.from_user.id, -bet)
    mines = set(random.sample(range(25), 5))
    await state.update_data(bet=bet, mines=list(mines), opened=[], multiplier=1.0)
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        builder.button(text="❓", callback_data=f"mine_click_{i}", style=ButtonStyle.PRIMARY)
    builder.adjust(5)
    
    builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ (x1.0)", callback_data="mine_cashout", style=ButtonStyle.SUCCESS))
    await message.answer(f"💣 Ставка: {bet}\nВыбирай клетки:", reply_markup=builder.as_markup())
    await state.set_state(GameStates.minefield_play)

@dp.callback_query(GameStates.minefield_play, F.data.startswith("mine_click_"))
async def mine_click(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[2])
    data = await state.get_data()
    bet, mines, opened, mult = data['bet'], data['mines'], data['opened'], data['multiplier']
    
    if idx in opened:
        await callback.answer("Уже открыто!")
        return
        
    if idx in mines:
        await callback.message.edit_text(f"💥 <b>БУМ!</b> Ты наступил на мину и потерял {bet} монет.", reply_markup=casino_menu(), parse_mode="HTML")
        await state.clear()
        return
        
    opened.append(idx)
    mult = 1.0 + (len(opened) * 0.2)
    await state.update_data(opened=opened, multiplier=mult)
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        if i in opened:
            builder.button(text="💎", callback_data=f"mine_click_{i}", style=ButtonStyle.SUCCESS)
        else:
            builder.button(text="❓", callback_data=f"mine_click_{i}", style=ButtonStyle.PRIMARY)
    builder.adjust(5)
    
    cashout_amount = int(bet * mult)
    builder.row(InlineKeyboardButton(text=f"💰 ЗАБРАТЬ ({cashout_amount} монет)", callback_data="mine_cashout", style=ButtonStyle.SUCCESS))
    
    await callback.message.edit_text(f"💣 Множитель: x{mult:.1f}\nОткрыто клеток: {len(opened)}/20\nВыбирай дальше или забирай!", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "mine_cashout")
async def mine_cashout(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet, mult = data['bet'], data['multiplier']
    win = int(bet * mult)
    update_balance(callback.from_user.id, win)
    await callback.message.edit_text(f"💰 Ты забрал {win} монет! (Ставка {bet} x {mult:.1f})", reply_markup=casino_menu(), parse_mode="HTML")
    await state.clear()

async def main():
    init_db()
    print("Бот запущен с цветными кнопками и новыми топаМИ!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
