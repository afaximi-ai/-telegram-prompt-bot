import os
import uuid
import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = 708544616
CHANNEL = "@prompt_realistic"

DB_FILE = "/data/bot.db"


# =========================
# SQLite
# =========================

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_prompt(prompt_id, prompt, photo_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO prompts (id, prompt, photo_id)
        VALUES (?, ?, ?)
        """,
        (prompt_id, prompt, photo_id)
    )

    conn.commit()
    conn.close()


def get_prompt(prompt_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT prompt
        FROM prompts
        WHERE id = ?
        """,
        (prompt_id,)
    )

    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


# =========================
# بررسی عضویت در کانال
# =========================

async def is_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID:
        return True

    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL,
            user_id=user_id
        )

        return member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception:
        return False


# =========================
# پیام عضویت
# =========================

async def membership_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 عضویت در کانال",
                url="https://t.me/prompt_realistic"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ عضو شدم",
                callback_data="check_membership"
            )
        ]
    ])

    await update.message.reply_text(
        "🔒 برای استفاده از ربات ابتدا باید عضو کانال ما شوید.\n\n"
        "1️⃣ روی «📢 عضویت در کانال» بزنید.\n"
        "2️⃣ عضو کانال شوید.\n"
        "3️⃣ سپس روی «✅ عضو شدم» بزنید.",
        reply_markup=keyboard
    )


# =========================
# Start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # اگر کاربر از لینک دریافت پرامپت آمده باشد
    if context.args:
        prompt_id = context.args[0]

        # ذخیره موقت شناسه پرامپت
        context.user_data["pending_prompt_id"] = prompt_id

    # بررسی عضویت
    if not await is_member(update, context):
        await membership_message(update, context)
        return

    # اگر عضو باشد، پرامپت را مستقیم نمایش بده
    prompt_id = context.user_data.pop(
        "pending_prompt_id",
        None
    )

    if prompt_id:
        prompt = get_prompt(prompt_id)

        if prompt:
            await update.message.reply_text(
                "✨ پرامپت:\n\n" + prompt
            )
            return

    await update.message.reply_text(
        "سلام 👋\n"
        "عکس + پرامپت را برای من بفرست."
    )


# =========================
# بررسی دوباره عضویت
# =========================

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    user_id = query.from_user.id

    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL,
            user_id=user_id
        )

        is_joined = member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception:
        is_joined = False

    if is_joined:

        await query.answer("✅ عضویت تأیید شد!")

        # دریافت شناسه پرامپتی که کاربر قبلاً درخواست کرده بود
        prompt_id = context.user_data.pop(
            "pending_prompt_id",
            None
        )

        if prompt_id:

            prompt = get_prompt(prompt_id)

            if prompt:
                await query.edit_message_text(
                    "✨ پرامپت:\n\n" + prompt
                )
                return

        await query.edit_message_text(
            "✅ عضویت شما تأیید شد!"
        )

    else:

        await query.answer(
            "❌ هنوز عضو کانال نشده‌اید!",
            show_alert=True
        )


# =========================
# دستور new
# =========================

async def new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "📸 اول عکس را بفرست.\n"
        "بعد در پیام بعدی پرامپت را بفرست."
    )


# =========================
# دریافت عکس
# =========================

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["photo"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        "✅ عکس دریافت شد.\n\n"
        "حالا پرامپت را در پیام بعدی بفرست."
    )


# =========================
# دریافت پرامپت
# =========================

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if "photo" not in context.user_data:
        return

    prompt = update.message.text
    photo = context.user_data["photo"]

    prompt_id = uuid.uuid4().hex[:8]

    # ذخیره در SQLite
    save_prompt(
        prompt_id,
        prompt,
        photo
    )

    # ساخت لینک
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

    # انتشار در کانال
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


# =========================
# اجرای ربات
# =========================

def main():

    # ساخت دیتابیس SQLite
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("new", new_prompt)
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_prompt
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern="^check_membership$"
        )
    )

    app.run_polling()


if __name__ == "__main__":
    main()