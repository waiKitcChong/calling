import os
import json
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# Firebase admin
import firebase_admin
from firebase_admin import credentials, messaging

# optional Agora token builder import (if available)
try:
    from agora_token_builder import RtcTokenBuilder, Role_Attendee
    AGORA_TOKEN_BUILDER_AVAILABLE = True
except Exception:
    AGORA_TOKEN_BUILDER_AVAILABLE = False

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')  # e.g. https://<project>.supabase.co/rest/v1
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FIREBASE_CRED_JSON = os.environ.get('FIREBASE_CRED_JSON')  # path to service account json file
AGORA_APP_ID = os.environ.get('AGORA_APP_ID', '')
AGORA_APP_CERTIFICATE = os.environ.get('AGORA_APP_CERTIFICATE', '')

# Initialize Firebase admin
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_JSON)
    firebase_admin.initialize_app(cred)

app = Flask(__name__)

def get_fcm_token_for_tourist(tourist_id):
    """Query Supabase REST to retrieve fcm token for a given tourist_id."""
    url = f"{SUPABASE_URL}/users_fcm_tokens?tourist_id=eq.{tourist_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        if len(data) > 0:
            return data[0].get('fcm_token')
    return None

@app.route('/send_call', methods=['POST'])
def send_call():
    payload = request.get_json()
    caller_id = payload.get('caller_id')
    caller_name = payload.get('caller_name')
    callee_id = payload.get('callee_id')
    channel_name = payload.get('channel_name')
    call_type = payload.get('call_type', 'video')

    token = get_fcm_token_for_tourist(callee_id)
    if not token:
        return jsonify({"error": "callee token not found"}), 404

    data = {
        "type": "incoming_call",
        "caller_id": caller_id,
        "caller_name": caller_name,
        "channel_name": channel_name,
        "call_type": call_type,
    }

    message = messaging.Message(
        data=data,
        token=token,
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                click_action='FLUTTER_NOTIFICATION_CLICK'
            )
        ),
        apns=messaging.APNSConfig(headers={'apns-priority': '10'})
    )

    resp = messaging.send(message)
    return jsonify({"result": resp})

@app.route('/call_response', methods=['POST'])
def call_response():
    payload = request.get_json()
    from_id = payload.get('from_id')
    to_id = payload.get('to_id')
    channel_name = payload.get('channel_name')
    response = payload.get('response')  # 'accepted' or 'rejected'

    token = get_fcm_token_for_tourist(to_id)
    if not token:
        return jsonify({"error": "target token not found"}), 404

    data = {
        "type": "call_accepted" if response == 'accepted' else 'call_rejected',
        "from_id": from_id,
        "channel_name": channel_name,
    }

    message = messaging.Message(data=data, token=token)
    resp = messaging.send(message)
    return jsonify({"result": resp})

@app.route('/generate_agora_token', methods=['POST'])
def generate_agora_token():
    """
    Request JSON:
    {
      "channel_name": "private_TRS25001_TRS25002_...",
      "uid": 0,
      "expire_in_seconds": 3600
    }
    """
    payload = request.get_json()
    channel_name = payload.get('channel_name')
    uid = int(payload.get('uid', 0))
    expire_in_seconds = int(payload.get('expire_in_seconds', 3600))

    if not AGORA_APP_ID:
        return jsonify({"token": "", "warning": "AGORA_APP_ID not configured, returning empty token (test mode)"}), 200

    if not AGORA_APP_CERTIFICATE or not AGORA_TOKEN_BUILDER_AVAILABLE:
        # If builder not available, fallback to empty token for test purposes
        return jsonify({"token": "", "warning": "Agora token builder not available or certificate missing. Install agora-access-token and set AGORA_APP_CERTIFICATE"}), 200

    # Use Agora token builder to generate token
    try:
        from agora_token_builder import RtcTokenBuilder, Role_Attendee
        current_ts = int(__import__('time').time())
        privilege_expired_ts = current_ts + expire_in_seconds
        token = RtcTokenBuilder.buildTokenWithUid(AGORA_APP_ID, AGORA_APP_CERTIFICATE, channel_name, uid, Role_Attendee, privilege_expired_ts)
        return jsonify({"token": token}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
