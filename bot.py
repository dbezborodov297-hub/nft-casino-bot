import asyncio
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "9209660223:AAFudEA1QGMyLOya1h8YS7mn-7ARBOEVpIw"
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Привет! Отправь мне стикер или премиум-эмодзи, и я покажу его ID.")

@dp.message()
async def get_id(message: types.Message):
    # Показываем "печатает..." (анимация)
    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(1.5) # Небольшая задержка для эффекта

    # Если это стикер
    if message.sticker:
        await message.reply(
            f"🎨 <b>Стикер!</b>\n\n"
            f"🆔 File ID:\n<code>{message.sticker.file_id}</code>\n\n"
            f"🔹 Уникальный ID (emoji):\n<code>{message.sticker.custom_emoji_id}</code>",
            parse_mode="HTML"
        )
        return

    # Если это сообщение с премиум-эмодзи в тексте
    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                await message.reply(
                    f"🌟 <b>Премиум-эмодзи!</b>\n\n"
                    f"🆔 Custom Emoji ID:\n<code>{entity.custom_emoji_id}</code>",
                    parse_mode="HTML"
                )
                return
                
    await message.reply("❌ Это не стикер и не премиум-эмодзи. Отправь стикер или эмодзи.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    Thread(target=run_flask, daemon=True).start()
    await asyncio.sleep(3)
    print("🚀 Детектор ID запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
