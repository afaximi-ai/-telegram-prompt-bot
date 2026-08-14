import os
import uuid
import json
import sqlite3
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
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
def save_prompt(prompt_id, prompt, photo_ids):
    conn = get_db_connection()
    cursor = conn.cursor()
    # ذخیره لیست عکس‌ها به صورت JSON
    photo_ids_json = json.dumps(photo_ids)
    cursor.execute(
        """
        INSERT INTO prompts (id, prompt, photo_id)
        VALUES (?, ?, ?)
        """,
        (prompt_id, prompt, photo_ids_json)
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
    # پاک کردن اطلاعات قبلی
    context.user_data.clear()
    # ساخت لیست جدید عکس‌ها
    context.user_data["photos"] = []
    await update.message.reply_text(
        "📸 حالا عکس‌ها را یکی‌یکی بفرست.\n\n"
        "می‌توانی چند عکس بفرستی.\n"
        "بعد از تمام شدن عکس‌ها، پرامپت را بفرست."
    )
# =========================
# دریافت عکس
# =========================
async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # اگر /new زده نشده باشد
    if "photos" not in context.user_data:
        context.user_data["photos"] = []
    # دریافت بهترین کیفیت عکس
    photo_id = update.message.photo[-1].file_id
    # اضافه کردن عکس به لیست
    context.user_data["photos"].append(photo_id)
    count = len(context.user_data["photos"])
    await update.message.reply_text(
        f"✅ عکس شماره {count} دریافت شد.\n\n"
        "📸 اگر عکس دیگری داری بفرست.\n"
        "📝 وقتی تمام شد، پرامپت را بفرست."
    )
# =========================
# دریافت پرامپت
# =========================
async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # بررسی وجود عکس
    if "photos" not in context.user_data:
        return
    photos = context.user_data["photos"]
    if not photos:
        await update.message.reply_text(
            "❌ هنوز هیچ عکسی دریافت نشده است."
        )
        return
    prompt = update.message.text
    # ساخت ID
    prompt_id = uuid.uuid4().hex[:8]
    # ذخیره در SQLite
    save_prompt(
        prompt_id,
        prompt,
        photos
    )
    # ساخت لینک دریافت پرامپت
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
    # =========================
    # ساخت آلبوم
    # =========================
    media_group = []
    for photo_id in photos:
        media_group.append(
            InputMediaPhoto(
                media=photo_id
            )
        )
    # =========================
    # انتشار آلبوم در کانال
    # =========================
    sent_messages = await context.bot.send_media_group(
        chat_id=CHANNEL,
        media=media_group
    )
    # =========================
    # ارسال دکمه زیر آلبوم
    # =========================
    await context.bot.send_message(
        chat_id=CHANNEL,
        text="✨ Prompt Realistic",
        reply_markup=keyboard,
        reply_to_message_id=sent_messages[0].message_id
    )
    # پیام موفقیت برای ادمین
    await update.message.reply_text(
        "✅ پست با موفقیت منتشر شد!\n\n"
        f"📸 تعداد عکس‌ها: {len(photos)}\n"
        f"🔗 لینک دریافت پرامپت:\n{link}"
    )
    # پاک کردن اطلاعات موقت
    context.user_data.clear()
# =========================
# اجرای ربات
# =========================
def main():
    # ساخت دیتابیس SQLite
    init_db()
    app = Application.builder().token(TOKEN).build()
    # Start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )
    # New
    app.add_handler(
        CommandHandler(
            "new",
            new_prompt
        )
    )
    # دریافت عکس
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo
        )
    )
    # دریافت پرامپت
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_prompt
        )
    )
    # بررسی عضویت
    app.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern="^check_membership$"
        )
    )
    print("Bot is running...")
    app.run_polling()
if __name__ == "__main__":
    main()