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
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "@hos_ine")

logging.basicConfig(level=logging.INFO)

# ===== إنشاء FastAPI + Telegram =====
app_fastapi = FastAPI()
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# ===== حماية من السبام =====
user_last_download = {}
DOWNLOAD_DELAY = 5

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

# ===== تحميل الفيديو (محسن لRailway + YouTube) =====
def download_video(url):

    if os.path.exists("downloads") and len(os.listdir("downloads")) > 30:
        shutil.rmtree("downloads")

    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "format": "b[height<=720][ext=mp4]/best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "retries": 15,
        "fragment_retries": 15,
        "concurrent_fragment_downloads": 5,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0"
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if info.get("duration") and info["duration"] > 2400:
            raise Exception("الفيديو طويل جداً")

        return ydl.prepare_filename(info)

# ===== واجهة رئيسية =====
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎬 طريقة الاستخدام", callback_data="how")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="public_stats")],
        [InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME.replace('@','')}")],
        [InlineKeyboardButton("✖️ إغلاق", callback_data="close_start")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== أوامر =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    with open("intro.mp4", "rb") as video:
        await context.bot.send_video(
            chat_id=chat_id,
            video=video,
            caption="🎬 أهلاً بك في أقوى بوت تحميل 🔥\n\nأرسل رابط TikTok / Instagram / YouTube 🚀"
        )
    user = update.effective_user
    add_user(user.id, user.username)

    if is_banned(user.id):
        await update.message.reply_text("🚫 أنت محظور")
        return

    text = f"""
╔═════════════════════════╗
    ㅤㅤ  🎬 𝗩𝗜𝗗𝗘𝗢 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗥  
╠═════════════════════════╣

ㅤ😍 أهلاً بك عزيزي {user.first_name}

ㅤ📥 المنصات المدعومة:
ㅤ• TikTok
ㅤ• Instagram
ㅤ• YouTube 

ㅤ⚡ الجودة: حتى 1080
ㅤ⏳  الانتظار: 5 ثواني لي كل تحميل

ㅤ🚀 سرعة عالية — بدون علامة مائية

╚═════════════════════════╝
"""

    await update.message.reply_text(text, reply_markup=main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "how":
        await query.edit_message_text(
            """
🎬 طريقة الاستخدام:

1️⃣ أرسل رابط فيديو مباشر  
2️⃣ انتظر قليلاً  
3️⃣ سيصلك الفيديو فوراً  

⚡الجودة: 1080
""",
            reply_markup=main_keyboard()
        )

    elif query.data == "public_stats":
        await query.edit_message_text(
            f"""
📊 إحصائيات البوت:

👥 المستخدمين: {get_users_count()}
📥 التحميلات: {get_downloads()}
""",
            reply_markup=main_keyboard()
        )

    elif query.data == "close_start":
        await query.delete_message()

# ===== معالجة الرسائل =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if is_banned(user_id):
        await update.message.reply_text("🚫 أنت محظور")
        return

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
            filesize = os.path.getsize(filename)

            with open(filename, "rb") as video:
                if filesize < 50 * 1024 * 1024:
                    await update.message.reply_video(video=video, supports_streaming=True)
                else:
                    await update.message.reply_document(document=video)

            os.remove(filename)
            increase_downloads()

        except Exception as e:
            await update.message.reply_text("❌ فشل التحميل")
            print(e)

    else:
        await update.message.reply_text("⚠️ أرسل رابط فيديو صالح فقط")

# ===== تسجيل =====
telegram_app.add_handler(CommandHandler("start", start))
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