import os
import json
import requests
import base64
import random
import string
import threading
from datetime import datetime
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Load token from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Set this on Render
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")     # Set this on Render

JSON_URL = "https://raw.githubusercontent.com/WolfT31/LoginSystem/main/LoginID.json"
DEFAULT_DATE = "2025-10-10"
EXPORT_PATH = "exported_users.txt"

# ====== States for conversation ======
CHOOSING, ADDING = range(2)

# ===== Helper functions =====
def generate_random_password(length=4):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))

def generate_random_username():
    prefix = "wolf_"
    suffix = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8 - len(prefix)))
    return prefix + suffix

def load_users():
    try:
        response = requests.get(JSON_URL)
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, list) else data.get("users", [])
        return []
    except:
        return []

def save_users(users):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    sha_url = "https://api.github.com/repos/WolfT31/LoginSystem/contents/LoginID.json"
    sha_response = requests.get(sha_url, headers=headers)
    if sha_response.status_code != 200:
        return False
    sha = sha_response.json().get("sha", "")
    content = json.dumps(users, indent=2)
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    data = {
        "message": "Update user list",
        "content": encoded_content,
        "sha": sha
    }
    update_url = "https://api.github.com/repos/WolfT31/LoginSystem/contents/LoginID.json"
    put_response = requests.put(update_url, headers=headers, json=data)
    return put_response.status_code == 200

def get_days_left(expire_str):
    try:
        expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
        return (expire_date - datetime.now().date()).days
    except:
        return -999

# ===== Telegram Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🔐 *Login Management Bot*\n"
        "Available commands:\n"
        "/add - Add new user\n"
        "/remove - Remove user\n"
        "/check - Check user\n"
        "/list - List all users\n"
        "/export - Export users\n"
        "/summary - Show dashboard\n"
        "/generate - Generate random account"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    if not users:
        await update.message.reply_text("No users found.")
        return
    reply = "📋 *Approved Users:*\n"
    for user in users:
        days = get_days_left(user['expiresAt'])
        reply += f"🆔 {user['id']} | 👤 {user['username']} | ⏳ {days} days left\n"
    await update.message.reply_text(reply, parse_mode="Markdown")

async def generate_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = generate_random_username()
    password = generate_random_password()
    await update.message.reply_text(
        f"✅ *Generated Account:*\n👤 Username: `{username}`\n🔒 Password: `{password}`",
        parse_mode="Markdown"
    )

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    total = len(users)
    expired = sum(1 for u in users if get_days_left(u["expiresAt"]) < 0)
    active = total - expired
    msg = (
        f"📊 *Summary Dashboard:*\n"
        f"Total users: {total}\n"
        f"Active: {active}\n"
        f"Expired: {expired}\n"
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ===== Add User Conversation =====
async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send user data in format:\n`<id>,<username>,<password>,<expiresAt>,<allowOffline>`", parse_mode="Markdown")
    return ADDING

async def add_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(",")
    if len(parts) != 5:
        await update.message.reply_text("❌ Invalid format. Please send:\n`id,username,password,expiresAt,allowOffline`", parse_mode="Markdown")
        return ADDING

    device_id, username, password, expiresAt, allowOffline = [p.strip() for p in parts]
    allowOffline = allowOffline.lower() == "true"

    users = load_users()
    if any(user["id"] == device_id for user in users):
        await update.message.reply_text("❌ This device ID already exists.")
        return ConversationHandler.END

    try:
        datetime.strptime(expiresAt, "%Y-%m-%d")
        users.append({
            "id": device_id,
            "username": username,
            "password": password,
            "expiresAt": expiresAt,
            "allowOffline": allowOffline
        })
        if save_users(users):
            await update.message.reply_text(f"✅ User `{username}` added successfully!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Failed to update database.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

    return ConversationHandler.END

# ===== Remove User =====
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: `/remove <device_id>`", parse_mode="Markdown")
        return
    device_id = context.args[0]
    users = load_users()
    updated = [u for u in users if u["id"] != device_id]
    if len(users) == len(updated):
        await update.message.reply_text("❌ User not found.")
        return
    if save_users(updated):
        await update.message.reply_text("✅ User removed successfully.")
    else:
        await update.message.reply_text("❌ Failed to update database.")

# ===== Export Users =====
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    lines = []
    for user in users:
        days_left = get_days_left(user["expiresAt"])
        lines.append(f"{user['id']}, {user['username']}, {user['expiresAt']}, {user['allowOffline']}, {days_left} days left")
    path = EXPORT_PATH
    with open(path, "w") as f:
        f.write("\n".join(lines))
    await update.message.reply_document(open(path, "rb"))

# ===== Telegram Bot Init =====
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("generate", generate_account))
    app.add_handler(CommandHandler("remove", remove_user))
    app.add_handler(CommandHandler("export", export))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_user_start)],
        states={ADDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_process)]},
        fallbacks=[],
    )
    app.add_handler(conv_handler)

    print("✅ Bot is polling...")
    app.run_polling()

# ===== Minimal Flask App to expose a port =====
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "✅ Bot is running!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=10000)

# ===== Run Both =====
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
