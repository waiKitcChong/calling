from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, messaging
import os
from supabase import create_client, Client
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 初始化 Firebase Admin SDK
# 需要在环境变量中设置 FIREBASE_CREDENTIALS (JSON格式)
firebase_creds = os.environ.get('FIREBASE_CREDENTIALS')
if firebase_creds:
    import json
    cred_dict = json.loads(firebase_creds)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

# 初始化 Supabase
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/api/call/initiate', methods=['POST'])
def initiate_call():
    """发起视频通话"""
    try:
        data = request.json
        caller_id = data.get('caller_id')
        caller_name = data.get('caller_name')
        receiver_id = data.get('receiver_id')
        call_type = data.get('call_type', 'video')  # video or audio
        channel_id = data.get('channel_id')  # Agora 频道ID
        
        if not all([caller_id, caller_name, receiver_id, channel_id]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # 从数据库获取接收者的 FCM token
        response = supabase.table('users_fcm_tokens')\
            .select('fcm_token')\
            .eq('tourist_id', receiver_id)\
            .order('updated_at', desc=True)\
            .limit(1)\
            .execute()
        
        if not response.data:
            return jsonify({"error": "Receiver FCM token not found"}), 404
        
        fcm_token = response.data[0]['fcm_token']
        
        # 构建 FCM 消息
        message = messaging.Message(
            notification=messaging.Notification(
                title=f'{caller_name} 正在呼叫你',
                body=f'{"视频" if call_type == "video" else "语音"}通话',
            ),
            data={
                'type': 'incoming_call',
                'call_type': call_type,
                'caller_id': caller_id,
                'caller_name': caller_name,
                'channel_id': channel_id,
                'timestamp': datetime.now().isoformat(),
            },
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='video_call_channel',
                    priority='max',
                    sound='default',
                    visibility='public',
                ),
            ),
            apns=messaging.APNSConfig(
                headers={
                    'apns-priority': '10',
                },
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=f'{caller_name} 正在呼叫你',
                            body=f'{"视频" if call_type == "video" else "语音"}通话',
                        ),
                        sound='default',
                        badge=1,
                        category='INCOMING_CALL',
                    ),
                ),
            ),
            token=fcm_token,
        )
        
        # 发送推送通知
        response = messaging.send(message)
        
        return jsonify({
            "success": True,
            "message_id": response,
            "receiver_id": receiver_id,
        }), 200
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/call/end', methods=['POST'])
def end_call():
    """结束通话通知"""
    try:
        data = request.json
        caller_id = data.get('caller_id')
        receiver_id = data.get('receiver_id')
        channel_id = data.get('channel_id')
        
        # 获取接收者的 FCM token
        response = supabase.table('users_fcm_tokens')\
            .select('fcm_token')\
            .eq('tourist_id', receiver_id)\
            .order('updated_at', desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            fcm_token = response.data[0]['fcm_token']
            
            message = messaging.Message(
                data={
                    'type': 'call_ended',
                    'caller_id': caller_id,
                    'channel_id': channel_id,
                },
                token=fcm_token,
            )
            
            messaging.send(message)
        
        return jsonify({"success": True}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/call/reject', methods=['POST'])
def reject_call():
    """拒接通话通知"""
    try:
        data = request.json
        caller_id = data.get('caller_id')
        receiver_id = data.get('receiver_id')
        
        # 通知发起者通话被拒绝
        response = supabase.table('users_fcm_tokens')\
            .select('fcm_token')\
            .eq('tourist_id', caller_id)\
            .order('updated_at', desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            fcm_token = response.data[0]['fcm_token']
            
            message = messaging.Message(
                data={
                    'type': 'call_rejected',
                    'receiver_id': receiver_id,
                },
                token=fcm_token,
            )
            
            messaging.send(message)
        
        return jsonify({"success": True}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)