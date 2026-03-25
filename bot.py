import imaplib
import email
import requests
import time
import re
import threading
import os
from email.header import decode_header

BOT_TOKEN = os.getenv("BOT_TOKEN")
IMAP_SERVER = "imap.gmail.com"

users = {}
user_states = {}

# ================= TELEGRAM =================
def send(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
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

# ================= LOGIN FLOW =================
def login_user(chat_id, email_addr, app_pass):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(email_addr, app_pass)
        mail.select("inbox")

        _, data = mail.uid("search", None, "ALL")
        uids = data[0].split()
        last_uid = uids[-1] if uids else None

        users[chat_id] = {
            "email": email_addr,
            "pass": app_pass,
            "last_uid": last_uid
        }

        mail.logout()

        send(chat_id, "✅ *Logged in successfully!*")

    except:
        send(chat_id, "❌ Login failed. Try again with `/start`")

# ================= LOGOUT =================
def logout_user(chat_id):
    if chat_id in users:
        del users[chat_id]
        send(chat_id, "🚪 Logged out.")
    else:
        send(chat_id, "You are not logged in.")

# ================= CHECK EMAIL =================
def check_user_email(chat_id, user):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(user["email"], user["pass"])
        mail.select("inbox")

        _, data = mail.uid("search", None, "ALL")
        uids = data[0].split()

        new_uids = [
            uid for uid in uids
            if user["last_uid"] is None or int(uid) > int(user["last_uid"])
        ]

        if new_uids:
            user["last_uid"] = new_uids[-1]

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

        mail.logout()

    except:
        send(chat_id, "⚠️ Error checking email.")

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
                user_states[chat_id] = "awaiting_email"
                send(chat_id, "📧 Enter your Gmail:")

            # ===== EMAIL STEP =====
            elif user_states.get(chat_id) == "awaiting_email":
                user_states[chat_id] = {
                    "step": "awaiting_password",
                    "email": text
                }
                send(chat_id, "🔑 Enter your App Password:")

            # ===== PASSWORD STEP =====
            elif isinstance(user_states.get(chat_id), dict):
                data = user_states[chat_id]

                if data["step"] == "awaiting_password":
                    email_addr = data["email"]
                    app_pass = text

                    user_states.pop(chat_id, None)
                    login_user(chat_id, email_addr, app_pass)

            # ===== LOGOUT =====
            elif text == "/logout":
                logout_user(chat_id)

# ================= LOOPS =================
def telegram_loop():
    while True:
        try:
            handle_updates()
            time.sleep(1)
        except:
            time.sleep(2)

def gmail_loop():
    while True:
        for chat_id, user in list(users.items()):
            check_user_email(chat_id, user)
        time.sleep(5)

# ================= MAIN =================
print("🚀 Step-login bot running...")

threading.Thread(target=telegram_loop).start()
threading.Thread(target=gmail_loop).start()
