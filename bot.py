import imaplib
import email
import requests
import time
import re
import threading
import os
import json
import sqlite3
from email.header import decode_header

BOT_TOKEN = os.getenv("BOT_TOKEN")
IMAP_SERVER = "imap.gmail.com"

# ================= DATABASE =================
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    email TEXT,
    app_password TEXT,
    last_uid TEXT
)
""")
conn.commit()

def save_user(chat_id, email, password, last_uid):
    cursor.execute(
        "REPLACE INTO users VALUES (?, ?, ?, ?)",
        (chat_id, email, password, last_uid)
    )
    conn.commit()

def delete_user(chat_id):
    cursor.execute("DELETE FROM users WHERE chat_id=?", (chat_id,))
    conn.commit()

def get_all_users():
    cursor.execute("SELECT * FROM users")
    return cursor.fetchall()

# ================= STATE =================
user_states = {}

# ================= TELEGRAM =================
def send(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

def send_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚙️ Gmail Variations", "callback_data": "gen"}],
            [{"text": "🚪 Logout", "callback_data": "logout"}]
        ]
    }

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": chat_id,
        "text": "✅ You are logged in",
        "reply_markup": json.dumps(keyboard)
    })

# ================= OTP =================
def extract_otp(text):
    text = text.lower()
    if not any(k in text for k in ["otp", "code", "verification", "password"]):
        return None
    match = re.findall(r"\b\d{4,8}\b", text)
    return match[0] if match else None

# ================= EMAIL =================
def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ["text/plain", "text/html"]:
                try:
                    return part.get_payload(decode=True).decode()
                except:
                    return ""
    return ""

# ================= LOGIN =================
def login_user(chat_id, email_addr, app_pass):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(email_addr, app_pass)
        mail.select("inbox")

        _, data = mail.uid("search", None, "ALL")
        uids = data[0].split()
        last_uid = uids[-1] if uids else None

        save_user(chat_id, email_addr, app_pass, last_uid)

        mail.logout()

        send(chat_id, "✅ Logged in!")
        send_menu(chat_id)

    except:
        send(chat_id, "❌ Login failed")

# ================= LOGOUT =================
def logout_user(chat_id):
    delete_user(chat_id)
    user_states.pop(chat_id, None)
    send(chat_id, "🚪 Logged out")

# ================= CHECK EMAIL =================
def check_email(chat_id, email_addr, password, last_uid):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(email_addr, password)
        mail.select("inbox")

        _, data = mail.uid("search", None, "ALL")
        uids = data[0].split()

        new_uids = [
            uid for uid in uids
            if last_uid is None or int(uid) > int(last_uid)
        ]

        if new_uids:
            last_uid = new_uids[-1]

        for uid in new_uids:
            _, msg_data = mail.uid("fetch", uid, "(RFC822)")

            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])

                    subject, enc = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(enc or "utf-8")

                    body = get_body(msg)
                    otp = extract_otp(subject + "\n" + body)

                    if otp:
                        send(chat_id, f"🔐 OTP: `{otp}`")

        save_user(chat_id, email_addr, password, last_uid)

        mail.logout()

    except:
        send(chat_id, "⚠️ Email error")

# ================= TELEGRAM =================
LAST_UPDATE_ID = None

def handle_updates():
    global LAST_UPDATE_ID

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 5}

    if LAST_UPDATE_ID:
        params["offset"] = LAST_UPDATE_ID + 1

    res = requests.get(url, params=params).json()

    for update in res.get("result", []):
        LAST_UPDATE_ID = update["update_id"]

        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")

            # ===== START =====
            if text == "/start":
                cursor.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
                user = cursor.fetchone()

                if user:
                    send(chat_id, "👋 Welcome back!")
                    send_menu(chat_id)
                else:
                    user_states[chat_id] = "awaiting_email"
                    send(chat_id, "📧 Enter your Gmail:")

            # ===== EMAIL =====
            elif user_states.get(chat_id) == "awaiting_email":
                user_states[chat_id] = {
                    "step": "awaiting_password",
                    "email": text
                }
                send(chat_id, "🔑 Enter App Password:")

            # ===== PASSWORD =====
            elif isinstance(user_states.get(chat_id), dict):
                data = user_states[chat_id]
                if data["step"] == "awaiting_password":
                    login_user(chat_id, data["email"], text)
                    user_states.pop(chat_id, None)

        # ===== BUTTONS =====
        if "callback_query" in update:
            data = update["callback_query"]["data"]
            chat_id = update["callback_query"]["message"]["chat"]["id"]

            if data == "logout":
                logout_user(chat_id)

# ================= LOOPS =================
def telegram_loop():
    while True:
        handle_updates()
        time.sleep(1)

def gmail_loop():
    while True:
        users = get_all_users()

        for chat_id, email_addr, password, last_uid in users:
            check_email(chat_id, email_addr, password, last_uid)

        time.sleep(5)

# ================= MAIN =================
print("🚀 DB BOT RUNNING...")

threading.Thread(target=telegram_loop).start()
threading.Thread(target=gmail_loop).start()
