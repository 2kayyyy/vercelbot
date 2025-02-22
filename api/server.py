from flask import Flask, request
import requests
import os

app = Flask(__name__)

VERIFY_TOKEN = "test123"
PAGE_ACCESS_TOKEN = "EAAIsIHpyGbYBO0Cj271ozXg67cjQOIMsq3PqKg2MuYYQvVD8aKiJY3Cd2M5B7o2fb4LN9NPbE2YHW2xyIzk1rZBsmYE8DNMd1AmPYbkIBS3Lux2krHBLMTm4amDiuBfO1bKgOfE07eSqD8iZAhHY5a6BkidnXH7tjoYx6F80nVdWq1jIkSfd6CrIRFoFoPu1muukrYNE6KpotaXgZDZD"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                if 'message' in event and 'text' in event['message']:
                    message_text = event['message']['text']
                    send_message(sender_id, "Hey! Say 'hi' to start.")
    return "Message received", 200

def send_message(sender_id, text):
    url = "https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": sender_id}, "message": {"text": text}}
    requests.post(url, params=params, json=data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 3000)))