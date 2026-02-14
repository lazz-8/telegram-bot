import os
import logging
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# ===== إعدادات =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

DEVELOPER_USERNAME = "@hos_ine"

logging.basicConfig(level=logging.INFO)

# ===== قاعدة البيانات =====
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    join_date TEXT
)
""")

def add_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
                   (user_id, username, datetime.now().isoformat()))
    conn.commit()

def get_users_count():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

# ===== تحميل الفيديو =====
def download_video(url):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ===== FastAPI =====
app_fastapi = FastAPI()
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# ===== أزرار =====
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎬 تحميل فيديو", url="https://t.me/{}".format(telegram_app.bot.username))],
        [InlineKeyboardButton("👤 المطور", url=f"https://t.me/{DEVELOPER_USERNAME.replace('@','')}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== أوامر =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, update.effective_user.username)

    await update.message.reply_text(
        "🚀 مرحبًا بك في بوت تحميل الفيديوهات\n\n"
        "📥 يدعم:\n"
        "• TikTok\n"
        "• Instagram\n"
        "• YouTube\n"
        "• YouTube Shorts\n\n"
        "✨ فقط أرسل الرابط وسيتم التحميل فورًا.",
        reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 طريقة الاستخدام:\n"
        "1️⃣ أرسل رابط الفيديو\n"
        "2️⃣ انتظر قليلاً\n"
        "3️⃣ سيتم إرسال الفيديو بجودة جيدة\n\n"
        "💡 البوت يعمل 24/7"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"📊 عدد المستخدمين: {get_users_count()}")

# ===== معالجة الروابط =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text

    if any(x in url for x in ["tiktok.com", "instagram.com", "youtube.com", "youtu.be"]):
        await update.message.reply_text("⏳ جاري التحميل...")

        try:
            filename = download_video(url)

            with open(filename, "rb") as video:
                await update.message.reply_video(
                    video=video,
                    supports_streaming=True
                )

            os.remove(filename)

        except Exception as e:
            await update.message.reply_text("❌ فشل التحميل")
            print(e)

    else:
        await update.message.reply_text("⚠️ أرسل رابط صالح فقط")

# ===== تسجيل الهاندلرز =====
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(CommandHandler("stats", stats))
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
    await telegram_app.bot.set_webhook(WEBHOOK_URL + "/webhook")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=PORT)