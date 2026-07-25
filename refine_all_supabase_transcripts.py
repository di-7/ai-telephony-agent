import urllib.request
import json
import os
import sys

from main import fetch_videosdk_session_transcript_from_api, refine_dialogue_transcript

SUPABASE_URL = "https://zuxjdbrgfwpphswgxkiw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A"

def fetch_all_supabase_logs():
    url = f"{SUPABASE_URL}/rest/v1/call_logs?select=*&order=created_at.desc"
    req = urllib.request.Request(url, headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def patch_supabase_log(log_id, patch_data):
    url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{log_id}"
    req = urllib.request.Request(url, data=json.dumps(patch_data).encode('utf-8'), method='PATCH')
    req.add_header('apikey', SUPABASE_KEY)
    req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as resp:
        return resp.status

def main():
    print("Fetching all Supabase call logs...")
    logs = fetch_all_supabase_logs()
    print(f"Total call logs in Supabase: {len(logs)}")
    
    updated_count = 0
    for log in logs:
        log_id = log['id']
        existing_transcript = log.get('transcript') or []
        caller_name = log.get('caller_name') or log.get('name') or 'Mukund Verma'
        
        refined = None
        if isinstance(existing_transcript, list) and len(existing_transcript) > 0:
            refined = refine_dialogue_transcript(existing_transcript, caller_name=caller_name)
        
        if refined and json.dumps(refined) != json.dumps(existing_transcript):
            patch_data = {'transcript': refined}
            status = patch_supabase_log(log_id, patch_data)
            updated_count += 1
            print(f"Refined transcript for log {log_id[:8]} ({caller_name}): {len(existing_transcript)} turns -> {len(refined)} turns [{status}]")
        else:
            print(f"Log {log_id[:8]} ({caller_name}): {len(existing_transcript)} turns already refined.")

    print(f"\nDone! Updated {updated_count} call log transcripts in Supabase.")

if __name__ == "__main__":
    main()
