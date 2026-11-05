import asyncio
import random
import sqlite3
import os
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ButtonStyle # <--- Импорт цветов

BOT_TOKEN = "9209660223:AAH7LMOOtCxXGve5wkJsRwft2PkWfD8VYeU"
ADMIN_ID = 8907438590

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, coins INTEGER DEFAULT 0)''')
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect('bot.db'); c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit(); res = (0,)
    conn.close(); return res[0]

async def is_chat_admin(message: types.Message):
    if message.from_user.id == ADMIN_ID: return True
    if message.chat.type == "private": return False
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ["administrator", "creator"]
    except: return False

# --- ГЛАВНОЕ МЕНЮ С ЦВЕТАМИ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    init_db()
    builder = InlineKeyboardBuilder()
    # Зеленая кнопка
    builder.row(InlineKeyboardButton(text="🎭 РП-Команды", callback_data="rp_menu", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile", style=ButtonStyle.PRIMARY))
    # Красная кнопка
    builder.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="close", style=ButtonStyle.DANGER))
    
    await message.answer(
        "👋 <b>Привет!</b>\nВыбери раздел:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "close")
async def close_menu(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    coins = get_user(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>ПРОФИЛЬ</b>\n\n🪙 Монеты: <b>{coins}</b>", parse_mode="HTML")

# --- МЕНЮ РП (С ЦВЕТАМИ) ---
@dp.callback_query(lambda c: c.data == "rp_menu")
async def rp_menu(callback: types.CallbackQuery):
    text = (
        "🎭 <b>РП-КОМАНДЫ</b>\n\n"
        "Используй ответом на сообщение:\n\n"
        "• <b>/обнять</b>\n"
        "• <b>/поцеловать</b>\n"
        "• <b>/ударить</b>\n"
        "• <b>/кусь</b>\n"
        "• <b>/трахнуть</b>\n"
        "• <b>/отсосать</b>\n"
        "• <b>/связать</b>\n"
        "• <b>/раздеть</b>"
    )
    builder = InlineKeyboardBuilder()
    # Зеленая кнопка "Назад"
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main", style=ButtonStyle.SUCCESS))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎭 РП-Команды", callback_data="rp_menu", style=ButtonStyle.SUCCESS))
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile", style=ButtonStyle.PRIMARY))
    builder.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="close", style=ButtonStyle.DANGER))
    await callback.message.edit_text("👋 <b>Главное меню</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

# --- РП-КОМАНДЫ ---
@dp.message(Command("трахнуть"))
async def rp_trah(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"🔥 {message.from_user.first_name} трахнул {target}! 🍆💦")

@dp.message(Command("отсосать"))
async def rp_otsosat(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"💦 {message.from_user.first_name} отсосал у {target}! 👅")

@dp.message(Command("связать"))
async def rp_svyazat(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"🪢 {message.from_user.first_name} связал {target}! 🔗")

@dp.message(Command("раздеть"))
async def rp_razdet(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"👕 {message.from_user.first_name} раздел {target}! 🩲")

@dp.message(Command("обнять"))
async def rp_obnyat(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"🫂 {message.from_user.first_name} обнял {target}! 🤗")

@dp.message(Command("поцеловать"))
async def rp_potselovat(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"💋 {message.from_user.first_name} поцеловал {target}! 😘")

@dp.message(Command("ударить"))
async def rp_udarit(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"👊 {message.from_user.first_name} ударил {target}! 💥")

@dp.message(Command("кусь"))
async def rp_kus(message: types.Message):
    if not message.reply_to_message: return await message.reply("❌ Ответь на сообщение.")
    target = message.reply_to_message.from_user.first_name
    await message.reply(f"😈 {message.from_user.first_name} кусь {target}! 🦷")

# --- МОДЕРАЦИЯ ---
@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if not await is_chat_admin(message) or not message.reply_to_message:
        return await message.reply("❌ Нет прав или нет ответа.")
    try:
        await bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 3600)
        await message.reply("🤐 Замучен на час.")
    except Exception as e: await message.reply(f"Ошибка: {e}")

@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if not await is_chat_admin(message) or not message.reply_to_message:
        return await message.reply("❌ Нет прав.")
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.reply("🔨 Забанен.")
    except: pass

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
