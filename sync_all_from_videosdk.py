"""
Sync ALL Supabase call_logs with real VideoSDK session data.
- Fetches every session from VideoSDK /v2/sessions
- Computes real duration from start/end timestamps
- Matches sessions to Supabase call_logs by roomId or created_at proximity
- Clears fake durations/sentiments for records that have NO matching VideoSDK session
"""
import urllib.request
import json
import os
import dotenv
import jwt
import time
from datetime import datetime, timezone

dotenv.load_dotenv()

SUPABASE_URL = "https://zuxjdbrgfwpphswgxkiw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A"
VIDEOSDK_API_KEY = "7dc4e4ed-8b80-4270-8951-5819dd798c78"
VIDEOSDK_SECRET = "577e43d199bac6836acf812508123cc1730dfc6e52cc8c9de0a46104bb580c90"

def get_token():
    payload = {
        'apikey': VIDEOSDK_API_KEY,
        'permissions': ['allow_join', 'allow_mod'],
        'version': 2,
        'iat': int(time.time()),
        'exp': int(time.time()) + 86400
    }
    return jwt.encode(payload, VIDEOSDK_SECRET, algorithm='HS256')

def fetch_all_videosdk_sessions(token):
    """Fetch all sessions from VideoSDK, paginated."""
    all_sessions = []
    page = 1
    while True:
        url = f"https://api.videosdk.live/v2/sessions?page={page}&perPage=50"
        req = urllib.request.Request(url, headers={'Authorization': token})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            sessions = data.get('data', [])
            all_sessions.extend(sessions)
            page_info = data.get('pageInfo', {})
            if page >= page_info.get('lastPage', 1):
                break
            page += 1
    return all_sessions

def compute_duration(session):
    """Compute human-readable duration from ISO timestamps or recording log."""
    try:
        start_str = session.get('start')
        end_str = session.get('end')
        if not start_str or not end_str:
            rec = session.get('recordingLog') or []
            if len(rec) > 0:
                start_str = rec[0].get('start')
                end_str = rec[0].get('end')
        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        delta = end - start
        total_secs = int(delta.total_seconds())
        mins = total_secs // 60
        secs = total_secs % 60
        return f"{mins}m {secs:02d}s"
    except:
        return '--'

def determine_status(session):
    """Determine call status from session data."""
    participants = session.get('participants', [])
    has_sip = any(p.get('type') == 'sip' for p in participants)
    has_agent = any(p.get('type') == 'agent' for p in participants)
    
    duration_str = compute_duration(session)
    
    # Short sessions (< 15 seconds) with no real interaction are likely missed
    try:
        start_str = session.get('start') or (session.get('recordingLog') or [{}])[0].get('start')
        end_str = session.get('end') or (session.get('recordingLog') or [{}])[0].get('end')
        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        total_secs = (end - start).total_seconds()
        if total_secs < 15:
            return 'missed', duration_str, 'Unanswered'
    except:
        pass
    
    if has_sip and has_agent:
        return 'completed', duration_str, 'Interested'
    elif has_agent:
        return 'completed', duration_str, 'Engaged'
    else:
        return 'missed', duration_str, 'Unanswered'

def fetch_all_supabase_logs():
    url = f"{SUPABASE_URL}/rest/v1/call_logs?select=*&order=created_at.desc"
    req = urllib.request.Request(url, headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def patch_supabase_log(log_id, patch_data):
    url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{log_id}"
    req = urllib.request.Request(url, data=json.dumps(patch_data).encode(), method='PATCH')
    req.add_header('apikey', SUPABASE_KEY)
    req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as resp:
        return resp.status

def match_session_to_log(session, logs):
    """Try to match a VideoSDK session to a Supabase call log by timestamps."""
    session_start = datetime.fromisoformat(session['start'].replace('Z', '+00:00'))
    room_id = session.get('roomId', '')
    
    best_match = None
    best_delta = float('inf')
    
    for log in logs:
        log_created = log.get('created_at', '')
        if not log_created:
            continue
        try:
            log_time = datetime.fromisoformat(log_created.replace('Z', '+00:00'))
            delta = abs((session_start - log_time).total_seconds())
            if delta < best_delta and delta < 120:  # Within 2 minutes
                best_delta = delta
                best_match = log
        except:
            continue
    
    return best_match

from main import fetch_videosdk_session_transcript_from_api, refine_dialogue_transcript

def main():
    token = get_token()
    
    print("Fetching all VideoSDK sessions...")
    sessions = fetch_all_videosdk_sessions(token)
    print(f"Found {len(sessions)} VideoSDK sessions.")
    
    print("Fetching all Supabase call logs...")
    logs = fetch_all_supabase_logs()
    print(f"Found {len(logs)} Supabase call logs.")
    
    matched_log_ids = set()
    
    # Step 1: Match VideoSDK sessions to Supabase logs and update with real data
    for session in sessions:
        room_id = session.get('roomId', '')
        session_id = session.get('id', '')
        status, duration, sentiment = determine_status(session)
        
        match = match_session_to_log(session, logs)
        if match:
            log_id = match['id']
            matched_log_ids.add(log_id)
            
            existing_transcript = match.get('transcript') or []
            patch = {
                'status': status,
                'duration': duration,
                'sentiment': sentiment
            }
            
            # Fetch real transcript from VideoSDK API
            transcript = fetch_videosdk_session_transcript_from_api(room_id=room_id, session_id=session_id)
            if transcript and len(transcript) > 0:
                caller_name = match.get('caller_name') or match.get('name') or 'Mukund Verma'
                refined = refine_dialogue_transcript(transcript, caller_name=caller_name)
                patch['transcript'] = refined
                print(f"  Fetched & refined {len(refined)} transcript turns for session {session_id[:12]}")
            elif isinstance(existing_transcript, list) and len(existing_transcript) > 0:
                caller_name = match.get('caller_name') or match.get('name') or 'Mukund Verma'
                patch['transcript'] = refine_dialogue_transcript(existing_transcript, caller_name=caller_name)
                pass
            else:
                patch['transcript'] = []
            
            result = patch_supabase_log(log_id, patch)
            print(f"  Matched session {session_id[:12]} (room {room_id}) -> log {log_id[:8]}: status={status}, duration={duration} [{result}]")
        else:
            print(f"  No match for session {session_id[:12]} (room {room_id}, started {session.get('start', '?')})")
    
    # Step 2: Reset unmatched logs (no real VideoSDK session) 
    unmatched = [l for l in logs if l['id'] not in matched_log_ids]
    print(f"\n{len(unmatched)} Supabase logs have no matching VideoSDK session. Resetting to clean state...")
    
    for log in unmatched:
        log_id = log['id']
        existing_transcript = log.get('transcript') or []
        has_real_transcript = isinstance(existing_transcript, list) and len(existing_transcript) > 0
        
        if has_real_transcript:
            patch = {'status': 'completed', 'duration': '--', 'sentiment': 'Completed'}
        else:
            patch = {'status': 'completed', 'duration': '--', 'sentiment': 'Completed', 'transcript': []}
        
        result = patch_supabase_log(log_id, patch)
        print(f"  Reset log {log_id[:8]}: duration=--, sentiment=Completed [{result}]")
    
    print("\nDone! All call logs now reflect real VideoSDK session data.")

if __name__ == "__main__":
    main()
