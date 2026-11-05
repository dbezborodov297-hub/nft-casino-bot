import asyncio
import sqlite3
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "9209660223:AAEM7nJz1VezgnNqf74aHZpcNfnYVrvS7-w"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Цены (можно менять)
STAR_PRICE = 1.5  # рублей за 1 звезду (пример)

app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 username TEXT,
                 amount INTEGER,
                 price REAL,
                 status TEXT DEFAULT 'pending',
                 created_at TEXT)''')
    conn.commit(); conn.close()

def create_order(user_id, username, amount, price):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, username, amount, price, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
              (user_id, username, amount, price))
    order_id = c.lastrowid
    conn.commit(); conn.close()
    return order_id

def get_order(order_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, amount, price, status FROM orders WHERE id = ?", (order_id,))
    res = c.fetchone()
    conn.close()
    return res

def complete_order(order_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
    conn.commit(); conn.close()

# --- ГЛАВНОЕ МЕНЮ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy_stars"))
    builder.row(InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders"))
    await message.answer("👋 Добро пожаловать в магазин звёзд!", reply_markup=builder.as_markup())

# --- ПОКУПКА ЗВЁЗД ---
@dp.callback_query(lambda c: c.data == "buy_stars")
async def buy_stars(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        price = amount * STAR_PRICE
        builder.row(InlineKeyboardButton(
            text=f"⭐ {amount} звёзд — {price:.0f} руб.",
            callback_data=f"order_{amount}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text("Выбери количество звёзд:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data.startswith("order_"))
async def process_order(callback: types.CallbackQuery):
    amount = int(callback.data.split("_")[1])
    price = amount * STAR_PRICE
    
    # Создаем заказ
    order_id = create_order(callback.from_user.id, callback.from_user.username or "нет", amount, price)
    
    # Уведомляем админа
    admin_text = (
        f"🆕 <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n"
        f"👤 Покупатель: @{callback.from_user.username or 'нет'} (ID: <code>{callback.from_user.id}</code>)\n"
        f"⭐ Звёзд: <b>{amount}</b>\n"
        f"💰 Сумма: <b>{price:.0f} руб.</b>\n\n"
        f"<i>Отправь звёзды вручную и нажми «Выполнено»</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{order_id}"))
    
    try:
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except: pass
    
    await callback.message.edit_text(
        f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
        f"⭐ Звёзд: {amount}\n"
        f"💰 К оплате: {price:.0f} руб.\n\n"
        f"<b>Реквизиты для оплаты:</b>\n"
        f"<code>СБП: +7 999 123-45-67</code>\n"
        f"<code>TON: UQ... (твой кошелек)</code>\n\n"
        f"<i>После оплаты напиши админу @твой_ник</i>",
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data.startswith("complete_"))
async def complete_order_cb(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ Только админ!", show_alert=True)
    
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    
    if not order:
        return await callback.answer("❌ Заказ не найден!", show_alert=True)
    
    complete_order(order_id)
    await callback.message.edit_text(f"✅ Заказ #{order_id} выполнен!")
    
    # Уведомляем покупателя
    try:
        await bot.send_message(order[1], f"🎉 <b>Заказ #{order_id} выполнен!</b>\n⭐ Звёзды отправлены.", parse_mode="HTML")
    except: pass

@dp.callback_query(lambda c: c.data == "my_orders")
async def my_orders(callback: types.CallbackQuery):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT id, amount, price, status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5", (callback.from_user.id,))
    orders = c.fetchall()
    conn.close()
    
    if not orders:
        return await callback.message.edit_text("📋 У тебя пока нет заказов.")
    
    text = "📋 <b>ТВОИ ЗАКАЗЫ</b>\n\n"
    for oid, amount, price, status in orders:
        status_icon = "✅" if status == "completed" else "⏳"
        text += f"{status_icon} Заказ #{oid}: {amount} ⭐ — {price:.0f} руб.\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "back")
async def back(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy_stars"))
    builder.row(InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders"))
    await callback.message.edit_text("👋 Главное меню:", reply_markup=builder.as_markup())

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    print("🚀 Бот-магазин звёзд запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
