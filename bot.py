import os
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]

ADMIN_ID = 708544616
CHANNEL = "@prompt_realistic"

prompts = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        prompt_id = context.args[0]

        if prompt_id in prompts:
            await update.message.reply_text(
                "✨ پرامپت:\n\n" + prompts[prompt_id]
            )
            return

    await update.message.reply_text(
        "سلام 👋\n"
        "عکس + پرامپت را برای من بفرست."
    )


async def new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "📸 اول عکس را بفرست.\n"
        "بعد در پیام بعدی پرامپت را بفرست."
    )


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["photo"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        "✅ عکس دریافت شد.\n\n"
        "حالا پرامپت را در پیام بعدی بفرست."
    )


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if "photo" not in context.user_data:
        return

    prompt = update.message.text
    photo = context.user_data["photo"]

    prompt_id = uuid.uuid4().hex[:8]
    prompts[prompt_id] = prompt

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={prompt_id}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✨ دریافت پرامپت",
                url=link
            )
        ]
    ])

    await context.bot.send_photo(
        chat_id=CHANNEL,
        photo=photo,
        caption="✨ Prompt Realistic",
        reply_markup=keyboard
    )

    await update.message.reply_text(
        "✅ پست با موفقیت در کانال منتشر شد!\n\n"
        f"🔗 لینک دریافت پرامپت:\n{link}"
    )

    context.user_data.clear()


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_prompt))

    app.add_handler(
        MessageHandler(filters.PHOTO, receive_photo)
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
