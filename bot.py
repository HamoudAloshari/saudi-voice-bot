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

# ----------------- خادم Render لإبقاء البوت شغالاً 24/7 -----------------
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Live 24/7!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ----------------- البيانات الافتراضية -----------------
BOT_TOKEN = "8604985808:AAGqxFBZTx9RFs8XIqfg7dr_nlsYMl-vCcE"
FISH_VOICE_ID = "c3e5d81d807f4cbc9a0c2872a4dea9ea"
ELEVEN_VOICE_ID = "OoE8swS3hImZANNOodf6"

DEFAULT_FISH_KEY = "sk-fish-s2GZTsNwOwqn5hM1T-f3RivFQEHvpegZpLO1xPY4Dwc"
DEFAULT_ELEVEN_KEY = "sk_bda49de5150802a42f5a3c6ec27990fc92e6cf411a8525c9"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ----------------- قاعدة البيانات -----------------
conn = sqlite3.connect("bot_storage_v4.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    engine TEXT DEFAULT 'eleven',
    fish_key TEXT,
    eleven_key TEXT
)
""")
conn.commit()

user_states = {}

def get_user(user_id):
    cursor.execute("SELECT engine, fish_key, eleven_key FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return {"engine": row[0], "fish_key": row[1], "eleven_key": row[2]}
    # جعل ElevenLabs الافتراضي
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, 'eleven', ?, ?)", (user_id, DEFAULT_FISH_KEY, DEFAULT_ELEVEN_KEY))
    conn.commit()
    return {"engine": "eleven", "fish_key": DEFAULT_FISH_KEY, "eleven_key": DEFAULT_ELEVEN_KEY}

def update_user_engine(user_id, engine):
    cursor.execute("UPDATE users SET engine = ? WHERE user_id = ?", (engine, user_id))
    conn.commit()

def update_user_key(user_id, key_type, key_value):
    if key_type == "fish":
        cursor.execute("UPDATE users SET fish_key = ?, engine = 'fish' WHERE user_id = ?", (key_value, user_id))
    else:
        cursor.execute("UPDATE users SET eleven_key = ?, engine = 'eleven' WHERE user_id = ?", (key_value, user_id))
    conn.commit()

def main_keyboard(engine):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    engine_name = "⚡ ElevenLabs" if engine == "eleven" else "🐟 Fish Audio"
    markup.row(f"🔄 المنصة الحالية: {engine_name}")
    markup.row("🔑 مفتاح ElevenLabs", "🔑 مفتاح Fish Audio")
    markup.row("ℹ️ فحص حسابي")
    return markup

def split_text(text, max_len=350):
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

# ----------------- أوامر البوت -----------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    get_user(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("⚡ استخدام ElevenLabs", callback_data="set_eleven"),
        types.InlineKeyboardButton("🐟 استخدام Fish Audio", callback_data="set_fish")
    )
    bot.send_message(
        message.chat.id,
        "👋 **أهلاً بك في بوت الراوي المزدوج!**\n\n"
        "تم ضبط جميع المفاتيح بنجاح.\n"
        "👇 اختر المنصة التي تفضلها للبدء:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data in ["set_fish", "set_eleven"])
def callback_set_engine(call):
    engine = "fish" if call.data == "set_fish" else "eleven"
    update_user_engine(call.message.chat.id, engine)
    name = "Fish Audio 🐟" if engine == "fish" else "ElevenLabs ⚡"
    bot.answer_callback_query(call.id, f"تم ضبط {name}")
    bot.send_message(
        call.message.chat.id,
        f"✅ **أنت الآن تعمل رسمياً على: {name}**\n\nأرسل أي نص الآن وسأحوله بصوت الراوي المدمج فوراً.",
        reply_markup=main_keyboard(engine)
    )

@bot.message_handler(func=lambda msg: msg.text.startswith("🔄 المنصة الحالية") or msg.text in ["🔑 مفتاح Fish Audio", "🔑 مفتاح ElevenLabs", "ℹ️ فحص حسابي"])
def handle_menu_actions(message):
    user_id = message.chat.id
    user_states[user_id] = None  # إلغاء أي حالة انتظار سابقة فوراً
    user = get_user(user_id)

    if message.text.startswith("🔄 المنصة الحالية"):
        new_engine = "fish" if user["engine"] == "eleven" else "eleven"
        update_user_engine(user_id, new_engine)
        name = "ElevenLabs ⚡" if new_engine == "eleven" else "Fish Audio 🐟"
        bot.send_message(user_id, f"✅ **تم التحويل فوراً إلى: {name}**", reply_markup=main_keyboard(new_engine))

    elif message.text == "🔑 مفتاح ElevenLabs":
        user_states[user_id] = "WAITING_ELEVEN_KEY"
        bot.send_message(user_id, "📥 أرسل مفتاح **ElevenLabs** وسأحفظه وأحوّل المنصة عليه فوراً:", reply_markup=types.ReplyKeyboardRemove())

    elif message.text == "🔑 مفتاح Fish Audio":
        user_states[user_id] = "WAITING_FISH_KEY"
        bot.send_message(user_id, "📥 أرسل مفتاح **Fish Audio** وسأحفظه وأحوّل المنصة عليه فوراً:", reply_markup=types.ReplyKeyboardRemove())

    elif message.text == "ℹ️ فحص حسابي":
        f_key = user["fish_key"][:8] + "..." if user["fish_key"] else "غير مضاف"
        e_key = user["eleven_key"][:8] + "..." if user["eleven_key"] else "غير مضاف"
        curr = "ElevenLabs ⚡" if user["engine"] == "eleven" else "Fish Audio 🐟"
        bot.send_message(
            user_id,
            f"📋 **بيانات حسابك الحالية:**\n- المنصة النشطة الآن: `{curr}`\n- مفتاح Eleven: `{e_key}`\n- مفتاح Fish: `{f_key}`"
        )

# ----------------- توليد الصوت -----------------
@bot.message_handler(content_types=['text'])
def handle_text_generation(message):
    user_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(user_id)

    # ذكاء اصطناعي للتعرف على المفتاح مباشرة حتى لو لم يضغط زراً
    if text.startswith("sk_"):
        update_user_key(user_id, "eleven", text)
        user_states[user_id] = None
        bot.send_message(user_id, "✅ **تم التعرف على مفتاح ElevenLabs وحفظه، وتم تحويل البوت إلى ElevenLabs ⚡ تلقائياً!**\n\nأرسل القصة الآن وسينفذها فوراً.", reply_markup=main_keyboard("eleven"))
        return

    if text.startswith("sk-fish-"):
        update_user_key(user_id, "fish", text)
        user_states[user_id] = None
        bot.send_message(user_id, "✅ **تم التعرف على مفتاح Fish Audio وحفظه، وتم تحويل البوت إلى Fish Audio 🐟 تلقائياً!**\n\nأرسل القصة الآن وسينفذها فوراً.", reply_markup=main_keyboard("fish"))
        return

    user = get_user(user_id)
    engine = user["engine"]
    api_key = user["eleven_key"] if engine == "eleven" else user["fish_key"]

    if not api_key:
        bot.send_message(user_id, f"⚠️ لا يوجد مفتاح محفوظ لمنصة {engine}! أدخل المفتاح أولاً.")
        return

    chunks = split_text(text)
    engine_label = "ElevenLabs ⚡" if engine == "eleven" else "Fish Audio 🐟"
    status_msg = bot.send_message(user_id, f"⏳ جاري التوليد الحقيقي عبر **{engine_label}** ({len(chunks)} أجزاء)...")

    audio_segments, temp_files = [], []

    for i, chunk in enumerate(chunks):
        if engine == "eleven":
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
            headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
            payload = {
                "text": chunk,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
        else:
            url = "https://api.fish.audio/v1/tts"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"text": chunk, "reference_id": FISH_VOICE_ID, "format": "mp3"}

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=90)
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ اتصال بالإنترنت: {e}")
            return

        if res.status_code != 200:
            bot.delete_message(user_id, status_msg.message_id)
            err_text = res.text
            if res.status_code == 401:
                bot.send_message(user_id, f"⚠️ خطأ 401 في {engine_label}: المفتاح غير صحيح أو تم إلغاؤه.")
            elif res.status_code in [402, 429]:
                bot.send_message(user_id, f"⚠️ خطأ {res.status_code} في {engine_label}: تم استهلاك الحد المسموح أو تجاوز السرعة.")
            else:
                bot.send_message(user_id, f"❌ خطأ من سيرفر {engine_label} ({res.status_code}):\n`{err_text}`")
            return

        part_file = f"temp_{user_id}_{i}.mp3"
        with open(part_file, "wb") as f:
            f.write(res.content)
        temp_files.append(part_file)
        audio_segments.append(AudioSegment.from_file(part_file))
        time.sleep(1.2)

    if audio_segments:
        final_audio = audio_segments[0]
        for seg in audio_segments[1:]:
            final_audio += seg

        final_path = f"story_{user_id}.mp3"
        final_audio.export(final_path, format="mp3")
        bot.delete_message(user_id, status_msg.message_id)
        with open(final_path, "rb") as audio:
            bot.send_audio(user_id, audio, title="القصة الكاملة", performer=engine_label)

        if os.path.exists(final_path): os.remove(final_path)
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

while True:
    try:
        bot.infinity_polling(timeout=25, long_polling_timeout=25)
    except Exception as e:
        time.sleep(5)
