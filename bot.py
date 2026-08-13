import os
import uuid

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]

# آیدی عددی خودت را اینجا قرار بده
ADMIN_ID = 708544616

prompts = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args:
        prompt_id = args[0]

        if prompt_id in prompts:
            prompt = prompts[prompt_id]

            await update.message.reply_text(
                "✨ پرامپت:\n\n" + prompt
            )
            return

    await update.message.reply_text(
        "سلام 👋\n"
        "برای دریافت پرامپت از لینک اختصاصی همان تصویر استفاده کن."
    )


async def add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "بعد از /add پرامپت را بنویس."
        )
        return

    prompt = " ".join(context.args)

    prompt_id = uuid.uuid4().hex[:8]
    prompts[prompt_id] = prompt

    bot_username = (await context.bot.get_me()).username

    link = f"https://t.me/{bot_username}?start={prompt_id}"

    await update.message.reply_text(
        "✅ پرامپت ثبت شد!\n\n"
        "🔗 لینک دریافت پرامپت:\n"
        f"{link}\n\n"
        "این لینک را می‌توانی به دکمه پست کانالت وصل کنی."
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_prompt))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()


if __name__ == "__main__":
    main()
