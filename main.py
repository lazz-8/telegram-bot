import os
import logging
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# ===== إعدادات =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

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
        'format': 'best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ===== التحقق من الاشتراك =====
async def check_subscription(update, context):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
    if chat_member.status in ["member", "administrator", "creator"]:
        return True
    else:
        await update.message.reply_text(f"🚫 اشترك أولاً في القناة:\n{CHANNEL_USERNAME}")
        return False

# ===== FastAPI =====
app_fastapi = FastAPI()
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, update.effective_user.username)
    if not await check_subscription(update, context):
        return
    await update.message.reply_text("🔥 أرسل رابط TikTok أو Instagram")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"📊 المستخدمين: {get_users_count()}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return

    url = update.message.text

    if "tiktok.com" in url or "instagram.com" in url:
        await update.message.reply_text("⏳ جاري التحميل...")
        try:
            filename = download_video(url)
            await update.message.reply_video(video=open(filename, "rb"))
            os.remove(filename)
        except:
            await update.message.reply_text("❌ فشل التحميل")
    else:
        await update.message.reply_text("⚠️ رابط غير صالح")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("stats", stats))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app_fastapi.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app_fastapi.on_event("startup")
async def startup():
    await telegram_app.bot.set_webhook(WEBHOOK_URL + "/webhook")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=PORT)
