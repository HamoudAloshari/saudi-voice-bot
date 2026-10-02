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

# ========================================================
# 1. خادم Render الداخلي لإبقاء البوت شغالاً 24/7 دون توقف
# ========================================================
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Live and Running 24/7!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ========================================================
# 2. البيانات الخاصة بك كاملة ومدمجة وجاهزة
# ========================================================
BOT_TOKEN = "8604985808:AAGqxFBZTx9RFs8XIqfg7dr_nlsYMl-vCcE"

# بيانات Fish Audio
FISH_VOICE_ID = "c3e5d81d807f4cbc9a0c2872a4dea9ea"
DEFAULT_FISH_KEY = "sk-fish-s2GZTsNwOwqn5hM1T-f3RivFQEHvpegZpLO1xPY4Dwc"

# بيانات ElevenLabs
ELEVEN_VOICE_ID = "OoE8swS3hImZANNOodf6"
DEFAULT_ELEVEN_KEY = "sk_bda49de5150802a42f5a3c6ec27990fc92e6cf411a8525c9"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ========================================================
# 3. قاعدة البيانات لحفظ التبديل والمفاتيح
# ========================================================
conn = sqlite3.connect("bot_storage_v3.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    engine TEXT DEFAULT 'fish',
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
    # تسجيل المستخدم لأول مرة بالبيانات الافتراضية
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, 'fish', ?, ?)", (user_id, DEFAULT_FISH_KEY, DEFAULT_ELEVEN_KEY))
    conn.commit()
    return {"engine": "fish", "fish_key": DEFAULT_FISH_KEY, "eleven_key": DEFAULT_ELEVEN_KEY}

def update_user_engine(user_id, engine):
    cursor.execute("UPDATE users SET engine = ? WHERE user_id = ?", (engine, user_id))
    conn.commit()

def update_user_key(user_id, key_type, key_value):
    if key_type == "fish":
        cursor.execute("UPDATE users SET fish_key = ? WHERE user_id = ?", (key_value, user_id))
    else:
        cursor.execute("UPDATE users SET eleven_key = ? WHERE user_id = ?", (key_value, user_id))
    conn.commit()

# أزرار لوحة التحكم
def main_keyboard(engine):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    engine_name = "🐟 Fish Audio" if engine == "fish" else "⚡ ElevenLabs"
    markup.row(f"🔄 المنصة الحالية: {engine_name}")
    markup.row("🔑 مفتاح Fish Audio", "🔑 مفتاح ElevenLabs")
    markup.row("ℹ️ فحص حسابي")
    return markup

# ========================================================
# 4. دالة التقسيم الذكي للنصوص الطويلة
# ========================================================
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

# ========================================================
# 5. معالجات الأوامر والرسائل
# ========================================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    get_user(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🐟 استخدام Fish Audio", callback_data="set_fish"),
        types.InlineKeyboardButton("⚡ استخدام ElevenLabs", callback_data="set_eleven")
    )
    bot.send_message(
        message.chat.id,
        "👋 **أهلاً بك في بوت الراوي المزدوج!**\n\n"
        "تم ضبط جميع المفاتيح والأصوات السعودية بنجاح.\n\n"
        "👇 **اختر المنصة التي تريد توليد الصوت من خلالها الآن:**",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data in ["set_fish", "set_eleven"])
def callback_set_engine(call):
    engine = "fish" if call.data == "set_fish" else "eleven"
    update_user_engine(call.message.chat.id, engine)
    name = "Fish Audio 🐟" if engine == "fish" else "ElevenLabs ⚡"
    bot.answer_callback_query(call.id, f"تم التحويل إلى {name}")
    bot.send_message(
        call.message.chat.id,
        f"✅ **أنت الآن تستخدم: {name}**\n\nأرسل أي نص مهما كان طوله وسأحوله بصوت الراوي المدمج فوراً.",
        reply_markup=main_keyboard(engine)
    )

@bot.message_handler(func=lambda msg: msg.text.startswith("🔄 المنصة الحالية") or msg.text in ["🔑 مفتاح Fish Audio", "🔑 مفتاح ElevenLabs", "ℹ️ فحص حسابي"])
def handle_menu_actions(message):
    user_id = message.chat.id
    user = get_user(user_id)

    if message.text.startswith("🔄 المنصة الحالية"):
        new_engine = "eleven" if user["engine"] == "fish" else "fish"
        update_user_engine(user_id, new_engine)
        name = "ElevenLabs ⚡" if new_engine == "eleven" else "Fish Audio 🐟"
        bot.send_message(user_id, f"✅ **تم التحويل فوراً إلى: {name}**", reply_markup=main_keyboard(new_engine))

    elif message.text == "🔑 مفتاح Fish Audio":
        user_states[user_id] = "WAITING_FISH_KEY"
        bot.send_message(user_id, "📥 أرسل **مفتاح Fish Audio الجديد**:", reply_markup=types.ReplyKeyboardRemove())

    elif message.text == "🔑 مفتاح ElevenLabs":
        user_states[user_id] = "WAITING_ELEVEN_KEY"
        bot.send_message(user_id, "📥 أرسل **مفتاح ElevenLabs الجديد**:", reply_markup=types.ReplyKeyboardRemove())

    elif message.text == "ℹ️ فحص حسابي":
        f_key = user["fish_key"][:8] + "..." if user["fish_key"] else "غير مضاف"
        e_key = user["eleven_key"][:8] + "..." if user["eleven_key"] else "غير مضاف"
        curr = "Fish Audio 🐟" if user["engine"] == "fish" else "ElevenLabs ⚡"
        bot.send_message(
            user_id,
            f"📋 **بياناتك المسجلة:**\n- المنصة النشطة: `{curr}`\n- مفتاح Fish: `{f_key}`\n- مفتاح Eleven: `{e_key}`\n- صوت Fish: `{FISH_VOICE_ID}`\n- صوت Eleven: `{ELEVEN_VOICE_ID}`"
        )

# ========================================================
# 6. توليد الصوت ومعالجة النصوص الطويلة
# ========================================================
@bot.message_handler(content_types=['text'])
def handle_text_generation(message):
    user_id = message.chat.id
    state = user_states.get(user_id)

    # حفظ المفاتيح الجديدة في حال التحديث
    if state == "WAITING_FISH_KEY":
        update_user_key(user_id, "fish", message.text.strip())
        user_states[user_id] = None
        bot.send_message(user_id, "✅ تم تحديث وحفظ مفتاح Fish Audio بنجاح!", reply_markup=main_keyboard(get_user(user_id)["engine"]))
        return

    if state == "WAITING_ELEVEN_KEY":
        update_user_key(user_id, "eleven", message.text.strip())
        user_states[user_id] = None
        bot.send_message(user_id, "✅ تم تحديث وحفظ مفتاح ElevenLabs بنجاح!", reply_markup=main_keyboard(get_user(user_id)["engine"]))
        return

    user = get_user(user_id)
    engine = user["engine"]
    api_key = user["fish_key"] if engine == "fish" else user["eleven_key"]

    if not api_key:
        bot.send_message(user_id, f"⚠️ لا يوجد مفتاح محفوظ لمنصة {engine}!")
        return

    chunks = split_text(message.text.strip())
    engine_label = "Fish Audio" if engine == "fish" else "ElevenLabs"
    status_msg = bot.send_message(user_id, f"⏳ جاري التوليد عبر **{engine_label}** ({len(chunks)} أجزاء)...")

    audio_segments, temp_files = [], []

    for i, chunk in enumerate(chunks):
        if engine == "fish":
            url = "https://api.fish.audio/v1/tts"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"text": chunk, "reference_id": FISH_VOICE_ID, "format": "mp3"}
        else:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
            headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
            payload = {
                "text": chunk,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=60)
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ بالاتصال: {e}")
            return

        # فحص انتهاء الرصيد
        if res.status_code in [401, 402, 429]:
            bot.delete_message(user_id, status_msg.message_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"🔑 تحديث مفتاح {engine_label}", callback_data=f"change_{engine}"))
            bot.send_message(user_id, f"⚠️ **انتهى رصيد حساب {engine_label}!**\nاضغط بالأسفل لإرسال مفتاح جديد:", reply_markup=markup)
            return
        elif res.status_code != 200:
            bot.send_message(user_id, f"❌ خطأ من سيرفر {engine_label} ({res.status_code}): {res.text}")
            return

        part_file = f"temp_{user_id}_{i}.mp3"
        with open(part_file, "wb") as f:
            f.write(res.content)
        temp_files.append(part_file)
        audio_segments.append(AudioSegment.from_file(part_file))
        time.sleep(0.5)

    # الدمج والإرسال
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

@bot.callback_query_handler(func=lambda call: call.data in ["change_fish", "change_eleven"])
def callback_change_keys(call):
    key_type = "fish" if call.data == "change_fish" else "eleven"
    user_states[call.message.chat.id] = "WAITING_FISH_KEY" if key_type == "fish" else "WAITING_ELEVEN_KEY"
    name = "Fish Audio" if key_type == "fish" else "ElevenLabs"
    bot.send_message(call.message.chat.id, f"📥 أرسل مفتاح الـ API الجديد الخاص بـ **{name}**:")

# ========================================================
# 7. نظام إعادة التشغيل التلقائي عند أي انقطاع
# ========================================================
while True:
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception as e:
        time.sleep(5)
