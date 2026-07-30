import os
import json
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Config from environment variables
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'sunsiya_verify_2024')
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', '')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')

# Product & training data (can be updated via admin)
PRODUCTS = [
    {"name": "১০০% প্রিমিয়াম খাঁটি ঘি ২৫০ গ্রাম", "price": "৪২০", "stock": "আছে"},
    {"name": "১০০% প্রিমিয়াম খাঁটি ঘি ৫০০ গ্রাম", "price": "৮৪০", "stock": "আছে"},
    {"name": "১০০% প্রিমিয়াম খাঁটি ঘি ১ কেজি", "price": "১৬৯০", "stock": "আছে"},
]

SYSTEM_PROMPT = """তুমি Sunsiya Naturals-এর AI customer assistant। তোমার নাম "সুনসিয়া সহকারী"।

## তোমার ব্যক্তিত্ব:
- বন্ধুত্বপূর্ণ, উষ্ণ এবং সহায়ক
- বাংলায় কথা বলবে, সহজ ও প্রাঞ্জল ভাষায়
- কখনো রোবোটিক নয়, একদম মানুষের মতো কথা বলবে
- customer-এর সমস্যা বুঝে সহানুভূতি দেখাবে

## কোম্পানির তথ্য:
- নাম: Sunsiya Naturals
- ওয়েবসাইট: sunsiya.com
- ফোন: 01768-067187
- বিশেষত্ব: ১০০% খাঁটি দেশি পণ্য, কোনো ভেজাল নেই

## পণ্যসমূহ:
- ঘি ২৫০ গ্রাম: ৳৪২০
- ঘি ৫০০ গ্রাম: ৳৮৪০  
- ঘি ১ কেজি: ৳১৬৯০ (ফ্রি ডেলিভারি)

## ডেলিভারি:
- ঢাকার ভেতরে: ৬০৳, ঢাকার বাইরে: ১২০৳
- ১ কেজি অর্ডারে ফ্রি ডেলিভারি
- পেমেন্ট: ক্যাশ অন ডেলিভারি

## অর্ডার করতে:
- ওয়েবসাইট: sunsiya.com/khati-ghee
- ফোন: 01768-067187

## নির্দেশনা:
- সব সময় বাংলায় উত্তর দাও
- উত্তর সংক্ষিপ্ত কিন্তু সম্পূর্ণ রাখো (৩-৪ বাক্য)
- প্রয়োজনে emoji ব্যবহার করো
- অর্ডার করতে উৎসাহিত করো কিন্তু চাপ দিও না
- প্রশ্নের উত্তর না জানলে বলো ফোন করতে: 01768-067187"""

# Store conversation history per user
conversation_store = {}

def get_claude_response(user_id, user_message):
    """Get AI response from Claude"""
    if user_id not in conversation_store:
        conversation_store[user_id] = []
    
    conversation_store[user_id].append({
        "role": "user",
        "content": user_message
    })
    
    # Keep only last 10 messages
    if len(conversation_store[user_id]) > 10:
        conversation_store[user_id] = conversation_store[user_id][-10:]
    
    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': CLAUDE_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-6',
                'max_tokens': 500,
                'system': SYSTEM_PROMPT,
                'messages': conversation_store[user_id]
            },
            timeout=15
        )
        
        data = response.json()
        if 'content' in data and len(data['content']) > 0:
            reply = data['content'][0]['text']
            conversation_store[user_id].append({
                "role": "assistant",
                "content": reply
            })
            return reply
        else:
            return "দুঃখিত, একটু সমস্যা হয়েছে। অনুগ্রহ করে 01768-067187 নম্বরে কল করুন।"
    except Exception as e:
        print(f"Claude API error: {e}")
        return "দুঃখিত, একটু সমস্যা হয়েছে। অনুগ্রহ করে 01768-067187 নম্বরে কল করুন।"

def send_message(recipient_id, message_text):
    """Send message via Facebook Messenger"""
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
    """Facebook webhook verification"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("Webhook verified!")
        return challenge, 200
    else:
        return 'Verification failed', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming Facebook messages"""
    data = request.json
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                
                if 'message' in event and not event['message'].get('is_echo'):
                    message_text = event['message'].get('text', '')
                    
                    if message_text and sender_id:
                        print(f"Message from {sender_id}: {message_text}")
                        
                        # Get AI response
                        reply = get_claude_response(sender_id, message_text)
                        
                        # Send reply
                        send_message(sender_id, reply)
    
    return 'OK', 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'running',
        'service': 'Sunsiya AI Bot',
        'message': 'Messenger bot is active!'
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
