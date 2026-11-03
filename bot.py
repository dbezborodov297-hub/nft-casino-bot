import asyncio
import random
import sqlite3
import time
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9020652959:AAFK8u3s_rWTfmJc8Slr5qOnD0QkpW86k0Q"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

SHOP_ITEMS = {"🚀 Ракета": 50, "🗽 Статуя Свободы": 1200}
DAILY_BONUS = 50

# Хелпер для создания цветных кнопок (пока aiogram не обновился, передаем через json)
def make_btn(text, callback_data=None, url=None, style=None, icon=None):
    btn = {"text": text}
    if callback_data: btn["callback_data"] = callback_data
    if url: btn["url"] = url
    if style: btn["style"] = style  # "success", "danger", "primary"
    if icon: btn["icon_custom_emoji_id"] = icon
    return btn

class GameStates(StatesGroup):
    waiting_for_bet = State()
    minefield_bet = State()
    minefield_play = State()
    selling_price = State()
    offer_amount = State()

# --- БД ---
def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT)''')
    # Таблица для лотов на рынке
    c.execute('''CREATE TABLE IF NOT EXISTS market (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_name TEXT, price INTEGER)''')
    # Таблица для предложений о покупке
    c.execute('''CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY AUTOINCREMENT, market_id INTEGER, buyer_id INTEGER, amount INTEGER)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance, last_bonus) VALUES (?, 1000, 0)", (user_id,))
        conn.commit()
        res = (1000, 0)
    conn.close()
    return res

def update_balance(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
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
    bal, _ = get_user(user_id)
    if bal < price: return False
    update_balance(user_id, -price)
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (user_id, item_name))
    conn.commit()
    conn.close()
    return True

def get_leaderboard():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    return top

# --- Клавиатуры ---
def main_menu():
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
    builder.row(InlineKeyboardButton(text="🎁 БОНУС", callback_data="daily"))
    return builder.as_markup()

def casino_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 МОНЕТКА", callback_data="game_coin"),
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="game_dice")
    )
    builder.row(InlineKeyboardButton(text="🎯 ДАРТС", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="💣 МИННОЕ ПОЛЕ", callback_data="game_mine"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

def market_menu():
    builder = InlineKeyboardBuilder()
    # Получаем лоты с рынка
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT id, seller_id, item_name, price FROM market")
    lots = c.fetchall()
    conn.close()
    
    if not lots:
        builder.row(InlineKeyboardButton(text="😕 Рынок пуст", callback_data="noop"))
    else:
        for lot in lots:
            lot_id, seller_id, item_name, price = lot
            if seller_id != 0: # не показываем свои же лоты
                builder.row(InlineKeyboardButton(text=f"Купить {item_name} за {price}", callback_data=f"market_buy_{lot_id}"))
    
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    return builder.as_markup()

# --- Хэндлеры ---
@dp.message(Command("start"))
async def start(message: types.Message):
    get_user(message.from_user.id)
    text = (f"🌟 <b>NFT CASINO</b> 🌟\n\n"
            f"👋 Привет, <b>{message.from_user.first_name}</b>!\n"
            f"💳 Баланс: <b>1000 монет</b>.\n\n"
            f"<i>Играй, покупай NFT и продавай их другим игрокам!</i>")
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>ГЛАВНОЕ МЕНЮ</b>", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: types.CallbackQuery):
    top = get_leaderboard()
    text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b>\n\n"
    for i, (uid, bal) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} ID {uid} — <b>{bal}</b> монет\n"
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    bal, _ = get_user(callback.from_user.id)
    items = get_inventory(callback.from_user.id)
    text = (f"╔══════════════════╗\n"
            f"   👤 <b>ПРОФИЛЬ</b>\n"
            f"╚══════════════════╝\n\n"
            f"💰 Баланс: <b>{bal}</b>\n"
            f"🎒 NFT в инвентаре: <b>{len(items)}</b> шт.\n"
            f"🏆 Место в топе: смотри вкладку ТОП\n\n"
            f"<i>Чтобы продать NFT, зайди в Инвентарь.</i>")
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "daily")
async def cb_daily(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, last_bonus = get_user(user_id)
    now = int(time.time())
    if now - last_bonus < 86400:
        left = 86400 - (now - last_bonus)
        await callback.answer(f"⏳ Жди: {left//3600}ч {(left%3600)//60}м", show_alert=True)
        return
    update_balance(user_id, DAILY_BONUS)
    update_bonus_time(user_id, now)
    await callback.answer(f"🎉 +{DAILY_BONUS} монет!", show_alert=True)
    await callback.message.edit_text("🎁 Бонус получен!", reply_markup=main_menu(), parse_mode="HTML")

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
            # Кнопка "Продать" (зеленая)
            btn = make_btn(f"💰 Продать {name}", callback_data=f"sell_{item_id}", style="success")
            builder.row(InlineKeyboardButton(**btn))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("sell_"))
async def cb_sell_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[1])
    await state.update_data(sell_item_id=item_id)
    await callback.message.edit_text("💵 Введи цену, за которую хочешь продать этот NFT на рынке (целое число):")
    await state.set_state(GameStates.selling_price)

@dp.message(GameStates.selling_price)
async def process_sell_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
    except: return
    data = await state.get_data()
    item_id = data['sell_item_id']
    
    # Проверяем, что предмет наш
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, item_name FROM inventory WHERE id = ?", (item_id,))
    res = c.fetchone()
    if not res or res[0] != message.from_user.id:
        await message.answer("❌ Ошибка: этот NFT не твой.")
        await state.clear()
        return
    
    item_name = res[1]
    # Удаляем из инвентаря и ставим на рынок
    c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    c.execute("INSERT INTO market (seller_id, item_name, price) VALUES (?, ?, ?)", (message.from_user.id, item_name, price))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ NFT <b>{item_name}</b> выставлен на рынок за <b>{price}</b> монет!", reply_markup=main_menu(), parse_mode="HTML")
    await state.clear()

# --- Магазин и Рынок ---
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: types.CallbackQuery):
    text = "🛒 <b>МАГАЗИН (Официальный)</b>\n\n"
    builder = InlineKeyboardBuilder()
    for name, price in SHOP_ITEMS.items():
        text += f"🔹 {name} — <b>{price}</b> монет\n"
        builder.row(InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{name}"))
    builder.row(InlineKeyboardButton(text="🏪 РЫНОК ИГРОКОВ", callback_data="market"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_main"))
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
    conn.close()
    
    if not res:
        await callback.answer("Лот уже продан!", show_alert=True)
        return
    
    seller_id, item_name, price = res
    bal, _ = get_user(callback.from_user.id)
    
    if bal < price:
        # Предложить свою цену (кнопки: Предложить / Отмена)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🤝 Предложить цену", callback_data=f"offer_start_{lot_id}"))
        builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="market"))
        await callback.message.edit_text(f"У тебя не хватает монет (нужно {price}).\nНо ты можешь предложить продавцу свою цену!", reply_markup=builder.as_markup())
        return

    # Покупка по полной цене
    update_balance(callback.from_user.id, -price)
    update_balance(seller_id, price)
    
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("DELETE FROM market WHERE id = ?", (lot_id,))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (callback.from_user.id, item_name))
    conn.commit()
    conn.close()
    
    await callback.answer(f"✅ Куплено: {item_name}", show_alert=True)
    await callback.message.edit_text("🏪 Рынок обновлен.", reply_markup=market_menu())

@dp.callback_query(F.data.startswith("offer_start_"))
async def cb_offer_start(callback: types.CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split("_")[2])
    await state.update_data(offer_lot_id=lot_id)
    await callback.message.edit_text("💵 Введи сумму, которую ты предлагаешь за этот NFT:")
    await state.set_state(GameStates.offer_amount)

@dp.message(GameStates.offer_amount)
async def process_offer(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
    except: return
    data = await state.get_data()
    lot_id = data['offer_lot_id']
    
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT seller_id, item_name FROM market WHERE id = ?", (lot_id,))
    res = c.fetchone()
    conn.close()
    
    if not res:
        await message.answer("Лот уже неактуален.")
        await state.clear()
        return
    
    seller_id, item_name = res
    
    # Сохраняем предложение
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO offers (market_id, buyer_id, amount) VALUES (?, ?, ?)", (lot_id, message.from_user.id, amount))
    conn.commit()
    conn.close()
    
    # Отправляем уведомление продавцу с ЦВЕТНЫМИ кнопками
    builder = InlineKeyboardBuilder()
    # Зеленая кнопка Принять
    btn_accept = make_btn("✅ ПРИНЯТЬ", callback_data=f"offer_accept_{lot_id}_{message.from_user.id}_{amount}", style="success")
    # Красная кнопка Отклонить
    btn_decline = make_btn("❌ ОТКЛОНИТЬ", callback_data=f"offer_decline_{lot_id}", style="danger")
    
    builder.row(InlineKeyboardButton(**btn_accept))
    builder.row(InlineKeyboardButton(**btn_decline))
    
    try:
        await bot.send_message(
            seller_id,
            f"💰 <b>Новое предложение!</b>\n\n"
            f"Покупатель предлагает <b>{amount}</b> монет за твой NFT <b>{item_name}</b>.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except:
        pass
        
    await message.answer(f"✅ Предложение отправлено продавцу!", reply_markup=main_menu(), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("offer_accept_"))
async def cb_offer_accept(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    lot_id = int(parts[2])
    buyer_id = int(parts[3])
    amount = int(parts[4])
    
    # Проверка, что лот еще висит
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT seller_id, item_name FROM market WHERE id = ?", (lot_id,))
    res = c.fetchone()
    if not res:
        conn.close()
        await callback.answer("Лот уже продан или удален.", show_alert=True)
        return
    seller_id, item_name = res
    
    # Проверка баланса покупателя
    buyer_bal, _ = get_user(buyer_id)
    if buyer_bal < amount:
        await callback.answer("У покупателя уже не хватает денег.", show_alert=True)
        return

    # Транзакция
    update_balance(buyer_id, -amount)
    update_balance(seller_id, amount)
    
    c.execute("DELETE FROM market WHERE id = ?", (lot_id,))
    c.execute("INSERT INTO inventory (user_id, item_name) VALUES (?, ?)", (buyer_id, item_name))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"✅ Сделка совершена! Ты продал {item_name} за {amount} монет.")
    try:
        await bot.send_message(buyer_id, f"✅ Твое предложение принято! Ты купил {item_name} за {amount}.")
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
    bal, _ = get_user(message.from_user.id)
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
            
    new_bal, _ = get_user(message.from_user.id)
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
    bal, _ = get_user(message.from_user.id)
    if bal < bet:
        await message.answer(f"❌ Мало монет.")
        await state.clear(); return

    update_balance(message.from_user.id, -bet)
    # Генерируем 5 мин
    mines = set(random.sample(range(25), 5))
    await state.update_data(bet=bet, mines=list(mines), opened=[], multiplier=1.0)
    
    builder = InlineKeyboardBuilder()
    for i in range(25):
        builder.button(text="❓", callback_data=f"mine_click_{i}")
    builder.adjust(5)
    
    builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ (x1.0)", callback_data="mine_cashout"))
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
        # Взрыв
        await callback.message.edit_text(f"💥 <b>БУМ!</b> Ты наступил на мину и потерял {bet} монет.", reply_markup=casino_menu(), parse_mode="HTML")
        await state.clear()
        return
        
    # Безопасно
    opened.append(idx)
    mult = 1.0 + (len(opened) * 0.2) # Каждая клетка +20% к множителю
    await state.update_data(opened=opened, multiplier=mult)
    
    # Перерисовываем поле
    builder = InlineKeyboardBuilder()
    for i in range(25):
        if i in opened:
            builder.button(text="💎", callback_data=f"mine_click_{i}")
        else:
            builder.button(text="❓", callback_data=f"mine_click_{i}")
    builder.adjust(5)
    
    # Кнопка забрать
    cashout_amount = int(bet * mult)
    btn_cash = make_btn(f"💰 ЗАБРАТЬ ({cashout_amount} монет)", callback_data="mine_cashout", style="success")
    builder.row(InlineKeyboardButton(**btn_cash))
    
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
    print("Бот запущен с рынком и цветными кнопками!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
