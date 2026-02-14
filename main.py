import os
import logging
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
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
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
                   (user_id, username, datetime.now().isoformat()))
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row and row[0] == 1

def ban_user(user_id):
    cursor.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()

def unban_user(user_id):
    cursor.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()

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
        "🎬 أرسل رابط TikTok / Instagram / YouTube\n"
        "⚡ وسيتم التحميل بجودة عالية فورًا"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
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

# ===== بث =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if is_banned(user_id):
        await update.message.reply_text("🚫 أنت محظور")
        return

    # بث
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

    url = update.message.text

    if any(x in url for x in ["tiktok.com", "instagram.com", "youtube.com", "youtu.be"]):
        await update.message.reply_text("⏳ جاري التحميل...")

        try:
            filename = download_video(url)

            with open(filename, "rb") as video:
                await update.message.reply_video(video=video, supports_streaming=True)

            os.remove(filename)
            increase_downloads()

        except Exception as e:
            await update.message.reply_text("❌ فشل التحميل")
            print(e)
    else:
        await update.message.reply_text("⚠️ أرسل رابط صالح فقط")

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
    await telegram_app.bot.set_webhook(WEBHOOK_URL + "/webhook")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=PORT)