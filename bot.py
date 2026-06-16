import os

import telebot


BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start", "help"])
def send_help(message):
    bot.reply_to(
        message,
        "Send me any Telegram sticker.\n\n"
        "I will reply with the real sticker file_id that can be used with bot.send_sticker().",
    )


@bot.message_handler(content_types=["sticker"])
def get_sticker_id(message):
    sticker = message.sticker
    bot.reply_to(
        message,
        "COPY THIS file_id:\n"
        f"{sticker.file_id}\n\n"
        "Details:\n"
        f"file_unique_id: {sticker.file_unique_id}\n"
        f"set_name: {sticker.set_name or 'None'}\n"
        f"emoji: {sticker.emoji or 'None'}\n"
        f"is_animated: {sticker.is_animated}\n"
        f"is_video: {sticker.is_video}",
    )


@bot.message_handler(func=lambda message: True)
def fallback(message):
    bot.reply_to(message, "Send a sticker, then I will reply with its file_id.")


print("Sticker ID bot is running...")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
