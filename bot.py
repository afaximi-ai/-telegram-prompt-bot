import os
import uuid
import json
import sqlite3
import asyncio

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
    ReplyKeyboardRemove,
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

    cursor.execute(
        """
        INSERT INTO prompts
        (id, prompt, photo_id)
        VALUES (?, ?, ?)
        """,
        (
            prompt_id,
            prompt,
            json.dumps(photo_ids)
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

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    PROMPT_BUTTON
                )
            ]
        ],
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
# ارسال پرامپت
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

        context.user_data[
            "pending_prompt_id"
        ] = context.args[0]

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
# ساخت پرامپت از عکس
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
        "album_groups",
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

        await send_prompt_result(
            update,
            generated_prompt.strip()
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

    try:

        member = await context.bot.get_chat_member(
            chat_id=CHANNEL,
            user_id=query.from_user.id
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
        "album_groups"
    ] = {}

    context.user_data[
        "collecting_post"
    ] = True

    await update.message.reply_text(
        "📸 عکس‌ها را بفرست یا یک آلبوم را از کانال دیگر Forward کن.\n\n"
        "حداکثر ۱۰ عکس برای یک پست.\n\n"
        "بعد از تمام شدن عکس‌ها، پرامپت را بفرست.",
        reply_markup=get_main_keyboard()
    )


# =========================================================
# آماده‌سازی خودکار پست
# =========================================================

async def start_collecting_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):
        return

    context.user_data[
        "collecting_post"
    ] = True


# =========================================================
# ذخیره عکس
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

    context.user_data[
        "collecting_post"
    ] = True

    photos = context.user_data.setdefault(
        "photos",
        []
    )

    album_groups = context.user_data.setdefault(
        "album_groups",
        {}
    )

    # =====================================================
    # تشخیص آلبوم
    # =====================================================

    media_group_id = update.message.media_group_id

    if media_group_id:

        group = album_groups.setdefault(
            media_group_id,
            []
        )

        photo_id = update.message.photo[-1].file_id

        if photo_id not in group:

            group.append(
                photo_id
            )

        if len(group) <= 10:

            context.user_data[
                "photos"
            ] = group.copy()

        print(
            "ALBUM:",
            media_group_id,
            "PHOTO COUNT:",
            len(group)
        )

        await asyncio.sleep(1.5)

        current_group = album_groups.get(
            media_group_id,
            []
        )

        if (
            current_group
            and
            photo_id == current_group[-1]
        ):

            await update.message.reply_text(
                f"✅ {len(current_group)} عکس دریافت شد.\n\n"
                "📝 حالا پرامپت را بفرست تا عکس‌ها و پرامپت را باهم در کانال منتشر کنم.",
                reply_markup=get_main_keyboard()
            )

        return

    # =====================================================
    # عکس تکی
    # =====================================================

    photo_id = update.message.photo[-1].file_id

    if photo_id not in photos:

        photos.append(
            photo_id
        )

    if len(photos) > 10:

        photos.pop()

        await update.message.reply_text(
            "❌ حداکثر ۱۰ عکس برای هر پست مجاز است.",
            reply_markup=ReplyKeyboardRemove()
        )

        return

    # =====================================================
    # فقط عکس تکی
    # حذف کامل کیبورد پایین تلگرام
    # =====================================================

    await update.message.reply_text(
        "📝 پرامپت را بفرست تا عکس و پرامپت را باهم در کانال منتشر کنم.",
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# هندلر عکس
# =========================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if context.user_data.get(
        "waiting_for_prompt_from_photo"
    ):

        await generate_prompt_from_photo(
            update,
            context
        )

        return

    if update.effective_user.id == ADMIN_ID:

        await receive_photo(
            update,
            context
        )

        return


# =========================================================
# دریافت پرامپت
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

    photos = list(
        context.user_data.get(
            "photos",
            []
        )
    )

    if not photos:

        return

    prompt = update.message.text

    if not prompt or not prompt.strip():

        return

    prompt = prompt.strip()

    if len(photos) > 10:

        photos = photos[:10]

    print(
        "======================================"
    )

    print(
        "NEW POST"
    )

    print(
        "PHOTOS:",
        len(photos)
    )

    print(
        "======================================"
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
    # لینک ربات
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
    # ارسال کانال
    # =====================================================

    try:

        if len(photos) == 1:

            # =================================================
            # عکس تکی:
            # دکمه مستقیماً زیر خود عکس قرار می‌گیرد
            # هیچ پیام خالی یا پیام جداگانه‌ای ایجاد نمی‌شود
            # =================================================

            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=photos[0],
                reply_markup=keyboard
            )

        else:

            # =================================================
            # آلبوم چندعکسی
            # =================================================

            media = []

            for photo_id in photos:

                media.append(
                    InputMediaPhoto(
                        media=photo_id
                    )
                )

            await context.bot.send_media_group(
                chat_id=CHANNEL,
                media=media
            )

            # برای آلبوم، دکمه جداگانه ارسال می‌شود
            await context.bot.send_message(
                chat_id=CHANNEL,
                text="✨ دریافت پرامپت",
                reply_markup=keyboard
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
    # پاک کردن پست فعلی
    # =====================================================

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
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(60)
        .build()
    )

    # =====================================================
    # START
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # =====================================================
    # NEW
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