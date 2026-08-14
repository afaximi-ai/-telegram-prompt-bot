import os
import uuid
import json
import sqlite3
import base64
from google import genai
from google.genai import types
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
# =========================
# تنظیمات
# =========================
TOKEN = os.environ["BOT_TOKEN"]
# API Key جمینای
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_ID = 708544616
CHANNEL = "@prompt_realistic"
DB_FILE = "/data/bot.db"
# مدل Gemini
GEMINI_MODEL = "gemini-3.5-flash"
# =========================
# Gemini Client
# =========================
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
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
    photo_ids_json = json.dumps(photo_ids)
    cursor.execute(
        """
        INSERT INTO prompts (id, prompt, photo_id)
        VALUES (?, ?, ?)
        """,
        (
            prompt_id,
            prompt,
            photo_ids_json
        )
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
# بررسی عضویت کانال
# =========================
async def is_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    # ادمین نیازی به عضویت ندارد
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
async def membership_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # اگر کاربر از لینک دریافت پرامپت آمده
    if context.args:
        prompt_id = context.args[0]
        context.user_data["pending_prompt_id"] = prompt_id
    # بررسی عضویت
    if not await is_member(update, context):
        await membership_message(
            update,
            context
        )
        return
    # اگر عضو است، پرامپت را نمایش بده
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
        "سلام 👋\n\n"
        "📸 عکس + پرامپت را برای من بفرست.\n\n"
        "🪄 برای ساخت پرامپت از روی عکس، "
        "از منوی ربات گزینه «ساخت پرامپت از عکس» را انتخاب کن."
    )
# =========================
# منوی ساخت پرامپت از عکس
# =========================
async def prompt_from_photo_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # بررسی عضویت
    if not await is_member(update, context):
        await membership_message(
            update,
            context
        )
        return
    # فعال کردن حالت
    context.user_data["waiting_for_prompt_from_photo"] = True
    await update.message.reply_text(
        "🪄 ساخت پرامپت از عکس\n\n"
        "📸 حالا عکسی که می‌خواهی از روی آن پرامپت بسازم را ارسال کن.\n\n"
        "من تصویر را بررسی می‌کنم و یک پرامپت انگلیسی "
        "حرفه‌ای و دقیق برای تولید مجدد تصویر می‌سازم."
    )
# =========================
# تحلیل عکس و ساخت پرامپت
# =========================
async def generate_prompt_from_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # فقط زمانی اجرا شود که کاربر این قابلیت را انتخاب کرده باشد
    if not context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):
        return
    # بررسی API Key
    if not GEMINI_API_KEY or gemini_client is None:
        await update.message.reply_text(
            "❌ API جمینای هنوز تنظیم نشده است.\n\n"
            "لطفاً GEMINI_API_KEY را در Environment Variables "
            "تنظیم کن."
        )
        context.user_data.pop(
            "waiting_for_prompt_from_photo",
            None
        )
        return
    try:
        await update.message.reply_text(
            "🔍 عکس دریافت شد...\n\n"
            "🤖 در حال تحلیل تصویر و ساخت پرامپت حرفه‌ای هستم..."
        )
        # =========================
        # دریافت فایل تلگرام
        # =========================
        photo = update.message.photo[-1]
        telegram_file = await context.bot.get_file(
            photo.file_id
        )
        # دانلود در حافظه
        image_bytes = await telegram_file.download_as_bytearray()
        # =========================
        # ساخت پرامپت تحلیلی
        # =========================
        analysis_prompt = """
Analyze the provided image extremely carefully and create a highly detailed
English prompt that can be used to recreate the image with an AI image
generator.
Describe the image objectively and visually.
Include, when visible:
- Main subject and identity-neutral physical appearance
- Face and facial features
- Hair
- Skin tone
- Clothing and accessories
- Pose and body position
- Hand position
- Facial expression
- Camera angle
- Framing and composition
- Perspective
- Background
- Environment
- Lighting
- Shadows
- Colors
- Atmosphere
- Depth of field
- Lens characteristics
- Camera style
- Image quality
- Photorealism
- Important small visual details
If text is visible in the image, describe it accurately.
Do NOT mention that you are analyzing an image.
Do NOT use explanations before or after the prompt.
Return ONLY the final English image-generation prompt.
Make the prompt detailed, natural, professional and optimized for
photorealistic AI image generation.
Do not invent major elements that are not visible in the image.
"""
        # =========================
        # ارسال تصویر به Gemini
        # =========================
        image_part = types.Part.from_bytes(
            data=bytes(image_bytes),
            mime_type="image/jpeg"
        )
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                image_part,
                analysis_prompt
            ]
        )
        generated_prompt = response.text
        if not generated_prompt:
            await update.message.reply_text(
                "❌ Gemini نتوانست پرامپت تولید کند."
            )
            return
        generated_prompt = generated_prompt.strip()
        # =========================
        # ارسال پرامپت
        # =========================
        await update.message.reply_text(
            "✨ پرامپت ساخته شد:\n\n"
            + generated_prompt
        )
    except Exception as e:
        print(
            "Gemini error:",
            repr(e)
        )
        await update.message.reply_text(
            "❌ هنگام ساخت پرامپت خطایی رخ داد.\n\n"
            "لطفاً دوباره امتحان کن."
        )
    finally:
        context.user_data.pop(
            "waiting_for_prompt_from_photo",
            None
        )
# =========================
# بررسی دوباره عضویت
# =========================
async def check_membership(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
        await query.answer(
            "✅ عضویت تأیید شد!"
        )
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
            "✅ عضویت شما تأیید شد!\n\n"
            "حالا می‌توانید از ربات استفاده کنید."
        )
    else:
        await query.answer(
            "❌ هنوز عضو کانال نشده‌اید!",
            show_alert=True
        )
# =========================
# دستور /new
# =========================
async def new_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != ADMIN_ID:
        return
    # پاک کردن اطلاعات قبلی
    context.user_data.clear()
    # ایجاد لیست عکس‌ها
    context.user_data["photos"] = []
    await update.message.reply_text(
        "📸 حالا عکس‌ها را یکی‌یکی بفرست.\n\n"
        "می‌توانی چند عکس بفرستی.\n"
        "حداکثر ۱۰ عکس برای یک پست.\n\n"
        "بعد از تمام شدن عکس‌ها، پرامپت را بفرست."
    )
# =========================
# دریافت عکس
# =========================
async def receive_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != ADMIN_ID:
        return
    # اگر /new زده نشده باشد
    if "photos" not in context.user_data:
        context.user_data["photos"] = []
    photos = context.user_data["photos"]
    # حداکثر ۱۰ عکس
    if len(photos) >= 10:
        await update.message.reply_text(
            "❌ برای یک پست حداکثر ۱۰ عکس می‌توانی بفرستی.\n\n"
            "حالا پرامپت را بفرست."
        )
        return
    # بهترین کیفیت عکس
    photo_id = update.message.photo[-1].file_id
    # اضافه کردن عکس
    photos.append(photo_id)
    count = len(photos)
    await update.message.reply_text(
        f"✅ عکس شماره {count} دریافت شد.\n\n"
        "📸 اگر عکس دیگری داری بفرست.\n"
        "📝 وقتی تمام شد، پرامپت را بفرست."
    )
# =========================
# دریافت پرامپت
# =========================
async def receive_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
    # متن پرامپت
    prompt = update.message.text
    if not prompt or not prompt.strip():
        await update.message.reply_text(
            "❌ پرامپت نمی‌تواند خالی باشد."
        )
        return
    # =========================
    # ساخت ID
    # =========================
    prompt_id = uuid.uuid4().hex[:8]
    # =========================
    # ذخیره در SQLite
    # =========================
    save_prompt(
        prompt_id,
        prompt,
        photos
    )
    # =========================
    # ساخت لینک
    # =========================
    bot_username = (
        await context.bot.get_me()
    ).username
    link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?start={prompt_id}"
    )
    # =========================
    # ساخت دکمه
    # =========================
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
    # ارسال آلبوم
    # =========================
    try:
        sent_messages = await context.bot.send_media_group(
            chat_id=CHANNEL,
            media=media_group
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ خطا هنگام ارسال آلبوم:\n\n"
            f"{e}"
        )
        return
    # =========================
    # قرار دادن دکمه روی عکس اول
    # =========================
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL,
            message_id=sent_messages[0].message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        await update.message.reply_text(
            "⚠️ عکس‌ها در کانال منتشر شدند، "
            "اما قرار دادن دکمه با خطا مواجه شد:\n\n"
            f"{e}\n\n"
            f"🔗 لینک دریافت پرامپت:\n{link}"
        )
        context.user_data.clear()
        return
    # =========================
    # پیام موفقیت برای ادمین
    # =========================
    await update.message.reply_text(
        "✅ پست با موفقیت در کانال منتشر شد!\n\n"
        f"📸 تعداد عکس‌ها: {len(photos)}\n"
        f"🔗 لینک دریافت پرامپت:\n{link}"
    )
    # =========================
    # پاک کردن اطلاعات موقت
    # =========================
    context.user_data.clear()
# =========================
# تنظیم منوی ربات
# =========================
async def setup_bot_menu(
    application: Application
):
    await application.bot.set_my_commands([
        (
            "start",
            "شروع ربات"
        ),
        (
            "promptfromphoto",
            "🪄 ساخت پرامپت از عکس"
        ),
        (
            "new",
            "📸 انتشار پست جدید"
        )
    ])
# =========================
# اجرای ربات
# =========================
def main():
    # ساخت دیتابیس
    init_db()
    # ساخت Application
    app = (
        Application
        .builder()
        .token(TOKEN)
        .post_init(setup_bot_menu)
        .build()
    )
    # =========================
    # دستورات
    # =========================
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )
    app.add_handler(
        CommandHandler(
            "new",
            new_prompt
        )
    )
    app.add_handler(
        CommandHandler(
            "promptfromphoto",
            prompt_from_photo_command
        )
    )
    # =========================
    # عکس برای ساخت پرامپت
    #
    # این هندلر باید قبل از receive_photo باشد
    # =========================
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            generate_prompt_from_photo
        ),
        group=0
    )
    # =========================
    # دریافت عکس‌های ادمین
    # =========================
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo
        ),
        group=1
    )
    # =========================
    # دریافت پرامپت ادمین
    # =========================
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_prompt
        )
    )
    # =========================
    # بررسی عضویت
    # =========================
    app.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern="^check_membership$"
        )
    )
    print("Bot is running...")
    # اجرای ربات
    app.run_polling()
# =========================
# شروع برنامه
# =========================
if __name__ == "__main__":
    main()