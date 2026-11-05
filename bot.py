import asyncio
import os
import sqlite3
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

BOT_TOKEN = "9209660223:AAHCOzCABUnZGvBfA54zklp78MyA5QW6B6g"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- БАЗА ---
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS contacts (
                 user_id INTEGER PRIMARY KEY, 
                 username TEXT, 
                 first_name TEXT, 
                 phone_number TEXT)''')
    conn.commit(); conn.close()

def save_contact(user_id, username, first_name, phone):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO contacts (user_id, username, first_name, phone_number) VALUES (?, ?, ?, ?)",
              (user_id, username, first_name, phone))
    conn.commit(); conn.close()

def get_contacts():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, phone_number FROM contacts")
    res = c.fetchall()
    conn.close()
    return res

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Привет! /help — команды.")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        f"📖 <b>ИНСТРУКЦИЯ</b>\n\n"
        f"• <b>/sticker_id</b> — узнать ID стикерпака (ответом на стикер)\n"
        f"• <b>/share_contact</b> — поделиться своим контактом\n"
        f"• <b>/admin</b> — админ-панель (только для владельца)"
    )
    await message.answer(text, parse_mode="HTML")

# --- 1. УЗНАТЬ ID СТИКЕРПАКА ---
@dp.message(Command("sticker_id"))
async def sticker_id(message: types.Message):
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await message.reply("❌ Ответь на стикер командой /sticker_id")
    
    sticker = message.reply_to_message.sticker
    pack_name = sticker.set_name if sticker.set_name else "Неизвестно"
    
    text = (f"🎨 <b>Информация о стикере:</b>\n\n"
            f"🆔 File ID: <code>{sticker.file_id}</code>\n"
            f"📦 Название пака: <code>{pack_name}</code>\n"
            f"🔹 Уникальный ID: <code>{sticker.custom_emoji_id}</code>")
    await message.reply(text, parse_mode="HTML")

# --- 2. ПОДЕЛИТЬСЯ КОНТАКТОМ ---
@dp.message(Command("share_contact"))
async def share_contact(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться своим контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Нажми на кнопку ниже, чтобы поделиться своим номером:", reply_markup=keyboard)

# Обработка полученного контакта
@dp.message(lambda message: message.contact is not None)
async def handle_contact(message: types.Message):
    contact = message.contact
    # Проверяем, что это контакт самого пользователя (а не пересланный)
    if contact.user_id == message.from_user.id:
        save_contact(
            message.from_user.id, 
            message.from_user.username, 
            message.from_user.first_name, 
            contact.phone_number
        )
        await message.answer("✅ Спасибо! Твой номер сохранён.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Пожалуйста, поделись своим контактом (нажми на кнопку).", reply_markup=ReplyKeyboardRemove())

# --- 3. АДМИН-ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Только для владельца.")
    
    contacts = get_contacts()
    if not contacts:
        return await message.reply("📋 Пока никто не поделился контактом.")
    
    text = "👑 <b>АДМИН-ПАНЕЛЬ: КОНТАКТЫ</b>\n\n"
    for uid, uname, fname, phone in contacts:
        text += f"👤 {fname}"
        if uname:
            text += f" (@{uname})"
        text += f"\n🆔 ID: <code>{uid}</code>\n📱 Тел: <code>{phone}</code>\n\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
