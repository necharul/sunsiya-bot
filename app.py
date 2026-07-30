import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'sunsiya_verify_2024')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

SYSTEM_PROMPT = """তুমি Sunsiya Naturals-এর AI customer assistant। তোমার নাম "সুনসিয়া সহকারী"।

তোমার ব্যক্তিত্ব:
- বন্ধুত্বপূর্ণ, উষ্ণ এবং সহায়ক
- বাংলায় কথা বলবে, সহজ ও প্রাঞ্জল ভাষায়
- একদম মানুষের মতো কথা বলবে
- customer-এর সমস্যা বুঝে সহানুভূতি দেখাবে

কোম্পানির তথ্য:
- নাম: Sunsiya Naturals
- ওয়েবসাইট: sunsiya.com
- ফোন: 01768-067187
- বিশেষত্ব: ১০০% খাঁটি দেশি পণ্য, কোনো ভেজাল নেই

পণ্যসমূহ:
- ঘি ২৫০ গ্রাম: ৳৪২০
- ঘি ৫০০ গ্রাম: ৳৮ ৪০
- ঘি ১ কেজি: ৳১৬৯০ (ফ্রি ডেলিভারি)

ডেলিভারি:
- ঢাকার ভেতরে: ৬০৳, ঢাকার বাইরে: ১২০৳
- ১ কেজি অর্ডারে ফ্রি ডেলিভারি
- পেমেন্ট: ক্যাশ অন ডেলিভারি

অর্ডার করতে:
- ওয়েবসাইট: sunsiya.com/khati-ghee
- ফোন: 01768-067187

নির্দেশনা:
- সব সময় বাংলায় উত্তর দাও
- উত্তর সংক্ষিপ্ত রাখো (৩-৪ বাক্য)
- প্রয়োজনে emoji ব্যবহার করো
- প্রশ্নের উত্তর না জানলে বলো ফোন করতে: 01768-067187"""

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
        # ✅ পরিবর্তন: v1 এর জায়গায় v1beta ব্যবহার করা হয়েছে
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": conversation_store[user_id]
        }
        
        response = requests.post(url, json=payload, timeout=15)
        data = response.json()
        
        # API যদি কোনো কারণে এরর রিটার্ন করে তা প্রিন্ট করে সঠিক ট্র্যাকিং
        if 'error' in data:
            print(f"Gemini API Returned Error: {data['error']}")
            return "দুঃখিত, আমাদের সিস্টেমে সাময়িক সমস্যা হচ্ছে। অনুগ্রহ করে 01768-067187 নম্বরে কল করুন।"
        
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
                if 'message' in event and not event['message'].get('is_echo'):
                    message_text = event['message'].get('text', '')
                    if message_text and sender_id:
                        print(f"Message from {sender_id}: {message_text}")
                        reply = get_gemini_response(sender_id, message_text)
                        send_message(sender_id, reply)
    return 'OK', 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'running', 'service': 'Sunsiya AI Bot', 'message': 'Messenger bot is active!'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
