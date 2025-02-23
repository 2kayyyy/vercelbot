from flask import Flask, request
import requests
import os
import re
import sqlite3
import time
from telegram.ext import Application
from google.generativeai import GenerativeModel
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env
load_dotenv()
print("Environment variables loaded")  # Debug

# Configuration (stored in .env, no defaults—required for runtime)
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
PAGE_ACCESS_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CASH_APP_RECEIVER = os.environ["CASH_APP_RECEIVER"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


# Set up Application (no polling to avoid conflict with Flask)
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
print("Telegram Application built")  # Debug

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    print("Webhook received")  # Debug
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            print(f"Verification successful, challenge: {request.args.get('hub.challenge')}")  # Debug
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    data = request.get_json()
    print(f"POST data: {data}")  # Debug
    if data['object'] == 'page':
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                if 'message' in event and 'text' in event['message']:
                    message_text = event['message']['text'].lower()
                    print(f"Message from {sender_id}: {message_text}")  # Debug
                    facebook_name = get_facebook_name(sender_id)  # Mock
                    if "hi" in message_text:
                        reply = get_ai_response("hi", "Welcome to the casino!")
                        send_message(sender_id, reply)
                    elif "username" in message_text:
                        reply = get_ai_response("username", "Asking for game username!")
                        send_message(sender_id, reply)
                    elif "cash.app" in message_text:
                        handle_cash_in(sender_id, message_text, facebook_name)
                    elif message_text == "yes":
                        amount = get_last_amount(sender_id)
                        reply = get_ai_response(f"confirm recharge of ${amount}", "Confirming recharge!")
                        send_message(sender_id, reply)
                    elif "split" in message_text:
                        handle_split_recharge(sender_id, message_text, facebook_name)
                    elif any(game in message_text for game in ["gamea", "gameb"]):
                        handle_single_recharge(sender_id, message_text, facebook_name)
                    elif "cashout" in message_text:
                        handle_cash_out(sender_id, message_text, facebook_name)
                    elif any(word in message_text for word in ["support", "help", "issue"]):
                        handle_support(sender_id, message_text, facebook_name)
    return "Message received", 200

def send_telegram_alert(message):
    print(f"Attempting Telegram alert: {message}")  # Debug
    try:
        # Use run_sync to call the async send_message synchronously
        result = application.bot.run_sync(
            lambda: application.bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
        )
        print(f"Telegram alert sent successfully: {message}")  # Debug
    except Exception as e:
        print(f"Telegram alert failed: {e}")  # Debug

def init_db():
    print("Initializing database")  # Debug
    db_path = '/tmp/receipts.db'  # Use /tmp for Vercel
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS receipts 
                 (id TEXT PRIMARY KEY, sender_id TEXT, amount REAL, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_recharges 
                 (id TEXT PRIMARY KEY, sender_id TEXT, game TEXT, username TEXT, amount REAL, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cashouts 
                 (id TEXT PRIMARY KEY, sender_id TEXT, game TEXT, username TEXT, amount REAL, points_remaining REAL, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets 
                 (id TEXT PRIMARY KEY, sender_id TEXT, summary TEXT, status TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# AI Helper for Flirty Casino Girl Vibe (using Gemini)
def get_ai_response(user_message, context=""):
    print(f"Generating AI response for: {user_message}")  # Debug
    model = GenerativeModel("gemini-2.0-flash", api_key=GEMINI_API_KEY)
    response = model.generate_content(f"""
    You are a flirty, slutty casino girl named Cherry, working at Casino Test Bot. Use short, playful, conversational phrases with a sexy, fun vibe. Respond to: "{user_message}" 
    Context: {context}. Keep it under 20 words, flirty, and casino-themed.
    """)
    return response.text.strip() if response.text else "Hey hun😘 how can i help you?"

def send_message(sender_id, text):
    url = "https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": sender_id}, "message": {"text": text}}
    try:
        print(f"Sending message to {sender_id}: {text}")  # Debug
        response = requests.post(url, params=params, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending message: {e}")

def handle_cash_in(sender_id, url, facebook_name):
    if verify_receipt(url, sender_id):
        amount = get_receipt_amount(url)
        send_telegram_alert(f"Cash In Alert\nFacebook Name: {facebook_name}\nCashApp Amount: ${amount}")
        reply = get_ai_response(f"sent ${amount} to {CASH_APP_RECEIVER}", "Confirming cash in!")
        send_message(sender_id, f"{reply} Confirm to recharge? (Yes/No)")
    else:
        reply = get_ai_response("invalid receipt", "Oops, naughty receipt!")
        send_message(sender_id, f"{reply} Try again, sugar!")

def verify_receipt(url, sender_id):
    try:
        if not url.startswith("https://cash.app/"):
            return False
        match = re.search(r"amount=(\d+\.\d+)", url)
        if not match:
            return False
        amount = float(match.group(1))
        receiver = CASH_APP_RECEIVER  # Mock—parse real receiver from URL
        if receiver != CASH_APP_RECEIVER:
            return False

        conn = sqlite3.connect('/tmp/receipts.db')
        c = conn.cursor()
        c.execute("SELECT id FROM receipts WHERE id=?", (url,))
        if c.fetchone():
            conn.close()
            return False  # Duplicate
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO receipts (id, sender_id, amount, timestamp) VALUES (?, ?, ?, ?)",
                  (url, sender_id, amount, timestamp))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Receipt verification error: {e}")
        return False

def get_receipt_amount(url):
    match = re.search(r"amount=(\d+\.\d+)", url)
    return float(match.group(1)) if match else 0.0

def get_last_amount(sender_id):
    # Mock—store in memory or DB per user
    return 10.0  # Default—adapt to real receipt

def handle_split_recharge(sender_id, message, facebook_name):
    games = parse_split_recharge(message, sender_id)
    total_amount = get_last_amount(sender_id)
    for game, username, amount, cash_app in games:
        if amount <= total_amount:
            recharge_amount = amount * 1.1  # +10% bonus
            record_recharge(sender_id, game, username, recharge_amount, cash_app)
            reply = get_ai_response(f"recharged {game} for ${recharge_amount}", f"Recharging {game}!")
            send_message(sender_id, f"{reply} Ooh, hot wins, babe! 💋")
    send_message(sender_id, "Recharges processed! Check your games, darling! 😘")
    send_telegram_alert(f"Cash In Alert\nFacebook Name: {facebook_name}\nCashApp Amount: ${total_amount}\nGame: {', '.join(g[0] for g in games)}\nGame Username: {', '.join(g[1] for g in games)}\nRecharge Amount: ${sum(g[2] * 1.1 for g in games)}")

def handle_single_recharge(sender_id, message, facebook_name):
    game, username = parse_game_username(message, sender_id)
    amount = get_last_amount(sender_id)
    recharge_amount = amount * 1.1  # +10% bonus
    record_recharge(sender_id, game, username, recharge_amount, CASH_APP_RECEIVER)
    reply = get_ai_response(f"recharged {game} for ${recharge_amount}", "Big win, sexy!")
    send_message(sender_id, f"{reply} You can cashout: $40 to $100 / Enjoy the game, honey! ❤️")
    send_telegram_alert(f"Cash In Alert\nFacebook Name: {facebook_name}\nCashApp Amount: ${amount}\nGame: {game}\nGame Username: {username}\nRecharge Amount: ${recharge_amount}")

def parse_game_username(message, sender_id):
    if "gamea" in message:
        return "GameA", message.replace("gamea", "").strip()
    elif "gameb" in message:
        return "GameB", message.replace("gameb", "").strip()
    return None, None

def parse_split_recharge(message, sender_id):
    games = []
    parts = message.split(",")
    total_amount = get_last_amount(sender_id)
    remaining = total_amount
    for part in parts:
        part = part.strip()
        if "gamea" in part:
            amount = float(re.search(r"\$(\d+\.\d+)", part).group(1)) if re.search(r"\$(\d+\.\d+)", part) else remaining / len(parts)
            games.append(("GameA", "user_gamea", min(amount, remaining), CASH_APP_RECEIVER))
            remaining -= amount
        elif "gameb" in part:
            amount = float(re.search(r"\$(\d+\.\d+)", part).group(1)) if re.search(r"\$(\d+\.\d+)", part) else remaining / len(parts)
            games.append(("GameB", "user_gameb", min(amount, remaining), CASH_APP_RECEIVER))
            remaining -= amount
    return games

def record_recharge(sender_id, game, username, amount, cash_app):
    conn = sqlite3.connect('/tmp/receipts.db')
    c = conn.cursor()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO game_recharges (id, sender_id, game, username, amount, cash_app, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (f"{sender_id}_{game}_{timestamp}", sender_id, game, username, amount, cash_app, timestamp))
    conn.commit()
    conn.close()

def handle_cash_out(sender_id, message, facebook_name):
    game, username = parse_game_username(message, sender_id)
    deposit = get_last_amount(sender_id) * 1.1  # Initial recharge + 10%
    points = get_points(sender_id, game, username)
    if points < deposit * 3 or points > deposit * 10:
        reply = get_ai_response("invalid cashout", "Naughty cashout, babe—try again!")
        send_message(sender_id, f"{reply} Must be 3-10x deposit (${deposit:.2f}). Points: {points}")
        return
    cashout_amount = max(40.0, min(points, deposit * 10))  # Min $40, max 10x
    points_remaining = points - cashout_amount
    if points_remaining > deposit * 10:
        points_remaining = 0  # Redeem all if >10x
    next_cashout_min = max(40.0, points_remaining * 3) if points_remaining > 0 else 0
    next_cashout_max = points_remaining * 10 if points_remaining > 0 else 0
    send_telegram_alert(f"Cash Out Alert\nFacebook Name: {facebook_name}\nGame: {game}\nGame Username: {username}\nCashout Amount: ${cashout_amount}\nPoints Remaining: {points_remaining}")
    record_cashout(sender_id, game, username, cashout_amount, points_remaining)
    reply = get_ai_response(f"cashout ${cashout_amount}", "Big win, sexy—cashin’ out!")
    message = f"{reply} Your cashout of ${cashout_amount} sent to ID [Y] for ${cashout_amount}.\n{points_remaining} points left."
    if points_remaining > 0:
        message += f"\nNext cashout: ${next_cashout_min:.2f} to ${next_cashout_max:.2f}"
    send_message(sender_id, message)

def get_points(sender_id, game, username):
    # Mock—fetch from DB or game API
    return 50.0  # Example points

def record_cashout(sender_id, game, username, amount, points_remaining):
    conn = sqlite3.connect('/tmp/receipts.db')
    c = conn.cursor()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO cashouts (id, sender_id, game, username, amount, points_remaining, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (f"{sender_id}_{game}_{timestamp}", sender_id, game, username, amount, points_remaining, timestamp))
    conn.commit()
    conn.close()

def handle_support(sender_id, message, facebook_name):
    summary = message or "User requests support"
    send_telegram_alert(f"Support Alert\nFacebook Name: {facebook_name}\nShort Summary: {summary}")
    reply = get_ai_response("support request", "Oh, honey, I’ll get help—talk dirty to support! 😘")
    send_message(sender_id, f"{reply} Our team will contact you soon. Details, please!")

def get_facebook_name(sender_id):
    # Mock—fetch from Facebook Graph API later
    return "User" + sender_id[-4:]  # Simple mock

if __name__ == '__main__':
    print("Starting Flask server on port 3000")  # Debug
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 3000)))