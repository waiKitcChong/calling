from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, messaging
import os
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for Flutter

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        # Try to get service account from environment variable (for Render)
        service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        
        if service_account_json:
            # Parse JSON from environment variable
            service_account_dict = json.loads(service_account_json)
            cred = credentials.Certificate(service_account_dict)
        else:
            # Fallback to local file (for development)
            cred = credentials.Certificate('service_account.json')
        
        firebase_admin.initialize_app(cred)
        print('✅ Firebase Admin SDK initialized')
    except Exception as e:
        print(f'❌ Error initializing Firebase: {e}')

initialize_firebase()

@app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'service': 'TripMate Video Call Notification Service',
        'endpoints': {
            '/send-call-notification': 'POST - Send video call notification',
            '/health': 'GET - Health check'
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/send-call-notification', methods=['POST', 'OPTIONS'])
def send_call_notification():
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        fcm_token = data.get('token')
        title = data.get('title', 'Incoming Video Call')
        body = data.get('body', 'You have an incoming call')
        notification_data = data.get('data', {})
        
        if not fcm_token:
            return jsonify({'error': 'FCM token is required'}), 400
        
        print(f'📞 Sending call notification to token: {fcm_token[:20]}...')
        
        # Create FCM message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=notification_data,
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    channel_id='tripmate_calls',
                    priority='max',
                    visibility='public',
                    default_sound=True,
                    default_vibrate_timings=True,
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                        content_available=True,
                    )
                )
            )
        )
        
        # Send notification
        response = messaging.send(message)
        
        print(f'✅ Notification sent successfully: {response}')
        
        return jsonify({
            'success': True,
            'message_id': response
        }), 200
        
    except messaging.UnregisteredError:
        print('❌ Error: FCM token is invalid or unregistered')
        return jsonify({
            'error': 'Invalid or unregistered FCM token'
        }), 400
        
    except Exception as e:
        print(f'❌ Error sending notification: {str(e)}')
        return jsonify({
            'error': 'Failed to send notification',
            'details': str(e)
        }), 500

@app.route('/send-batch-notifications', methods=['POST'])
def send_batch_notifications():
    """Send notifications to multiple tokens (for group calls)"""
    try:
        data = request.get_json()
        tokens = data.get('tokens', [])
        title = data.get('title', 'Incoming Video Call')
        body = data.get('body', 'You have an incoming call')
        notification_data = data.get('data', {})
        
        if not tokens:
            return jsonify({'error': 'No tokens provided'}), 400
        
        # Create multicast message
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=notification_data,
            tokens=tokens,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    channel_id='tripmate_calls',
                )
            ),
        )
        
        # Send to multiple devices
        response = messaging.send_multicast(message)
        
        print(f'✅ Batch notification sent: {response.success_count} successful, {response.failure_count} failed')
        
        return jsonify({
            'success': True,
            'success_count': response.success_count,
            'failure_count': response.failure_count
        }), 200
        
    except Exception as e:
        print(f'❌ Error sending batch notification: {str(e)}')
        return jsonify({
            'error': 'Failed to send batch notification',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)