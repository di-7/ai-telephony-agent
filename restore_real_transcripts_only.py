import urllib.request
import json
import os
import dotenv

dotenv.load_dotenv()

SUPABASE_URL = "https://zuxjdbrgfwpphswgxkiw.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A"

HARDCODED_INDICATORS = [
    "Hi! Thanks for checking out our site. How can I assist you today?",
    "Hi! Thanks for checking out our site. I'm an AI assistant.",
    "Thank you for connecting. I am ready to assist you with your account inquiry.",
    "Thank you for connecting. I am here to help you with your account."
]

def restore_real_transcripts():
    url = f"{SUPABASE_URL}/rest/v1/call_logs?select=*"
    req = urllib.request.Request(url, method='GET')
    req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
    req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
    
    try:
        with urllib.request.urlopen(req) as resp:
            logs = json.loads(resp.read().decode('utf-8'))
            print(f"Total call logs fetched: {len(logs)}")
            
            cleared_count = 0
            for log in logs:
                log_id = log['id']
                transcript = log.get('transcript') or []
                
                # Check if transcript contains any hardcoded placeholder text
                has_placeholder = False
                if isinstance(transcript, list):
                    for turn in transcript:
                        if isinstance(turn, dict):
                            txt = turn.get('text', '')
                            if any(ind in txt for ind in HARDCODED_INDICATORS):
                                has_placeholder = True
                                break
                
                if has_placeholder:
                    cleared_count += 1
                    patch_url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{log_id}"
                    patch_data = {'transcript': []}
                    
                    p_req = urllib.request.Request(patch_url, data=json.dumps(patch_data).encode('utf-8'), method='PATCH')
                    p_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                    p_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                    p_req.add_header('Content-Type', 'application/json')
                    
                    with urllib.request.urlopen(p_req) as p_resp:
                        print(f"Cleared placeholder transcript for log {log_id[:8]}")
            
            print(f"Successfully cleared fake placeholder transcripts from {cleared_count} records. Real transcripts remain untouched!")

    except Exception as e:
        print(f"Error restoring transcripts: {e}")

if __name__ == "__main__":
    restore_real_transcripts()
