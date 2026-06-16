import os
from html import escape

import telebot


BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def custom_emoji_entities(message):
    entities = []
    if getattr(message, "entities", None):
        entities.extend(message.entities)
    if getattr(message, "caption_entities", None):
        entities.extend(message.caption_entities)
    return [entity for entity in entities if entity.type == "custom_emoji"]


def get_entity_text(text, entity):
    if not text:
        return "🙂"
    return text[entity.offset : entity.offset + entity.length] or "🙂"


@bot.message_handler(commands=["start", "help"])
def send_help(message):
    bot.reply_to(
        message,
        "Premium Emoji ID Bot ready hai.\n\n"
        "Mujhe Telegram Premium custom emoji bhejo. "
        "Main uska custom_emoji_id aur use karne wala HTML code de dunga.",
    )


@bot.message_handler(content_types=["text"])
def get_custom_emoji_id(message):
    entities = custom_emoji_entities(message)

    if not entities:
        bot.reply_to(
            message,
            "Is message me premium custom emoji detect nahi hua.\n\n"
            "Telegram emoji panel se Premium/custom emoji select karke bhejo, normal emoji nahi.",
        )
        return

    text = message.text or message.caption or ""
    blocks = []

    for index, entity in enumerate(entities, start=1):
        fallback_emoji = get_entity_text(text, entity)
        emoji_id = entity.custom_emoji_id
        html_code = f'<tg-emoji emoji-id="{emoji_id}">{fallback_emoji}</tg-emoji>'

        blocks.append(
            f"Emoji {index}\n"
            f"custom_emoji_id:\n{emoji_id}\n\n"
            f"HTML code:\n<code>{escape(html_code)}</code>"
        )

    bot.reply_to(message, "\n\n".join(blocks))


@bot.message_handler(content_types=["sticker"])
def sticker_warning(message):
    bot.reply_to(
        message,
        "Ye sticker hai, premium custom emoji nahi.\n\n"
        "Emoji keyboard se Premium/custom emoji ko text message ke andar bhejo.",
    )


@bot.message_handler(func=lambda message: True)
def fallback(message):
    bot.reply_to(
        message,
        "Mujhe text message me Telegram Premium/custom emoji bhejo.",
    )


print("Premium Emoji ID bot is running...")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
