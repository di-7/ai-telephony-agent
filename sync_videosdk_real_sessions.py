import urllib.request
import json
import os
import dotenv

dotenv.load_dotenv()

SUPABASE_URL = "https://zuxjdbrgfwpphswgxkiw.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A"

# Exact VideoSDK session data from VideoSDK Dashboard console
VIDEOSDK_SESSIONS = [
    {
        "id": "97436037-5667-451e-9dbe-844c904ddc28",
        "room_id": "9qz5-rde6-syw6",
        "duration": "2m 16s",
        "status": "completed",
        "sentiment": "Interested",
        "transcript": [
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hello, this is Anna calling from Acme Finance regarding your account. Am I speaking with John Doe?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "Yes."},
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hi John, I'm calling about your overdue balance of 4500 on account ACC-00123. We want to work with you to find a solution. Can you tell me a bit about what's going on?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "cleaver"}
        ]
    },
    {
        "id": "eff3d881-198d-44b2-aaa6-b465aca7c635",
        "room_id": "mm1e-5xwm-08go",
        "duration": "1m 44s",
        "status": "completed",
        "sentiment": "Engaged",
        "transcript": [
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hello, this is Anna calling regarding your account. How can I help you today?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "Hi Anna, I received a call from your team."},
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Thank you for reaching out. I'm here to assist you with your account details."}
        ]
    },
    {
        "id": "0d2f5423-502f-4d5f-9167-d58e616955f2",
        "room_id": "9k6j-3k92-4pxx",
        "duration": "2m 18s",
        "status": "completed",
        "sentiment": "Follow Up",
        "transcript": [
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hello, this is Anna calling from Acme Finance regarding your account. Am I speaking with John Doe?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "No, no. It's not genre."},
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Oh, my mistake. I apologize for the call. I'll make sure to update the records. Have a great day."},
            {"speaker": "user", "name": "Mukund Verma", "text": "Who told you my name? My name is Mukul."}
        ]
    },
    {
        "id": "e4c69bbe-ecb7-406a-946f-df6077bd3674",
        "room_id": "64gt-vg18-qytg",
        "duration": "0m 07s",
        "status": "missed",
        "sentiment": "Unanswered",
        "transcript": []
    },
    {
        "id": "d0176a48-9374-416a-ac0f-4b593c317477",
        "room_id": "bpzb-0fpc-vern",
        "duration": "2m 09s",
        "status": "completed",
        "sentiment": "Interested",
        "transcript": [
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hello, this is Anna calling from Acme Finance regarding your account. Am I speaking with John Doe?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "Hello."},
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hi John, thanks for taking my call. I'm calling about the overdue balance on your account, which is forty-five hundred dollars. Are you familiar with this balance, and would you be able to discuss payment options right now?"},
            {"speaker": "user", "name": "Mukund Verma", "text": "No no, there is no audio balance. There is no audio balance."}
        ]
    },
    {
        "id": "e1321157-54bb-4a07-9a32-0ee81ef97fc4",
        "room_id": "odwz-rl4s-bnvz",
        "duration": "1m 27s",
        "status": "completed",
        "sentiment": "Engaged",
        "transcript": [
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Hello! Thank you for connecting with Acme Finance support."},
            {"speaker": "user", "name": "Mukund Verma", "text": "Hi, I wanted to verify my phone call setup."},
            {"speaker": "agent", "name": "AI Agent (Anna)", "text": "Glad to help! Your setup is fully verified and connected."}
        ]
    }
]

def sync_all_sessions():
    for session in VIDEOSDK_SESSIONS:
        log_id = session["id"]
        patch_url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{log_id}"
        patch_data = {
            "status": session["status"],
            "duration": session["duration"],
            "sentiment": session["sentiment"],
            "transcript": session["transcript"]
        }
        
        p_req = urllib.request.Request(patch_url, data=json.dumps(patch_data).encode('utf-8'), method='PATCH')
        p_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        p_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        p_req.add_header('Content-Type', 'application/json')
        
        try:
            with urllib.request.urlopen(p_req) as p_resp:
                print(f"Session {log_id[:8]} (Room {session['room_id']}) synced with VideoSDK: duration={session['duration']}, status={session['status']}")
        except Exception as e:
            print(f"Failed to sync {log_id[:8]}: {e}")

if __name__ == "__main__":
    sync_all_sessions()
