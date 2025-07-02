import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

# 🔐 Токен и ID администратора
BOT_TOKEN = "8046924394:AAHogO7tHUdt7m8ZHNxZnt6gF2mSLHxBYng"
ADMIN_ID = 7634857359  # Замени на свой Telegram ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 🔎 Простейшая "база"
guarantors = {}  # username -> user_id
scammers = {}    # username -> dict

# 📷 Отправка изображения или текста, если фото нет
async def send_photo_or_text(message: Message, image_path: str, text: str):
    try:
        photo = FSInputFile(image_path)
        await message.answer_photo(photo, caption=text)
    except Exception as e:
        print(f"Ошибка при отправке фото '{image_path}': {e}")
        await message.answer(text)

# 🚀 /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Используй команду /check @username чтобы проверить пользователя.")

# 🔍 /check @username
@dp.message(Command("check"))
async def cmd_check(message: Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        await message.answer("Используй: /check @username")
        return

    username = args[1][1:].lower()

    if username in guarantors:
        user_id = guarantors[username]
        text = (
            f"🖼 Ник: @{username}\n"
            f"🆔 id: {user_id}\n"
            f"🕰 Проверка...\n"
            f"✅ Это гарант!"
        )
        await send_photo_or_text(message, "guarant.jpg", text)

    elif username in scammers:
        scam = scammers[username]
        reasons = "\n".join(f"- {r}" for r in scam["reasons"])
        text = (
            f"🖼 Ник: @{username}\n"
            f"🆔 id: {scam['id']}\n"
            f"🕰 Проверка...\n"
            f"❌ Это скамер!\n"
            f"📦 Сделок в скаме: {scam['count']}\n"
            f"📅 Последняя фиксация: {scam['last_date']}\n"
            f"\n📄 Причины:\n{reasons}"
        )
        await send_photo_or_text(message, "scammer.jpg", text)

    else:
        text = (
            f"🖼 Ник: @{username}\n"
            f"🆔 id: -\n"
            f"🕰 Проверка...\n"
            f"🌌 Обычный пользователь."
        )
        await send_photo_or_text(message, "user.jpg", text)

# ➕ /add_guarant @username (reply optional)
@dp.message(Command("add_guarant"))
async def add_guarant(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("У тебя нет прав.")

    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        return await message.answer("Используй: /add_guarant @username")

    username = args[1][1:].lower()
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else "-"
    guarantors[username] = user_id
    await message.answer(f"✅ @{username} добавлен в гаранты.")

# ❌ /remove_guarant @username
@dp.message(Command("remove_guarant"))
async def remove_guarant(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("У тебя нет прав.")

    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        return await message.answer("Используй: /remove_guarant @username")

    username = args[1][1:].lower()
    if username in guarantors:
        guarantors.pop(username)
        await message.answer(f"🗑 @{username} удалён из гарантов.")
    else:
        await message.answer(f"@{username} не найден в базе гарантов.")

# ❌ /add_scam @username 2 причина
@dp.message(Command("add_scam"))
async def add_scam(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("У тебя нет прав.")

    args = message.text.split(maxsplit=3)
    if len(args) < 3 or not args[1].startswith("@"):
        return await message.answer("Используй: /add_scam @username количество_сделок причина")

    username = args[1][1:].lower()
    try:
        count = int(args[2])
    except ValueError:
        return await message.answer("❗ Количество должно быть числом.")

    reason = args[3] if len(args) > 3 else "Не указана"
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else "-"

    if username in scammers:
        scammers[username]["count"] += count
        scammers[username]["reasons"].append(reason)
        scammers[username]["last_date"] = "сейчас"
    else:
        scammers[username] = {
            "id": user_id,
            "count": count,
            "last_date": "сейчас",
            "reasons": [reason]
        }

    await message.answer(f"🚫 @{username} добавлен в скамеры.")

# ❌ /remove_scam @username
@dp.message(Command("remove_scam"))
async def remove_scam(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("У тебя нет прав.")

    args = message.text.split()
    if len(args) != 2 or not args[1].startswith("@"):
        return await message.answer("Используй: /remove_scam @username")

    username = args[1][1:].lower()
    if username in scammers:
        scammers.pop(username)
        await message.answer(f"🗑 @{username} удалён из скамеров.")
    else:
        await message.answer(f"@{username} не найден в скамах.")

# 🔁 Запуск
async def main():
    print("Текущая папка:", os.getcwd())
    print("Файлы в папке:", os.listdir())
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
