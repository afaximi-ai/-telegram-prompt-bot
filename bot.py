import os
import uuid
import json
import sqlite3

from google import genai
from google.genai import types

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CopyTextButton,
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


# =========================================================
# تنظیمات
# =========================================================

TOKEN = os.environ["BOT_TOKEN"]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ADMIN_ID = 708544616

CHANNEL = "@prompt_realistic"

DB_FILE = "/data/bot.db"

GEMINI_MODEL = "gemini-3.5-flash"

PROMPT_BUTTON = "🪄 ✨ ساخت پرامپت از عکس"


# =========================================================
# Gemini
# =========================================================

gemini_client = None

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================================================
# SQLite
# =========================================================

def get_db_connection():

    os.makedirs(
        os.path.dirname(DB_FILE),
        exist_ok=True
    )

    return sqlite3.connect(DB_FILE)


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


def save_prompt(
    prompt_id,
    prompt,
    photo_ids
):

    conn = get_db_connection()
    cursor = conn.cursor()

    photo_ids_json = json.dumps(
        photo_ids
    )

    cursor.execute(
        """
        INSERT INTO prompts
        (id, prompt, photo_id)
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


# =========================================================
# کیبورد اصلی
# =========================================================

def get_main_keyboard():

    keyboard = [
        [
            KeyboardButton(
                PROMPT_BUTTON
            )
        ]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True
    )


# =========================================================
# بررسی عضویت
# =========================================================

async def is_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    except Exception as e:

        print(
            "Membership error:",
            repr(e)
        )

        return False


# =========================================================
# پیام عضویت
# =========================================================

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


# =========================================================
# ارسال نتیجه پرامپت
# فقط خود پرامپت
# =========================================================

async def send_prompt_result(
    update: Update,
    prompt: str
):

    prompt = prompt.strip()

    if len(prompt) <= 256:

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📋 کپی پرامپت",
                    copy_text=CopyTextButton(
                        text=prompt
                    )
                )
            ]
        ])

        await update.message.reply_text(
            prompt,
            reply_markup=keyboard
        )

    else:

        await update.message.reply_text(
            prompt,
            reply_markup=get_main_keyboard()
        )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if context.args:

        prompt_id = context.args[0]

        context.user_data[
            "pending_prompt_id"
        ] = prompt_id

    if not await is_member(
        update,
        context
    ):

        await membership_message(
            update,
            context
        )

        return

    prompt_id = context.user_data.pop(
        "pending_prompt_id",
        None
    )

    if prompt_id:

        prompt = get_prompt(
            prompt_id
        )

        if prompt:

            await send_prompt_result(
                update,
                prompt
            )

            return

    await update.message.reply_text(
        "سلام 👋\n\n"
        "به ربات Prompt Realistic خوش آمدی ✨\n\n"
        "برای ساخت پرامپت از روی عکس، "
        "دکمه زیر را بزن و سپس عکس را ارسال کن. 👇",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# دکمه ساخت پرامپت از عکس
# =========================================================

async def prompt_from_photo_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await is_member(
        update,
        context
    ):

        await membership_message(
            update,
            context
        )

        return

    context.user_data.pop(
        "photos",
        None
    )

    context.user_data.pop(
        "media_group_id",
        None
    )

    context.user_data[
        "waiting_for_prompt_from_photo"
    ] = True

    await update.message.reply_text(
        "🪄 ساخت پرامپت از عکس\n\n"
        "📸 حالا عکس را ارسال کن.\n\n"
        "🤖 عکس را بررسی می‌کنم و یک پرامپت "
        "انگلیسی حرفه‌ای و دقیق برایت می‌سازم.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# Gemini Vision
# =========================================================

async def generate_prompt_from_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):

        return

    if not GEMINI_API_KEY or gemini_client is None:

        await update.message.reply_text(
            "❌ API جمینای تنظیم نشده است.\n\n"
            "GEMINI_API_KEY را در Railway Variables قرار بده.",
            reply_markup=get_main_keyboard()
        )

        context.user_data.pop(
            "waiting_for_prompt_from_photo",
            None
        )

        return

    try:

        await update.message.reply_text(
            "🔍 عکس دریافت شد...\n\n"
            "🤖 در حال تحلیل تصویر و ساخت پرامپت...",
            reply_markup=get_main_keyboard()
        )

        photo = update.message.photo[-1]

        telegram_file = await context.bot.get_file(
            photo.file_id
        )

        image_bytes = (
            await telegram_file.download_as_bytearray()
        )

        analysis_prompt = """
Analyze the provided image extremely carefully.

Create ONE highly detailed English prompt that can be used
to recreate the image with an AI image generator.

Describe ONLY what is visually present.

Include:

- Main subject
- Gender presentation if visually apparent
- Approximate age appearance
- Face
- Facial features
- Hair
- Skin tone
- Clothing
- Accessories
- Pose
- Body position
- Hand position
- Facial expression
- Camera angle
- Framing
- Composition
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
- Photorealism
- Image quality
- Fine visual details

If text is visible in the image, describe it accurately.

Do NOT explain your answer.

Do NOT say that you analyzed an image.

Do NOT add headings.

Do NOT add notes.

Return ONLY the final English image-generation prompt.

Make it detailed, natural and professional.

Do not invent important elements that are not visible.
"""

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
                "❌ Gemini نتوانست پرامپت تولید کند.",
                reply_markup=get_main_keyboard()
            )

            return

        generated_prompt = generated_prompt.strip()

        await send_prompt_result(
            update,
            generated_prompt
        )

    except Exception as e:

        print(
            "Gemini error:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ هنگام ساخت پرامپت خطایی رخ داد.\n\n"
            "لطفاً دوباره امتحان کن.",
            reply_markup=get_main_keyboard()
        )

    finally:

        context.user_data.pop(
            "waiting_for_prompt_from_photo",
            None
        )


# =========================================================
# بررسی عضویت
# =========================================================

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

        joined = member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception as e:

        print(
            "Membership check error:",
            repr(e)
        )

        joined = False

    if not joined:

        await query.answer(
            "❌ هنوز عضو کانال نشده‌اید!",
            show_alert=True
        )

        return

    await query.answer(
        "✅ عضویت تأیید شد!"
    )

    prompt_id = context.user_data.pop(
        "pending_prompt_id",
        None
    )

    if prompt_id:

        prompt = get_prompt(
            prompt_id
        )

        if prompt:

            if len(prompt) <= 256:

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📋 کپی پرامپت",
                            copy_text=CopyTextButton(
                                text=prompt
                            )
                        )
                    ]
                ])

                await query.message.reply_text(
                    prompt,
                    reply_markup=keyboard
                )

            else:

                await query.message.reply_text(
                    prompt,
                    reply_markup=get_main_keyboard()
                )

            try:
                await query.delete_message()
            except Exception:
                pass

            return

    await query.edit_message_text(
        "✅ عضویت شما تأیید شد!\n\n"
        "حالا می‌توانید از ربات استفاده کنید."
    )


# =========================================================
# /new
# =========================================================

async def new_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data.clear()

    context.user_data[
        "photos"
    ] = []

    context.user_data[
        "media_group_id"
    ] = None

    await update.message.reply_text(
        "📸 حالا عکس‌ها را یکی‌یکی بفرست یا یک آلبوم را از کانال دیگر فوروارد کن.\n\n"
        "حداکثر ۱۰ عکس برای یک پست.\n\n"
        "بعد از تمام شدن عکس‌ها، پرامپت را بفرست.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# دریافت عکس ادمین
# =========================================================

async def receive_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):
        return

    if "photos" not in context.user_data:
        return

    photos = context.user_data.get(
        "photos",
        []
    )

    # =====================================================
    # حداکثر ۱۰ عکس
    # =====================================================

    if len(photos) >= 10:

        return

    # =====================================================
    # تشخیص Media Group
    # =====================================================

    media_group_id = update.message.media_group_id

    # -----------------------------------------------------
    # اگر اولین عکس یک آلبوم است
    # -----------------------------------------------------

    if media_group_id:

        current_group_id = context.user_data.get(
            "media_group_id"
        )

        # ---------------------------------------------
        # اولین عکس آلبوم
        # ---------------------------------------------

        if current_group_id is None:

            context.user_data[
                "media_group_id"
            ] = media_group_id

            current_group_id = media_group_id

            print(
                f"NEW MEDIA GROUP: {media_group_id}"
            )

        # ---------------------------------------------
        # اگر آلبوم دیگری آمد
        # ---------------------------------------------

        elif current_group_id != media_group_id:

            print(
                "Different media group ignored:"
                f" {media_group_id}"
            )

            return

        # ---------------------------------------------
        # جلوگیری از ذخیره تکراری
        # ---------------------------------------------

        photo_id = update.message.photo[-1].file_id

        if photo_id not in photos:

            photos.append(
                photo_id
            )

        context.user_data[
            "photos"
        ] = photos

        print(
            "ALBUM PHOTO RECEIVED | "
            f"group={media_group_id} | "
            f"count={len(photos)}"
        )

        # برای آلبوم به ازای هر عکس پیام نمی‌دهیم
        return

    # =====================================================
    # عکس معمولی
    # =====================================================

    photo_id = update.message.photo[-1].file_id

    if photo_id not in photos:

        photos.append(
            photo_id
        )

    context.user_data[
        "photos"
    ] = photos

    print(
        "SINGLE PHOTO RECEIVED | "
        f"count={len(photos)}"
    )

    await update.message.reply_text(
        f"✅ عکس شماره {len(photos)} دریافت شد.\n\n"
        "📸 اگر عکس دیگری داری بفرست.\n"
        "📝 وقتی تمام شد، پرامپت را بفرست.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# هندلر عکس
# =========================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # =====================================================
    # ساخت پرامپت با Gemini
    # =====================================================

    if context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):

        await generate_prompt_from_photo(
            update,
            context
        )

        return

    # =====================================================
    # دریافت عکس ادمین
    # =====================================================

    if (
        update.effective_user.id == ADMIN_ID
        and "photos" in context.user_data
    ):

        await receive_photo(
            update,
            context
        )

        return


# =========================================================
# دریافت پرامپت ادمین
# =========================================================

async def receive_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):
        return

    if "photos" not in context.user_data:
        return

    # =====================================================
    # گرفتن کپی عکس‌ها
    # =====================================================

    photos = list(
        context.user_data.get(
            "photos",
            []
        )
    )

    if not photos:

        await update.message.reply_text(
            "❌ هنوز هیچ عکسی دریافت نشده است.",
            reply_markup=get_main_keyboard()
        )

        return

    # =====================================================
    # پرامپت
    # =====================================================

    prompt = update.message.text

    if not prompt or not prompt.strip():

        await update.message.reply_text(
            "❌ پرامپت نمی‌تواند خالی باشد.",
            reply_markup=get_main_keyboard()
        )

        return

    prompt = prompt.strip()

    print(
        "========================================"
    )

    print(
        "POST START"
    )

    print(
        f"TOTAL PHOTOS: {len(photos)}"
    )

    print(
        f"MEDIA GROUP: "
        f"{context.user_data.get('media_group_id')}"
    )

    print(
        "========================================"
    )

    # =====================================================
    # ساخت ID
    # =====================================================

    prompt_id = uuid.uuid4().hex[:8]

    # =====================================================
    # ذخیره
    # =====================================================

    save_prompt(
        prompt_id,
        prompt,
        photos
    )

    # =====================================================
    # لینک
    # =====================================================

    bot_info = await context.bot.get_me()

    bot_username = bot_info.username

    link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?start={prompt_id}"
    )

    # =====================================================
    # دکمه
    # =====================================================

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✨ دریافت پرامپت",
                url=link
            )
        ]
    ])

    # =====================================================
    # ارسال به کانال
    # =====================================================

    try:

        # =================================================
        # فقط یک عکس
        # =================================================

        if len(photos) == 1:

            print(
                "SENDING ONE PHOTO"
            )

            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=photos[0],
                reply_markup=keyboard
            )

        # =================================================
        # چند عکس
        # =================================================

        else:

            print(
                f"SENDING ALBUM: {len(photos)} PHOTOS"
            )

            media = []

            for photo_id in photos:

                media.append(
                    InputMediaPhoto(
                        media=photo_id
                    )
                )

            # ---------------------------------------------
            # همه عکس‌ها در یک آلبوم
            # ---------------------------------------------

            await context.bot.send_media_group(
                chat_id=CHANNEL,
                media=media
            )

            print(
                "ALBUM SENT SUCCESSFULLY"
            )

            # ---------------------------------------------
            # دکمه جداگانه زیر آلبوم
            # ---------------------------------------------

            await context.bot.send_message(
                chat_id=CHANNEL,
                text="\u2063",
                reply_markup=keyboard
            )

            print(
                "BUTTON SENT SUCCESSFULLY"
            )

    except Exception as e:

        print(
            "CHANNEL SEND ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ خطا هنگام ارسال پست به کانال:\n\n"
            f"{e}",
            reply_markup=get_main_keyboard()
        )

        return

    # =====================================================
    # موفقیت
    # =====================================================

    await update.message.reply_text(
        "✅ پست با موفقیت در کانال منتشر شد!\n\n"
        f"📸 تعداد عکس‌ها: {len(photos)}\n"
        f"🆔 شناسه پرامپت: {prompt_id}",
        reply_markup=get_main_keyboard()
    )

    # =====================================================
    # پاک کردن اطلاعات موقت
    # =====================================================

    context.user_data.pop(
        "photos",
        None
    )

    context.user_data.pop(
        "media_group_id",
        None
    )


# =========================================================
# اجرای ربات
# =========================================================

def main():

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(60)
        .build()
    )

    # =====================================================
    # /start
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # =====================================================
    # /new
    # =====================================================

    app.add_handler(
        CommandHandler(
            "new",
            new_prompt
        )
    )

    # =====================================================
    # دکمه ساخت پرامپت
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & filters.Regex(
                f"^{PROMPT_BUTTON}$"
            ),
            prompt_from_photo_command
        )
    )

    # =====================================================
    # عکس
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    # =====================================================
    # متن
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            receive_prompt
        )
    )

    # =====================================================
    # بررسی عضویت
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern="^check_membership$"
        )
    )

    print(
        "Bot is running..."
    )

    app.run_polling()


# =========================================================
# شروع
# =========================================================

if __name__ == "__main__":

    main()