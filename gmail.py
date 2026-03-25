import imaplib
import email
import requests
import json
import random
import time
import re
import threading
from email.header import decode_header

# ================= CONFIG =================
EMAIL = "asocksavi01@gmail.com"
APP_PASSWORD = "wnpw jsfv wley ditx"

BOT_TOKEN = "7115609198:AAEAXFJDpYNznycabXUbI0oTfQNTaQAy8nw"
CHAT_ID = "6796283644"
IMAP_SERVER = "imap.gmail.com"

# ================= TELEGRAM =================
def send_telegram(message, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    })

def send_main_button(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚙️ Generate Gmail Variations", "callback_data": "gen"}]
        ]
    }

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": chat_id,
        "text": "Choose an option 👇",
        "reply_markup": json.dumps(keyboard)
    })

def send_variation_options(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "Dot Trick", "callback_data": "dot"}],
            [{"text": "Random Caps", "callback_data": "caps"}],
            [{"text": "Mixed", "callback_data": "mix"}]
        ]
    }

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
        "chat_id": chat_id,
        "text": "Select variation type:",
        "reply_markup": json.dumps(keyboard)
    })

# ================= EMAIL =================
def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ["text/plain", "text/html"]:
                try:
                    return part.get_payload(decode=True).decode()
                except:
                    return ""
    else:
        try:
            return msg.get_payload(decode=True).decode()
        except:
            return ""

# ================= OTP =================
def extract_otp(text):
    text = text.lower()

    if not any(k in text for k in ["otp", "code", "verification", "password"]):
        return None

    match = re.findall(r"\b\d{4,8}\b", text)
    return match[0] if match else None

# ================= VARIATIONS =================
def dot_variation(email_addr):
    name, domain = email_addr.split("@")
    variations = set()

    while len(variations) < 10:
        i = random.randint(1, len(name)-1)
        variations.add(name[:i] + "." + name[i:] + "@" + domain)

    return list(variations)

def caps_variation(email_addr):
    name, domain = email_addr.split("@")
    variations = set()

    while len(variations) < 10:
        new = "".join(
            c.upper() if random.random() > 0.5 else c
            for c in name
        )
        variations.add(new + "@" + domain)

    return list(variations)

def mixed_variation(email_addr):
    name, domain = email_addr.split("@")
    variations = set()

    while len(variations) < 10:
        new = ""
        for c in name:
            if random.random() > 0.5:
                c = c.upper()
            new += c

            if random.random() > 0.7:
                new += "."

        new = new.strip(".")
        variations.add(new + "@" + domain)

    return list(variations)

# ================= TELEGRAM HANDLER =================
LAST_UPDATE_ID = None
AUTHORIZED_CHAT = None

def handle_updates():
    global LAST_UPDATE_ID, AUTHORIZED_CHAT

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 5}

    if LAST_UPDATE_ID:
        params["offset"] = LAST_UPDATE_ID + 1

    res = requests.get(url, params=params).json()

    for update in res.get("result", []):
        LAST_UPDATE_ID = update["update_id"]

        # ===== /start =====
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")

            if text == "/start":
                AUTHORIZED_CHAT = chat_id

                send_telegram(
                    "🤖 *Welcome!*\n\n"
                    "I will send OTP emails instantly 🔐\n\n"
                    "Use the button below 👇",
                    chat_id
                )

                send_main_button(chat_id)

        # ===== BUTTONS =====
        if "callback_query" in update:
            data = update["callback_query"]["data"]
            chat_id = update["callback_query"]["message"]["chat"]["id"]

            if chat_id != AUTHORIZED_CHAT:
                return

            if data == "gen":
                send_variation_options(chat_id)

            elif data == "dot":
                send_telegram(
                    "🔹 *Dot Variations:*\n\n" +
                    "\n".join(f"`{v}`" for v in dot_variation(EMAIL)),
                    chat_id
                )

            elif data == "caps":
                send_telegram(
                    "🔹 *Caps Variations:*\n\n" +
                    "\n".join(f"`{v}`" for v in caps_variation(EMAIL)),
                    chat_id
                )

            elif data == "mix":
                send_telegram(
                    "🔹 *Mixed Variations:*\n\n" +
                    "\n".join(f"`{v}`" for v in mixed_variation(EMAIL)),
                    chat_id
                )

# ================= UID TRACK =================
last_uid = None

def init_last_uid():
    global last_uid

    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, APP_PASSWORD)
    mail.select("inbox")

    _, data = mail.uid("search", None, "ALL")
    uids = data[0].split()

    if uids:
        last_uid = uids[-1]

    mail.logout()

# ================= CHECK EMAIL =================
def check_email():
    global last_uid

    if not AUTHORIZED_CHAT:
        return

    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, APP_PASSWORD)
    mail.select("inbox")

    _, data = mail.uid("search", None, "ALL")
    uids = data[0].split()

    new_uids = [uid for uid in uids if last_uid is None or int(uid) > int(last_uid)]

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

                body = get_email_body(msg)
                otp = extract_otp(subject + "\n" + body)

                if otp:
                    send_telegram(
                        f"🔐 *OTP DETECTED*\n\nCode: `{otp}`",
                        AUTHORIZED_CHAT
                    )

    mail.logout()

# ================= THREADS =================
def telegram_loop():
    while True:
        try:
            handle_updates()
            time.sleep(1)
        except Exception as e:
            print("Telegram Error:", e)
            time.sleep(2)

def gmail_loop():
    while True:
        try:
            check_email()
            time.sleep(5)
        except Exception as e:
            print("Gmail Error:", e)
            time.sleep(5)

# ================= MAIN =================
print("🚀 FAST BOT RUNNING...")

init_last_uid()

t1 = threading.Thread(target=telegram_loop)
t2 = threading.Thread(target=gmail_loop)

t1.start()
t2.start()

t1.join()
t2.join()