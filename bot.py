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
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CopyTextButton,
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


def save_prompt(prompt_id, prompt, photo_ids):

    conn = get_db_connection()
    cursor = conn.cursor()

    photo_ids_json = json.dumps(photo_ids)

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
            KeyboardButton(PROMPT_BUTTON)
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

    except Exception:

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
# ارسال پرامپت + Copy
# =========================================================

async def send_prompt_result(
    update: Update,
    prompt: str
):

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
            "✨ پرامپت ساخته شد:\n\n"
            + prompt,
            reply_markup=keyboard
        )

    else:

        await update.message.reply_text(
            "✨ پرامپت ساخته شد:\n\n"
            + prompt
            + "\n\n"
            "📋 برای کپی کردن، روی متن پیام نگه دار "
            "و گزینه Copy را بزن.",
            reply_markup=get_main_keyboard()
        )


# =========================================================
# /start
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
# بررسی عضویت دوباره
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

        is_joined = member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception:

        is_joined = False

    if not is_joined:

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
                    "✨ پرامپت:\n\n"
                    + prompt,
                    reply_markup=keyboard
                )

            else:

                await query.message.reply_text(
                    "✨ پرامپت:\n\n"
                    + prompt
                    + "\n\n"
                    "📋 برای کپی کردن، روی متن پیام نگه دار "
                    "و گزینه Copy را بزن.",
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

    await update.message.reply_text(
        "📸 حالا عکس‌ها را یکی‌یکی بفرست.\n\n"
        "می‌توانی چند عکس بفرستی.\n"
        "حداکثر ۱۰ عکس برای یک پست.\n\n"
        "بعد از تمام شدن عکس‌ها، پرامپت را بفرست.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# دریافت عکس‌های /new
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

    photos = context.user_data[
        "photos"
    ]

    if len(photos) >= 10:

        await update.message.reply_text(
            "❌ برای یک پست حداکثر ۱۰ عکس می‌توانی بفرستی.\n\n"
            "حالا پرامپت را بفرست.",
            reply_markup=get_main_keyboard()
        )

        return

    photo_id = update.message.photo[-1].file_id

    photos.append(
        photo_id
    )

    count = len(photos)

    await update.message.reply_text(
        f"✅ عکس شماره {count} دریافت شد.\n\n"
        "📸 اگر عکس دیگری داری بفرست.\n"
        "📝 وقتی تمام شد، پرامپت را بفرست.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# دریافت پرامپت ادمین و ارسال به کانال
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

    photos = context.user_data[
        "photos"
    ]

    if not photos:

        await update.message.reply_text(
            "❌ هنوز هیچ عکسی دریافت نشده است.",
            reply_markup=get_main_keyboard()
        )

        return

    prompt = update.message.text

    if not prompt or not prompt.strip():

        await update.message.reply_text(
            "❌ پرامپت نمی‌تواند خالی باشد.",
            reply_markup=get_main_keyboard()
        )

        return

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
    # ساخت لینک
    # =====================================================

    bot_username = (
        await context.bot.get_me()
    ).username

    link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?start={prompt_id}"
    )

    # =====================================================
    # دکمه دریافت پرامپت
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
    # ارسال
    # =====================================================

    try:

        # -------------------------------------------------
        # یک عکس
        # -------------------------------------------------

        if len(photos) == 1:

            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=photos[0],
                reply_markup=keyboard
            )

        # -------------------------------------------------
        # چند عکس
        # -------------------------------------------------

        else:

            media_group = []

            for photo_id in photos:

                media_group.append(
                    InputMediaPhoto(
                        media=photo_id
                    )
                )

            sent_messages = (
                await context.bot.send_media_group(
                    chat_id=CHANNEL,
                    media=media_group
                )
            )

            # -------------------------------------------------
            # دکمه روی عکس اول آلبوم
            # -------------------------------------------------

            first_message = sent_messages[0]

            try:

                await context.bot.edit_message_reply_markup(
                    chat_id=CHANNEL,
                    message_id=first_message.message_id,
                    reply_markup=keyboard
                )

            except Exception as e:

                error_text = str(e).lower()

                # اگر تلگرام گفت چیزی تغییر نکرده،
                # آن را خطای واقعی حساب نمی‌کنیم.
                if "message is not modified" not in error_text:

                    print(
                        "Keyboard error:",
                        repr(e)
                    )

                    await update.message.reply_text(
                        "⚠️ عکس‌ها ارسال شدند، "
                        "اما دکمه روی عکس اول قرار نگرفت.",
                        reply_markup=get_main_keyboard()
                    )

                    context.user_data.clear()

                    return

    except Exception as e:

        print(
            "Channel send error:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ خطا هنگام ارسال عکس به کانال:\n\n"
            f"{e}",
            reply_markup=get_main_keyboard()
        )

        return

    # =====================================================
    # پیام موفقیت
    # =====================================================

    await update.message.reply_text(
        "✅ پست با موفقیت در کانال منتشر شد!\n\n"
        f"📸 تعداد عکس‌ها: {len(photos)}",
        reply_markup=get_main_keyboard()
    )

    # پاک کردن اطلاعات
    context.user_data.clear()


# =========================================================
# اجرای ربات
# =========================================================

def main():

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
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
    # عکس برای Gemini
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            generate_prompt_from_photo
        )
    )

    # =====================================================
    # عکس برای /new
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo
        )
    )

    # =====================================================
    # متن پرامپت ادمین
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            receive_prompt
        )
    )

    # =====================================================
    # عضویت
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