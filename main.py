import os
import logging
import sqlite3
import shutil
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)
import yt_dlp
import asyncio

# ===== إعدادات =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

# يمكن تغييره من Railway Environment
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "@hos_ine")

logging.basicConfig(level=logging.INFO)

# ===== حماية من السبام =====
user_last_download = {}
DOWNLOAD_DELAY = 10

# ===== قاعدة البيانات =====
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    join_date TEXT,
    banned INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    downloads INTEGER DEFAULT 0
)
""")

cursor.execute("INSERT OR IGNORE INTO stats (rowid, downloads) VALUES (1,0)")
conn.commit()

# ===== دوال قاعدة البيانات =====
def add_user(user_id, username):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
        (user_id, username, datetime.now().isoformat())
    )
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row and row[0] == 1

def get_users_count():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

def increase_downloads():
    cursor.execute("UPDATE stats SET downloads = downloads + 1 WHERE rowid=1")
    conn.commit()

def get_downloads():
    cursor.execute("SELECT downloads FROM stats WHERE rowid=1")
    return cursor.fetchone()[0]

def get_all_users():
    cursor.execute("SELECT user_id FROM users WHERE banned=0")
    return cursor.fetchall()

# ===== تحميل الفيديو (نسخة قوية شاملة) =====
def download_video(url):

    # تنظيف المجلد إذا كبر
    if os.path.exists("downloads") and len(os.listdir("downloads")) > 30:
        shutil.rmtree("downloads")

    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        # أفضل فيديو + أفضل صوت ثم دمج
        'format': 'bv*+ba/best',
        'merge_output_format': 'mp4',

        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'nocheckcertificate': True,
        'geo_bypass': True,

        # إعادة المحاولة عند الخطأ
        'retries': 3,
        'fragment_retries': 3,

        # تحسين دعم إنستغرام
        'http_headers': {
            'User-Agent': 'Mozilla/5.0'
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # منع الفيديوهات الطويلة أكثر من 30 دقيقة (اختياري)
        if info.get("duration") and info["duration"] > 1800:
            raise Exception("الفيديو طويل جداً")

        # الحصول على الاسم الحقيقي بعد الدمج
        filename = ydl.prepare_filename(info)

        # إذا تم الدمج يتحول الامتداد إلى mp4
        if not filename.endswith(".mp4"):
            filename = os.path.splitext(filename)[0] + ".mp4"

        return filename

# ===== لوحة تحكم =====
def admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
        [InlineKeyboardButton("📢 إذاعة", callback_data="broadcast")],
        [InlineKeyboardButton("❌ إغلاق", callback_data="close")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== أوامر =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username)

    if is_banned(user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت")
        return

    await update.message.reply_text(
        f"🔥 مرحبًا {user.first_name}\n\n"
        "🎬 أرسل رابط:\n"
        "• TikTok\n"
        "• Instagram\n"
        "• YouTube\n\n"
        "⚡ التحميل بجودة عالية\n"
        "⏳ يوجد انتظار 10 ثواني بين كل تحميل\n\n"
        f"👨‍💻 المطور: {DEVELOPER_USERNAME}"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 لوحة تحكم الأدمن",
            reply_markup=admin_keyboard()
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "stats":
        await query.edit_message_text(
            f"📊 عدد المستخدمين: {get_users_count()}\n"
            f"📥 عدد التحميلات: {get_downloads()}",
            reply_markup=admin_keyboard()
        )

    elif query.data == "broadcast":
        await query.edit_message_text("📢 أرسل الرسالة الآن ليتم بثها لكل المستخدمين")
        context.user_data["broadcast"] = True

    elif query.data == "close":
        await query.delete_message()

# ===== معالجة الرسائل =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if is_banned(user_id):
        await update.message.reply_text("🚫 أنت محظور")
        return

    # بث جماعي
    if context.user_data.get("broadcast") and user_id == ADMIN_ID:
        users = get_all_users()
        for user in users:
            try:
                await context.bot.send_message(chat_id=user[0], text=update.message.text)
            except:
                pass
        context.user_data["broadcast"] = False
        await update.message.reply_text("✅ تم الإرسال للجميع")
        return

    # منع السبام
    current_time = datetime.now().timestamp()
    last_time = user_last_download.get(user_id, 0)

    if current_time - last_time < DOWNLOAD_DELAY:
        remaining = int(DOWNLOAD_DELAY - (current_time - last_time))
        await update.message.reply_text(f"⏳ انتظر {remaining} ثانية")
        return

    url = update.message.text
    supported_sites = ["tiktok.com", "instagram.com", "youtube.com", "youtu.be"]

    if any(site in url for site in supported_sites):

        user_last_download[user_id] = current_time
        await update.message.reply_text("⏳ جاري التحميل...")

        try:
            filename = await asyncio.to_thread(download_video, url)

            with open(filename, "rb") as video:
                await update.message.reply_video(
                    video=video,
                    supports_streaming=True,
                    caption="✅ تم التحميل بنجاح"
                )

            os.remove(filename)
            increase_downloads()

        except Exception as e:
            await update.message.reply_text("❌ فشل التحميل")
            print(e)

    else:
        await update.message.reply_text("⚠️ أرسل رابط فيديو صالح فقط")

# ===== تسجيل =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("admin", admin_panel))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ===== Webhook =====
@app_fastapi.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app_fastapi.on_event("startup")
async def startup():
    await telegram_app.initialize()
    await telegram_app.start()

    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(WEBHOOK_URL + "/webhook")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=PORT)