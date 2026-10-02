import os
import re
import time
import sqlite3
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from pydub import AudioSegment
import telebot
from telebot import types

# --- خادم صغير لإبقاء Render راضياً وشغالاً ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running 24/7!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# --- إعدادات البوت والبيانات ---
BOT_TOKEN = "8604985808:AAGqxFBZTx9RFs8XIqfg7dr_nlsYMl-vCcE"
DEFAULT_VOICE_ID = "c3e5d81d807f4cbc9a0c2872a4dea9ea"
INITIAL_API_KEY = "sk-fish-s2GZTsNwOwqn5hM1T-f3RivFQEHvpegZpLO1xPY4Dwc"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

conn = sqlite3.connect("bot_storage.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, api_key TEXT, voice_id TEXT)")
conn.commit()

user_states = {}

def get_user(user_id):
    cursor.execute("SELECT api_key, voice_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return {"api_key": row[0], "voice_id": row[1]}
    save_user(user_id, INITIAL_API_KEY, DEFAULT_VOICE_ID)
    return {"api_key": INITIAL_API_KEY, "voice_id": DEFAULT_VOICE_ID}

def save_user(user_id, api_key, voice_id):
    cursor.execute("INSERT INTO users VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET api_key=excluded.api_key, voice_id=excluded.voice_id", (user_id, api_key, voice_id))
    conn.commit()

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔑 تبديل مفتاح الـ API", "🎙️ تغيير الصوت")
    markup.row("ℹ️ بيانات حسابي")
    return markup

def split_text(text, max_len=380):
    sentences = re.split(r'([.،؟!\n]+)', text)
    chunks, current = [], ""
    for part in sentences:
        if len(current) + len(part) < max_len:
            current += part
        else:
            if current.strip():
                chunks.append(current.strip())
            current = part
    if current.strip():
        chunks.append(current.strip())
    return chunks

@bot.message_handler(commands=['start'])
def start_cmd(message):
    get_user(message.chat.id)
    bot.send_message(
        message.chat.id,
        "👋 **أهلاً بك! البوت شغال سحابياً 24 ساعة.**\n\nأرسل قصتك وسيقوم الراوي السعودي بسردها مدمجة بالكامل.",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text in ["🔑 تبديل مفتاح الـ API", "🎙️ تغيير الصوت", "ℹ️ بيانات حسابي"])
def handle_menu(message):
    user_id = message.chat.id
    if message.text == "🔑 تبديل مفتاح الـ API":
        user_states[user_id] = "WAITING_API"
        bot.send_message(user_id, "📥 أرسل مفتاح الـ API الجديد:")
    elif message.text == "🎙️ تغيير الصوت":
        user_states[user_id] = "WAITING_VOICE"
        bot.send_message(user_id, "🎙️ أرسل الـ Voice ID الجديد:")
    elif message.text == "ℹ️ بيانات حسابي":
        user = get_user(user_id)
        masked_key = user["api_key"][:10] + "..." + user["api_key"][-4:]
        bot.send_message(user_id, f"📋 **بياناتك:**\n- API: `{masked_key}`\n- الصوت: `{user['voice_id']}`")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    state = user_states.get(user_id)

    if state == "WAITING_API":
        save_user(user_id, message.text.strip(), get_user(user_id)["voice_id"])
        user_states[user_id] = None
        bot.send_message(user_id, "✅ تم حفظ المفتاح الجديد بنجاح!", reply_markup=main_keyboard())
        return

    if state == "WAITING_VOICE":
        save_user(user_id, get_user(user_id)["api_key"], message.text.strip())
        user_states[user_id] = None
        bot.send_message(user_id, "✅ تم تحديث الصوت بنجاح!", reply_markup=main_keyboard())
        return

    user = get_user(user_id)
    chunks = split_text(message.text.strip())
    status_msg = bot.send_message(user_id, f"⏳ جاري معالجة وتوليد ({len(chunks)}) مقاطع صوتية...")

    headers = {"Authorization": f"Bearer {user['api_key']}", "Content-Type": "application/json"}
    audio_segments, temp_files = [], []

    for i, chunk in enumerate(chunks):
        payload = {"text": chunk, "reference_id": user["voice_id"], "format": "mp3"}
        try:
            res = requests.post("https://api.fish.audio/v1/tts", json=payload, headers=headers, timeout=60)
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ بالاتصال: {e}")
            return

        if res.status_code in [401, 402, 429]:
            bot.delete_message(user_id, status_msg.message_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔑 إدخال مفتاح جديد الآن", callback_data="change_api"))
            bot.send_message(user_id, "⚠️ **انتهى رصيد المفتاح!** اضغط بالأسفل للتحديث:", reply_markup=markup)
            return
        elif res.status_code != 200:
            bot.send_message(user_id, f"❌ خطأ ({res.status_code}): {res.text}")
            return

        part_file = f"chunk_{user_id}_{i}.mp3"
        with open(part_file, "wb") as f:
            f.write(res.content)
        temp_files.append(part_file)
        audio_segments.append(AudioSegment.from_file(part_file))
        time.sleep(0.5)

    if audio_segments:
        final_audio = audio_segments[0]
        for seg in audio_segments[1:]:
            final_audio += seg

        final_path = f"story_{user_id}.mp3"
        final_audio.export(final_path, format="mp3")
        bot.delete_message(user_id, status_msg.message_id)
        with open(final_path, "rb") as audio:
            bot.send_audio(user_id, audio, title="القصة الكاملة", performer="الراوي السعودي")

        if os.path.exists(final_path): os.remove(final_path)
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

@bot.callback_query_handler(func=lambda call: call.data == "change_api")
def callback_api(call):
    user_states[call.message.chat.id] = "WAITING_API"
    bot.send_message(call.message.chat.id, "📥 أرسل مفتاح الـ API الجديد:")

while True:
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception as e:
        time.sleep(5)
