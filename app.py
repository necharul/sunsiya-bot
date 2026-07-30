import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'sunsiya_verify_2024')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')

# --- On/off switch -----------------------------------------------------
# AI_ENABLED sets the default state on every restart (edit it in Render's
# Environment tab: true/false). ai_enabled below is the *live* value and
# can be flipped instantly via the /toggle link without waiting for a
# redeploy — see the /toggle route further down.
AI_ENABLED_DEFAULT = os.environ.get('AI_ENABLED', 'true').lower() == 'true'
ai_enabled = AI_ENABLED_DEFAULT

# --- Business info / training examples ----------------------------------
# Company details, prices, and example Q&A live in knowledge.txt, NOT here,
# so they can be edited as plain text (no Python syntax to break) and just
# need a commit + push to go live.
def load_knowledge():
    try:
        with open(os.path.join(os.path.dirname(__file__), 'knowledge.txt'), 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''

BUSINESS_KNOWLEDGE = load_knowledge()

SYSTEM_PROMPT = f"""তুমি Sunsiya Naturals-এর AI customer assistant। তোমার নাম "সানসিয়া সহকারী"।

তোমার ব্যক্তিত্ব:
- বন্ধুত্বপূর্ণ, উষ্ণ এবং সহায়ক
- বাংলায় কথা বলবে, সহজ ও প্রাঞ্জল ভাষায়
- একদম মানুষের মতো কথা বলবে
- customer-এর সমস্যা বুঝে সহানুভূতি দেখাবে

{BUSINESS_KNOWLEDGE}

নির্দেশনা:
- সব সময় বাংলায় উত্তর দাও
- উত্তর সংক্ষিপ্ত রাখো (৩-৪ বাক্য)
- প্রয়োজনে emoji ব্যবহার করো
- প্রশ্নের উত্তর না জানলে বলো ফোন করতে: 01768-067187
- উপরে "উদাহরণ কথোপকথন" দেওয়া থাকলে ঠিক সেই ভাষা ও ধরনে উত্তর দেওয়ার চেষ্টা করো"""

conversation_store = {}

def get_gemini_response(user_id, user_message):
    if user_id not in conversation_store:
        conversation_store[user_id] = []
    
    conversation_store[user_id].append({
        "role": "user",
        "parts": [{"text": user_message}]
    })
    
    if len(conversation_store[user_id]) > 10:
        conversation_store[user_id] = conversation_store[user_id][-10:]
    
    try:
        # gemini-1.5-flash is fully shut down (404). gemini-flash-latest is an
        # auto-updating alias that always points to Google's current GA flash model,
        # so this line won't need manual updates when Google retires models again.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": conversation_store[user_id]
        }
        
        response = requests.post(url, json=payload, timeout=15)
        data = response.json()
        
        if response.status_code != 200 or 'candidates' not in data:
            # Log the real Gemini error (bad model name, bad key, quota, etc.)
            # so it shows up in Render logs instead of failing silently.
            print(f"Gemini API returned status {response.status_code}: {data}")
            return "অতি দ্রুতই আমাদের একজন প্রতিনিধি আপনার প্রশ্নের উত্তর দিবে। অথবা, অনুগ্রহ করে 📞01768-067187 নম্বরে কল বা হোয়াটসঅ্যাপ করুন।"
        
        reply = data['candidates'][0]['content']['parts'][0]['text']
        
        conversation_store[user_id].append({
            "role": "model",
            "parts": [{"text": reply}]
        })
        
        return reply
        
    except Exception as e:
        print(f"Gemini API error: {e}")
        return "দুঃখিত, একটু সমস্যা হয়েছে। অনুগ্রহ করে 01768-067187 নম্বরে কল করুন। 📞"

def send_message(recipient_id, message_text):
    try:
        response = requests.post(
            'https://graph.facebook.com/v19.0/me/messages',
            params={'access_token': PAGE_ACCESS_TOKEN},
            json={
                'recipient': {'id': recipient_id},
                'message': {'text': message_text},
                'messaging_type': 'RESPONSE'
            },
            timeout=10
        )
        return response.json()
    except Exception as e:
        print(f"Send message error: {e}")
        return None

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200
    return 'Verification failed', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                if 'message' not in event:
                    continue

                if event['message'].get('is_echo'):
                    # This is YOUR own reply, sent manually from the Facebook
                    # Page inbox/Messenger app. It shows up here so you can
                    # find good examples in Render's Logs and copy them into
                    # knowledge.txt's "উদাহরণ কথোপকথন" section — that's how
                    # the AI "learns" your style over time.
                    echo_text = event['message'].get('text', '')
                    if echo_text:
                        print(f"[MANUAL REPLY - copy to knowledge.txt if useful]: {echo_text}")
                    continue

                message_text = event['message'].get('text', '')
                if not (message_text and sender_id):
                    continue

                print(f"Message from {sender_id}: {message_text}")

                if ai_enabled:
                    reply = get_gemini_response(sender_id, message_text)
                    send_message(sender_id, reply)
                else:
                    print(f"[AI OFF] Not auto-replying to {sender_id} — reply manually from Messenger.")
    return 'OK', 200

@app.route('/toggle', methods=['GET'])
def toggle_ai():
    """Bookmark this URL on your phone:
    https://sunsiya-bot.onrender.com/toggle?token=YOUR_ADMIN_TOKEN
    Each visit flips the AI on/off instantly (no redeploy, no waiting).
    Add &state=on or &state=off to set it directly instead of flipping."""
    global ai_enabled
    if not ADMIN_TOKEN or request.args.get('token', '') != ADMIN_TOKEN:
        return 'Unauthorized', 403

    state = request.args.get('state', '').lower()
    if state == 'on':
        ai_enabled = True
    elif state == 'off':
        ai_enabled = False
    else:
        ai_enabled = not ai_enabled

    return jsonify({'ai_enabled': ai_enabled})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({'ai_enabled': ai_enabled})

@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'running', 'service': 'Sunsiya AI Bot', 'message': 'Messenger bot is active!'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
