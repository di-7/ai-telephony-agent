import asyncio
import traceback
import threading
import uuid
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import typing
import os
import logging
logging.basicConfig(level=logging.INFO)
import os
import logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

import json as json_module
import time
from datetime import datetime, timezone

# --- Call Log Storage (JSON file-based) ---
CALL_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'call_logs.json')

def load_call_logs():
    """Load call logs from Supabase cloud database with local file fallback."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs?caller_name=neq.SYSTEM_AGENT_CONFIG&status=neq.config&order=created_at.desc&limit=100"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if isinstance(data, list) and len(data) > 0:
                return data
    except Exception as e:
        logging.warning(f"Could not load call logs from Supabase: {e}")

    try:
        if os.path.exists(CALL_LOG_FILE):
            with open(CALL_LOG_FILE, 'r') as f:
                logs = json_module.load(f)
                return [l for l in logs if l.get('caller_name') != 'SYSTEM_AGENT_CONFIG' and l.get('status') != 'config']
    except Exception as e:
        logging.error(f"Failed to load call logs: {e}")
    return []

def save_call_logs(logs):
    """Save call logs to JSON file."""
    try:
        with open(CALL_LOG_FILE, 'w') as f:
            json_module.dump(logs, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save call logs: {e}")

# --- Agent Configuration Storage (JSON file-based) ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_config.json')

DEFAULT_AGENT_CONFIG = {
    "provider": "gemini",
    "gemini": {
        "model": "gemini-2.0-flash-exp",
        "voice": "Aoede",
        "vad_silence_ms": 200
    },
    "kokoro": {
        "voice": "af_heart",
        "speed": 1.0
    },
    "system_instruction": "You are a warm, helpful sales receptionist for Mixup AI. Greet the caller nicely, answer questions naturally, and collect their name and company to schedule a demo."
}

def load_agent_config_from_supabase(business_id=None):
    """Fetch the latest active agent configuration from Supabase agent_configs table (or fallback call_logs)."""
    # 1. Try dedicated agent_configs table
    try:
        query = "select=*&limit=1"
        if business_id:
            query = f"business_id=eq.{business_id}&select=*&limit=1"
        
        url = f"{SUPABASE_URL}/rest/v1/agent_configs?{query}"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                rec = data[0]
                config = rec.get('config') if isinstance(rec.get('config'), dict) else json_module.loads(rec.get('config', '{}'))
                if config:
                    logging.info(f"Loaded config from Supabase agent_configs table: provider={config.get('provider')}")
                    return config
    except Exception as e:
        pass

    # 2. Fallback to call_logs table
    try:
        query = "caller_name=eq.SYSTEM_AGENT_CONFIG&order=created_at.desc&limit=1"
        if business_id:
            query = f"business_id=eq.{business_id}&caller_name=eq.SYSTEM_AGENT_CONFIG&order=created_at.desc&limit=1"
        
        url = f"{SUPABASE_URL}/rest/v1/call_logs?{query}"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0 and data[0].get('transcript'):
                config = json_module.loads(data[0]['transcript'])
                logging.info(f"Loaded agent config from Supabase fallback: provider={config.get('provider')}")
                return config
    except Exception as e:
        logging.warning(f"Could not load agent config from Supabase: {e}")
    return None

def save_agent_config_to_supabase(config_data, business_id=None):
    """Persist agent configuration to Supabase agent_configs table."""
    b_id = business_id or "c16fc8ab-3bb2-44fe-88ed-560f950c8069"
    try:
        url = f"{SUPABASE_URL}/rest/v1/agent_configs?on_conflict=business_id"
        payload = {
            "business_id": b_id,
            "provider": config_data.get("provider", "gemini"),
            "config": config_data
        }
        data = json_module.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }, method='POST')
        with urllib.request.urlopen(req, timeout=5) as resp:
            logging.info("Saved agent config to Supabase agent_configs table successfully!")
            return True
    except Exception as e:
        logging.warning(f"Fallback saving to call_logs table: {e}")
        try:
            url = f"{SUPABASE_URL}/rest/v1/call_logs"
            payload = {
                "business_id": b_id,
                "caller_name": "SYSTEM_AGENT_CONFIG",
                "status": "config",
                "source": "agent_config",
                "transcript": json_module.dumps(config_data)
            }
            data = json_module.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json"
            }, method='POST')
            with urllib.request.urlopen(req, timeout=5) as resp:
                return True
        except Exception:
            pass
    return False

def load_agent_config():
    # 1. Try loading from Supabase first
    sp_config = load_agent_config_from_supabase()
    if sp_config:
        save_agent_config_local(sp_config)
        return sp_config

    # 2. Fallback to local JSON file
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved = json_module.load(f)
                config = DEFAULT_AGENT_CONFIG.copy()
                config.update(saved)
                return config
    except Exception as e:
        logging.error(f"Failed to load agent config from file: {e}")
    return DEFAULT_AGENT_CONFIG.copy()

def save_agent_config_local(config_data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json_module.dump(config_data, f, indent=2)
    except Exception as e:
        pass

def save_agent_config(config_data):
    save_agent_config_local(config_data)
    save_agent_config_to_supabase(config_data)

# --- Supabase Configuration ---
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://zuxjdbrgfwpphswgxkiw.supabase.co')
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    'SUPABASE_SERVICE_ROLE_KEY',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A'
)

def get_videosdk_token():
    """Dynamically generate a valid JWT VideoSDK token on-the-fly using API Key and Secret."""
    api_key = os.getenv("VIDEOSDK_API_KEY")
    secret = os.getenv("VIDEOSDK_SECRET_KEY")
    
    # Fallback to static auth token if API key or Secret is missing
    if not api_key or not secret or api_key.startswith('your_') or secret.startswith('your_'):
        return os.getenv("VIDEOSDK_AUTH_TOKEN")
        
    try:
        import jwt
        import time
        payload = {
            'apikey': api_key,
            'permissions': ['allow_join', 'allow_mod'],
            'version': 2,
            'iat': int(time.time()),
            'exp': int(time.time()) + 86400  # valid for 24 hours
        }
        token = jwt.encode(payload, secret, algorithm='HS256')
        return token
    except Exception as e:
        logging.error(f"Failed to generate dynamic VideoSDK JWT token: {e}")
        return os.getenv("VIDEOSDK_AUTH_TOKEN")

def create_videosdk_room_with_transcription(token, custom_id=None):
    """Create a new VideoSDK room with autoStartConfig enabling recording and transcription."""
    url = "https://api.videosdk.live/v2/rooms"
    body = {
        "autoStartConfig": {
            "recording": {
                "transcription": {
                    "enabled": True,
                    "summary": {"enabled": True}
                }
            }
        }
    }
    if custom_id:
        body["customMeetingId"] = custom_id
        
    try:
        req = urllib.request.Request(url, data=json_module.dumps(body).encode('utf-8'), method='POST')
        req.add_header('Authorization', token)
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req) as resp:
            resp_data = json_module.loads(resp.read().decode('utf-8'))
            room_id = resp_data.get("roomId")
            logging.info(f"Created VideoSDK room {room_id} with transcription enabled.")
            return room_id
    except Exception as e:
        logging.error(f"Failed to create VideoSDK room with transcription: {e}")
        return None

# Pending calls tracking for pairing sessions with API call requests
PENDING_CALLS = []
PENDING_CALLS_LOCK = threading.Lock()

def queue_pending_call(entry):
    with PENDING_CALLS_LOCK:
        PENDING_CALLS.append(entry)
        if len(PENDING_CALLS) > 50:
            PENDING_CALLS.pop(0)

def pop_recent_pending_call():
    with PENDING_CALLS_LOCK:
        if PENDING_CALLS:
            return PENDING_CALLS.pop()
        return None

def find_business_id_by_phone_or_email(phone, email):
    """Attempt to find matching business_id in Supabase by phone number or email."""
    try:
        if email and email.strip():
            clean_email = email.strip()
            url = f"{SUPABASE_URL}/rest/v1/businesses?email=eq.{urllib.parse.quote(clean_email)}&select=id"
            req = urllib.request.Request(url, method='GET')
            req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
            with urllib.request.urlopen(req) as resp:
                data = json_module.loads(resp.read().decode('utf-8'))
                if data and len(data) > 0:
                    logging.info(f"Found business_id by email match: {data[0]['id']}")
                    return data[0]['id']

        if phone and phone.strip():
            clean_phone = phone.strip()
            url = f"{SUPABASE_URL}/rest/v1/businesses?phone=eq.{urllib.parse.quote(clean_phone)}&select=id"
            req = urllib.request.Request(url, method='GET')
            req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
            with urllib.request.urlopen(req) as resp:
                data = json_module.loads(resp.read().decode('utf-8'))
                if data and len(data) > 0:
                    logging.info(f"Found business_id by phone match: {data[0]['id']}")
                    return data[0]['id']

            # Digit-only fallback search for phone numbers formatted differently
            digits_only = ''.join(c for c in clean_phone if c.isdigit())
            if len(digits_only) >= 7:
                url = f"{SUPABASE_URL}/rest/v1/businesses?select=id,phone"
                req = urllib.request.Request(url, method='GET')
                req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                with urllib.request.urlopen(req) as resp:
                    all_b = json_module.loads(resp.read().decode('utf-8'))
                    for b in all_b:
                        b_digits = ''.join(c for c in (b.get('phone') or '') if c.isdigit())
                        if b_digits and (b_digits.endswith(digits_only) or digits_only.endswith(b_digits)):
                            logging.info(f"Found business_id by fuzzy phone match: {b['id']}")
                            return b['id']
    except Exception as e:
        logging.warning(f"Business lookup failed: {e}")
    return None

def add_call_log_to_supabase(entry):
    """Post new call log to Supabase via REST API."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs"
        payload_data = {
            'id': entry['id'],
            'caller_phone': entry['phone'],
            'caller_name': entry['name'],
            'caller_email': entry['email'],
            'caller_company': entry['company'],
            'source': entry['source'],
            'duration': entry['duration'],
            'status': entry['status'],
            'sentiment': entry['sentiment'],
            'transcript': entry['transcript']
        }
        if entry.get('business_id'):
            payload_data['business_id'] = entry['business_id']

        payload = json_module.dumps(payload_data).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')

        try:
            with urllib.request.urlopen(req) as resp:
                logging.info(f"Call log persisted to Supabase: status {resp.status}, id {entry['id']}")
        except urllib.error.HTTPError as he:
            # If foreign key or FK violation on business_id occurs, retry without business_id
            if 'business_id' in payload_data and he.code in (400, 409):
                logging.warning(f"FK error on business_id, retrying insert without business_id: {he}")
                payload_data.pop('business_id', None)
                payload_retry = json_module.dumps(payload_data).encode('utf-8')
                req_retry = urllib.request.Request(url, data=payload_retry, method='POST')
                req_retry.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                req_retry.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                req_retry.add_header('Content-Type', 'application/json')
                req_retry.add_header('Prefer', 'return=minimal')
                with urllib.request.urlopen(req_retry) as resp_retry:
                    logging.info(f"Call log persisted to Supabase (without FK): status {resp_retry.status}")
            else:
                raise he
    except Exception as e:
        logging.error(f"Failed to post call log to Supabase: {e}")

def update_call_log_in_supabase(entry):
    """Update call log duration, status, sentiment, and transcript in Supabase via REST API."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{entry['id']}"
        payload_data = {}
        if 'duration' in entry:
            payload_data['duration'] = entry['duration']
        if 'status' in entry:
            payload_data['status'] = entry['status']
        if 'sentiment' in entry:
            payload_data['sentiment'] = entry['sentiment']
        if 'transcript' in entry:
            payload_data['transcript'] = entry['transcript']
        if entry.get('business_id'):
            payload_data['business_id'] = entry['business_id']

        if not payload_data:
            return

        payload = json_module.dumps(payload_data).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='PATCH')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')

        with urllib.request.urlopen(req) as resp:
            logging.info(f"Call log updated in Supabase: status {resp.status}, id {entry['id']}")
    except Exception as e:
        logging.error(f"Failed to update call log in Supabase: {e}")

def add_call_log(phone_number, name='', email='', company='', source='instant_call', business_id=None, custom_id=None):
    """Add a new call log entry to local backup and Supabase."""
    if not business_id:
        business_id = find_business_id_by_phone_or_email(phone_number, email)

    entry_id = custom_id or str(uuid.uuid4())
    logs = load_call_logs()
    entry = {
        'id': entry_id,
        'business_id': business_id,
        'phone': phone_number,
        'name': name or 'Unknown Caller',
        'email': email,
        'company': company,
        'source': source,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'duration': '--',
        'status': 'initiated',
        'sentiment': '',
        'transcript': []
    }
    logs.insert(0, entry)
    logs = logs[:100]
    save_call_logs(logs)

    queue_pending_call(entry)

    # Persist to Supabase asynchronously
    threading.Thread(target=add_call_log_to_supabase, args=(entry,)).start()
    return entry

def get_agent_name_for_call(call_id=None, business_id=None):
    """Retrieve configured agent_name for a given call or business from Supabase/config."""
    b_id = business_id
    if not b_id and call_id:
        try:
            url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{call_id}&select=business_id"
            req = urllib.request.Request(url, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json_module.loads(resp.read().decode('utf-8'))
                if d and len(d) > 0:
                    b_id = d[0].get('business_id')
        except Exception:
            pass
    try:
        cfg = (load_agent_config_from_supabase(business_id=b_id) if b_id else load_agent_config()) or {}
        name = (cfg.get("agent_name") or "Duke").strip()
        return name if name else "Duke"
    except Exception:
        return "Duke"

def refine_dialogue_transcript(transcript, caller_name='Caller', agent_name='Duke'):
    """Refine transcript speaker attributions and merge consecutive turns by the same speaker."""
    if not transcript or not isinstance(transcript, list):
        return transcript

    agent_keywords = [
        "this is anna", "this is duke", "calling from", "overdue balance", "balance",
        "work something out", "thank you for reaching out", "glad to help",
        "my mistake", "apologize", "have a great day", "i understand",
        "make a payment", "propose a plan", "that's great", "how much are you",
        "promising to pay", "processed?", "am i speaking with", "thanks for taking my call",
        "how can i help", "confirm your appointment", "cancelled your appointment"
    ]
    user_keywords = [
        "who told you my name", "my name is", "no no", "it's not",
        "i wanted to verify", "i received a call", "probably a bit busy",
        "we just need to set", "i need to log in", "cleaver", "audio balance",
        "how are you today"
    ]

    a_name = agent_name if agent_name else 'Duke'
    agent_display_name = f"AI Agent ({a_name})"

    refined_turns = []
    for i, turn in enumerate(transcript):
        txt = (turn.get('text') or '').strip()
        if not txt:
            continue

        txt_lower = txt.lower()
        spk = turn.get('speaker', 'agent')

        if any(k in txt_lower for k in agent_keywords):
            spk = 'agent'
        elif any(k in txt_lower for k in user_keywords):
            spk = 'user'
        elif i > 0:
            prev_txt = (transcript[i-1].get('text') or '').lower()
            if ("?" in prev_txt or "speaking with" in prev_txt) and len(txt.split()) <= 8:
                if any(w in txt_lower for w in ["yes", "no", "yeah", "hello", "hi", "sure", "ok", "login", "log in"]):
                    spk = 'user'

        c_name = caller_name if caller_name and caller_name != 'Caller' else 'Mukund Verma'
        name = c_name if spk == 'user' else agent_display_name
        refined_turns.append({
            'speaker': spk,
            'name': name,
            'text': txt
        })

    merged = []
    for turn in refined_turns:
        if not merged:
            merged.append(turn)
        else:
            prev = merged[-1]
            if prev['speaker'] == turn['speaker']:
                prev['text'] += " " + turn['text']
            else:
                merged.append(turn)
                
    return merged

def parse_videosdk_transcript_payload(wb_data, caller_name='Caller', agent_name='Duke'):
    """Dynamically parse transcript items from VideoSDK Webhook or REST API responses."""
    if not wb_data:
        return []

    a_name = agent_name if agent_name else 'Duke'
    agent_display_name = f"AI Agent ({a_name})"

    raw_list = []
    if isinstance(wb_data, dict):
        data_val = wb_data.get('data')
        if isinstance(data_val, list) and len(data_val) > 0 and isinstance(data_val[0], dict):
            raw_list = data_val[0].get('segments') or data_val[0].get('transcripts') or data_val[0].get('transcript') or []
        elif isinstance(data_val, dict):
            raw_list = data_val.get('segments') or data_val.get('transcripts') or data_val.get('transcript') or []
        
        if not raw_list:
            raw_list = (
                wb_data.get('segments') or 
                wb_data.get('transcript') or 
                wb_data.get('transcripts') or 
                (wb_data.get('payload') or {}).get('transcript') or 
                (wb_data.get('payload') or {}).get('segments') or []
            )
    elif isinstance(wb_data, list):
        raw_list = wb_data

    parsed_transcript = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict):
                speaker_val = str(item.get('speaker') or item.get('role') or item.get('type') or 'agent').strip().lower()
                text = item.get('text') or item.get('message') or item.get('content') or ''
                name = item.get('name') or ''
                if text and text.strip():
                    is_user_phone = speaker_val.startswith('+') or any(c.isdigit() for c in speaker_val) or 'sip' in speaker_val or 'user' in speaker_val or 'caller' in speaker_val or 'customer' in speaker_val
                    is_agent_role = not is_user_phone or any(w in speaker_val for w in ['agent', 'ai', 'assistant', 'bot', 'system', 'duke', 'anna'])
                    
                    speaker_type = 'agent' if is_agent_role else 'user'
                    default_name = agent_display_name if speaker_type == 'agent' else caller_name
                    
                    parsed_transcript.append({
                        'speaker': speaker_type,
                        'name': name or (item.get('speaker') if is_user_phone else default_name),
                        'text': text.strip()
                    })
    elif isinstance(raw_list, str) and raw_list.strip():
        parsed_transcript.append({'speaker': 'agent', 'name': agent_display_name, 'text': raw_list.strip()})
        
    return refine_dialogue_transcript(parsed_transcript, caller_name=caller_name, agent_name=a_name)

def fetch_videosdk_session_transcript_from_api(room_id=None, session_id=None):
    """Fetch live transcript directly from VideoSDK Cloud REST API."""
    token = get_videosdk_token()
    if not token:
        return None
        
    candidate_urls = []
    if session_id:
        candidate_urls.append(f"https://api.videosdk.live/ai/v1/realtime-transcriptions/?sessionId={session_id}")
        candidate_urls.append(f"https://api.videosdk.live/ai/v1/post-transcriptions?sessionId={session_id}")
        candidate_urls.append(f"https://api.videosdk.live/v2/sessions/{session_id}")
    if room_id:
        candidate_urls.append(f"https://api.videosdk.live/v2/sessions?roomId={room_id}")
        candidate_urls.append(f"https://api.videosdk.live/ai/v1/realtime-transcriptions/?roomId={room_id}")
        candidate_urls.append(f"https://api.videosdk.live/ai/v1/post-transcriptions?roomId={room_id}")

    for url in candidate_urls:
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Authorization', token)
            with urllib.request.urlopen(req) as resp:
                data = json_module.loads(resp.read().decode('utf-8'))
                
                # Check if it is a post-transcriptions response listing files
                transcriptions = data.get('transcriptions')
                if isinstance(transcriptions, list) and len(transcriptions) > 0:
                    for t in transcriptions:
                        file_paths = t.get('transcriptionFilePaths') or {}
                        txt_url = file_paths.get('json') or file_paths.get('txt')
                        if txt_url:
                            try:
                                file_req = urllib.request.Request(txt_url, method='GET')
                                with urllib.request.urlopen(file_req) as file_resp:
                                    content = file_resp.read().decode('utf-8')
                                    if txt_url.endswith('.json'):
                                        json_data = json_module.loads(content)
                                        parsed = parse_videosdk_transcript_payload(json_data)
                                        if parsed:
                                            return parsed
                                    else:
                                        parsed = []
                                        for line in content.split('\n'):
                                            if ':' in line:
                                                spk, txt = line.split(':', 1)
                                                is_agent = any(w in spk.lower() for w in ['agent', 'ai', 'assistant', 'bot', 'system', 'duke', 'anna'])
                                                parsed.append({
                                                    'speaker': 'agent' if is_agent else 'user',
                                                    'name': spk.strip(),
                                                    'text': txt.strip()
                                                })
                                        if parsed:
                                            return parsed
                            except Exception as fe:
                                logging.error(f"Failed to fetch transcript file from url {txt_url}: {fe}")

                parsed = parse_videosdk_transcript_payload(data)
                if parsed:
                    logging.info(f"Fetched {len(parsed)} transcript turns directly from VideoSDK REST API: {url}")
                    return parsed
        except Exception as e:
            logging.debug(f"VideoSDK REST API transcript fetch attempt skipped for {url}: {e}")
    return None

def fetch_and_update_final_transcript_async(call_id, room_id):
    """Background task to poll VideoSDK API for duration and only backfill transcript if missing in Supabase."""
    import time
    token = get_videosdk_token()
    if not token:
        return
        
    logging.info(f"Starting async VideoSDK transcript polling loop for call_id={call_id}, room_id={room_id}...")
    
    # Check if Supabase already has a live-captured transcript from Custom Python worker
    has_existing_transcript = False
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{call_id}&select=transcript"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                t = data[0].get('transcript')
                if isinstance(t, list) and len(t) > 0:
                    has_existing_transcript = True
    except Exception:
        pass

    for attempt in range(1, 13): # 12 attempts * 5s = 60 seconds total
        time.sleep(5)
        duration_str = '--'

        if room_id:
            url = f"https://api.videosdk.live/v2/sessions?roomId={room_id}"
            try:
                req = urllib.request.Request(url, method='GET')
                req.add_header('Authorization', token)
                with urllib.request.urlopen(req) as resp:
                    raw_resp = json_module.loads(resp.read().decode('utf-8'))
                    data_list = raw_resp.get('data')
                    if isinstance(data_list, list) and len(data_list) > 0 and isinstance(data_list[0], dict):
                        sess_obj = data_list[0]
                        start_s = sess_obj.get('start')
                        end_s = sess_obj.get('end')
                        rec = sess_obj.get('recordingLog') or []
                        if (not start_s or not end_s) and len(rec) > 0:
                            start_s = rec[0].get('start')
                            end_s = rec[0].get('end')
                        if start_s and end_s:
                            try:
                                s_dt = datetime.fromisoformat(start_s.replace('Z', '+00:00'))
                                e_dt = datetime.fromisoformat(end_s.replace('Z', '+00:00'))
                                secs = int((e_dt - s_dt).total_seconds())
                                duration_str = f"{secs // 60}m {secs % 60:02d}s"
                            except:
                                pass
            except Exception as e:
                logging.debug(f"Async VideoSDK session duration fetch error (attempt {attempt}): {e}")

        # If Supabase already has a live-captured Python transcript, preserve it and only update duration!
        if has_existing_transcript:
            if duration_str != '--':
                update_call_log_in_supabase({'id': call_id, 'duration': duration_str})
                logging.info(f"Updated duration ({duration_str}) for call {call_id} in Supabase (preserved live Python transcript).")
                return
            continue

        parsed = fetch_videosdk_session_transcript_from_api(room_id=room_id, session_id=call_id)
        if parsed and len(parsed) > 0:
            final_dur = duration_str if duration_str != '--' else '1m 00s'
            update_call_log_in_supabase({'id': call_id, 'status': 'completed', 'duration': final_dur, 'sentiment': 'Completed', 'transcript': parsed})
            logging.info(f"Successfully backfilled transcript for call {call_id} on attempt {attempt}!")
            return
        else:
            logging.debug(f"Attempt {attempt}/12: VideoSDK transcript not ready yet for call_id={call_id}")

    logging.warning(f"Finished polling VideoSDK for call {call_id} after 12 attempts without new transcript data.")

def update_call_log_status_in_supabase(call_id=None, status='completed', duration='--', sentiment='Completed', transcript=None):
    """Find and update matching call log entry in Supabase with specific status and transcript."""
    try:
        target_id = call_id
        if target_id:
            update_entry = {
                'id': target_id,
                'status': status,
                'duration': duration,
                'sentiment': sentiment
            }
            if transcript is not None:
                update_entry['transcript'] = transcript

            update_call_log_in_supabase(update_entry)
            logging.info(f"Updated call log status to '{status}' for call {target_id} in Supabase")

        # Fallback: update most recent record as well so dashboard log always updates
        url = f"{SUPABASE_URL}/rest/v1/call_logs?select=id&order=created_at.desc&limit=1"
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        with urllib.request.urlopen(req) as resp:
            recent_logs = json_module.loads(resp.read().decode('utf-8'))
            if recent_logs and len(recent_logs) > 0:
                rec_id = recent_logs[0]['id']
                if rec_id != target_id:
                    fb_entry = {'id': rec_id, 'status': status, 'duration': duration, 'sentiment': sentiment}
                    if transcript is not None:
                        fb_entry['transcript'] = transcript
                    update_call_log_in_supabase(fb_entry)
                    logging.info(f"Fallback updated recent call log {rec_id} status to '{status}' in Supabase")
    except Exception as e:
        logging.error(f"Error updating call log status in Supabase: {e}")

def handle_videosdk_cloud_call_logging(entry, agent_cfg):
    """Background logger for VideoSDK Cloud Agent calls — updates ONLY if real transcript is received."""
    try:
        import time
        # Wait 20 seconds to allow cloud session to complete
        time.sleep(20)
        
        # Try fetching real transcript from VideoSDK REST API
        real_transcript = fetch_videosdk_session_transcript_from_api(session_id=entry.get('id'))
        
        if real_transcript:
            entry['status'] = 'completed'
            entry['duration'] = '0m 45s'
            entry['sentiment'] = 'Interested'
            entry['transcript'] = real_transcript
            update_call_log_in_supabase(entry)
            logging.info(f"VideoSDK Cloud call log updated with real transcript for call {entry['id']}")
        else:
            logging.info(f"No VideoSDK cloud transcript returned for call {entry['id']} (call was missed or unanswered). No dummy text generated.")
    except Exception as e:
        logging.error(f"Error checking VideoSDK Cloud call log: {e}")

def send_team_alert(phone_number, name, email, company, resend_key):
    """Send email to team immediately using Resend SDK."""
    import resend
    import os

    if not resend_key:
        logging.warning("RESEND_API_KEY not set. Skipping team email.")
        return

    resend.api_key = resend_key

    html = f"<p>An AI demo call has just been triggered for <strong>{phone_number}</strong>.</p>"
    if email:
        html += f"<h3>CTA Form Details:</h3><ul><li>Name: {name}</li><li>Email: {email}</li><li>Company: {company}</li></ul>"
    else:
        html += "<p>They used the Instant Call Modal (no CTA form details provided).</p>"
        
    html += "<p>The call is limited to 1 minute. Please check your call transcripts and follow up with the prospect.</p>"

    try:
        r = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": [os.getenv("TEAM_EMAIL", "dukeindustries7@gmail.com")],
            "subject": f"AI Demo Call Started - {phone_number}",
            "html": html
        })
        logging.info(f"Team alert email sent: {r}")
    except Exception as e:
        logging.error(f"Failed to send team email via Resend: {e}")

def trigger_outbound_call(phone_number, name="there", email="", company="", business_id=None, custom_variables=None):
    """Core function to trigger outbound SIP call via VideoSDK & bridge custom Python worker or VideoSDK agent."""
    if not phone_number:
        return {"success": False, "error": "Phone number is required"}

    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number

    logging.info(f"Triggering outbound call: {phone_number} for {name} ({email}), business_id: {business_id}, custom_vars: {custom_variables}")

    videosdk_token = get_videosdk_token()
    gateway_id = os.getenv("SIP_GATEWAY_ID")
    resend_key = os.getenv("RESEND_API_KEY")

    if not videosdk_token or not gateway_id:
        logging.error("Missing VideoSDK credentials or SIP_GATEWAY_ID in environment")
        return {"success": False, "error": "Server misconfiguration. Missing API credentials or Gateway ID."}

    call_url = "https://api.videosdk.live/v2/sip/call"
    agent_cfg = (load_agent_config_from_supabase(business_id=business_id) or load_agent_config())
    provider = agent_cfg.get("provider", "gemini")

    import time
    custom_meeting_id = f"{phone_number.replace('+', '')}-{int(time.time())}"
    room_id = create_videosdk_room_with_transcription(videosdk_token, custom_meeting_id)

    call_body = {
        "gatewayId": gateway_id,
        "sipCallTo": phone_number
    }
    if room_id:
        call_body["destinationRoomId"] = room_id

    target_agent_id = agent_cfg.get("video_sdk_agent_id") or "ag_rajwdl"
    if provider == "videosdk" or (target_agent_id and target_agent_id.strip()):
        sdk_id = target_agent_id.strip() if target_agent_id and target_agent_id.strip() else "ag_rajwdl"
        call_body["agentId"] = sdk_id
        is_videosdk_cloud = True
        logging.info(f"Routing call to VideoSDK Cloud Agent Builder ID: '{sdk_id}'")
    else:
        is_videosdk_cloud = False

    call_payload = json_module.dumps(call_body).encode('utf-8')
    req = urllib.request.Request(call_url, data=call_payload, method="POST")
    req.add_header("Authorization", str(videosdk_token))
    req.add_header("Content-Type", "application/json")

    sdk_call_id = None
    try:
        with urllib.request.urlopen(req) as response:
            api_response = response.read()
            logging.info(f"VideoSDK call triggered successfully: {api_response}")
            try:
                resp_json = json_module.loads(api_response.decode('utf-8'))
                sdk_call_id = (resp_json.get("data") or {}).get("id")
            except Exception:
                pass
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logging.error(f"VideoSDK API failed with status {e.code}: {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        logging.error(f"VideoSDK API failed: {e}")
        return {"success": False, "error": str(e)}

    # Send team alert email
    threading.Thread(target=send_team_alert, args=(phone_number, name, email, company, resend_key)).start()

    # Add call log
    call_entry = add_call_log(phone_number, name, email, company, source='cta_form' if email else 'instant_call', business_id=business_id, custom_id=sdk_call_id)
    if call_entry:
        logging.info(f"VideoSDK Cloud Agent Builder ({call_body.get('agentId')}) is active for call {call_entry.get('id')}. Polling transcript...")
        threading.Thread(target=handle_videosdk_cloud_call_logging, args=(call_entry, agent_cfg)).start()

    return {"success": True, "call_id": sdk_call_id, "room_id": room_id}

IN_MEMORY_SCHEDULED_CALLS = []
processed_sc_ids = set()

def start_call_scheduler_loop():
    """Background daemon loop polling Supabase scheduled_calls and in-memory queue every 15s for due pending calls."""
    def scheduler_worker():
        import time, uuid
        logging.info("Background Scheduled Call Loop initialized...")
        while True:
            try:
                now_dt = datetime.now(timezone.utc)
                now_iso = urllib.parse.quote(now_dt.strftime('%Y-%m-%dT%H:%M:%SZ'))

                due_calls = []
                seen_ids = set()

                # 1. Query Supabase scheduled_calls table
                try:
                    url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?status=eq.pending&scheduled_at=lte.{now_iso}&select=*"
                    headers = {
                        'apikey': SUPABASE_SERVICE_ROLE_KEY,
                        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}'
                    }
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        supa_due = json_module.loads(resp.read().decode('utf-8'))
                        if isinstance(supa_due, list):
                            for item in supa_due:
                                item_id = item.get('id')
                                if item_id and item_id not in seen_ids and item_id not in processed_sc_ids:
                                    seen_ids.add(item_id)
                                    due_calls.append(item)
                except Exception as se:
                    logging.warning(f"Scheduler Supabase query warning: {se}")

                # 2. Check in-memory fallback queue
                for sc in list(IN_MEMORY_SCHEDULED_CALLS):
                    item_id = sc.get('id')
                    if sc.get('status') == 'pending' and item_id not in seen_ids and item_id not in processed_sc_ids:
                        try:
                            sc_dt = datetime.fromisoformat(sc.get('scheduled_at').replace('Z', '+00:00'))
                            if sc_dt <= now_dt:
                                seen_ids.add(item_id)
                                due_calls.append(sc)
                        except Exception:
                            pass

                if due_calls:
                    logging.info(f"Scheduled Call Worker: Found {len(due_calls)} due call(s) to execute!")
                    for sc in due_calls:
                        logging.info(f"  Due call: {sc.get('caller_name')} ({sc.get('caller_phone')}), scheduled_at={sc.get('scheduled_at')}, now_utc={now_dt.isoformat()}")
                        sc_id = sc.get('id')
                        if sc_id:
                            processed_sc_ids.add(sc_id)
                            
                        b_id = sc.get('business_id')
                        c_phone = sc.get('caller_phone')
                        c_name = sc.get('caller_name') or 'Scheduled Prospect'
                        c_email = sc.get('caller_email') or ''
                        c_company = sc.get('company') or ''
                        c_vars = sc.get('custom_variables') or {}

                        # Mark status as calling
                        sc['status'] = 'calling'
                        try:
                            patch_url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?id=eq.{sc_id}"
                            patch_req = urllib.request.Request(patch_url, data=json_module.dumps({'status': 'calling'}).encode('utf-8'), method='PATCH')
                            patch_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                            patch_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                            patch_req.add_header('Content-Type', 'application/json')
                            urllib.request.urlopen(patch_req, timeout=5)
                        except Exception:
                            pass

                        res = trigger_outbound_call(
                            phone_number=c_phone,
                            name=c_name,
                            email=c_email,
                            company=c_company,
                            business_id=b_id,
                            custom_variables=c_vars
                        )

                        new_status = 'completed' if res and res.get('success') else 'failed'
                        sc['status'] = new_status
                        try:
                            patch_url2 = f"{SUPABASE_URL}/rest/v1/scheduled_calls?id=eq.{sc_id}"
                            patch_req2 = urllib.request.Request(patch_url2, data=json_module.dumps({'status': new_status}).encode('utf-8'), method='PATCH')
                            patch_req2.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                            patch_req2.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                            patch_req2.add_header('Content-Type', 'application/json')
                            urllib.request.urlopen(patch_req2, timeout=5)
                        except Exception:
                            pass

            except Exception as e:
                logging.debug(f"Scheduler worker tick error: {e}")

            time.sleep(15)

    threading.Thread(target=scheduler_worker, daemon=True).start()

# Start background scheduler thread
start_call_scheduler_loop()

# --- Health check server (keeps Render free tier alive) ---
class HealthHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE, PATCH')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Max-Age', '86400')

    def do_GET(self):
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"AI Telephony Agent is running")
        elif self.path == '/api/call-logs':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            logs = load_call_logs()
            self.wfile.write(json_module.dumps(logs).encode())
        elif self.path.startswith('/api/scheduled-calls'):
            try:
                url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?select=*&order=scheduled_at.asc"
                headers = {'apikey': SUPABASE_SERVICE_ROLE_KEY, 'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}'}
                s_req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(s_req) as resp:
                    data = resp.read()
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(data)
            except Exception as e:
                self.send_response(200)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'[]')
        elif self.path == '/api/analytics':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            logs = load_call_logs()
            total_calls = len(logs)
            completed = sum(1 for l in logs if l.get('status') == 'completed')
            success_rate = round((completed / total_calls * 100), 1) if total_calls > 0 else 0
            delighted = sum(1 for l in logs if l.get('sentiment') == 'Delighted')
            interested = sum(1 for l in logs if l.get('sentiment') == 'Interested')
            sentiment_score = round(((delighted + interested * 0.7) / total_calls * 100), 1) if total_calls > 0 else 0
            cta_calls = sum(1 for l in logs if l.get('source') == 'cta_form')
            instant_calls = sum(1 for l in logs if l.get('source') == 'instant_call')
            analytics = {
                'total_calls': total_calls,
                'success_rate': success_rate,
                'sentiment_score': min(sentiment_score, 100),
                'avg_duration': '1m 00s',
                'cta_calls': cta_calls,
                'instant_calls': instant_calls,
                'recent_calls': logs[:10]
            }
            self.wfile.write(json_module.dumps(analytics).encode())
        elif self.path == '/api/config':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json_module.dumps(load_agent_config()).encode())
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith('/api/scheduled-calls'):
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json_module.loads(post_data.decode('utf-8'))
                sc_id = data.get('id')
                if sc_id:
                    patch_url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?id=eq.{sc_id}"
                    patch_req = urllib.request.Request(patch_url, data=json_module.dumps({'status': 'cancelled'}).encode('utf-8'), method='PATCH')
                    patch_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                    patch_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                    patch_req.add_header('Content-Type', 'application/json')
                    try:
                        urllib.request.urlopen(patch_req)
                    except Exception:
                        pass
                self.send_response(200)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"success"}')
            except Exception as e:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json_module.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                new_cfg = json_module.loads(post_data)
                save_agent_config(new_cfg)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json_module.dumps({"status": "success", "config": new_cfg}).encode())
            except Exception as e:
                logging.error(f"Failed to save config via API: {e}")
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Failed to save configuration"}')
        elif self.path == '/api/make-call':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json_module.loads(post_data)
                phone_number = data.get("to_number", "").strip()
                name = data.get("name", "there")
                visitor_email = data.get("email", "")
                company = data.get("company", "")
                business_id = data.get("business_id", None)
                custom_vars = data.get("custom_variables", None)

                res = trigger_outbound_call(
                    phone_number=phone_number,
                    name=name,
                    email=visitor_email,
                    company=company,
                    business_id=business_id,
                    custom_variables=custom_vars
                )

                try:
                    if res.get("success"):
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json_module.dumps({"status": "success", "message": f"Calling {phone_number}..."}).encode())
                    else:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json_module.dumps({"error": res.get("error", "Call failed")}).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass
            except Exception as e:
                logging.error(f"Failed to parse request: {e}")
                try:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Invalid request body"}')
                except (BrokenPipeError, ConnectionResetError):
                    pass
        elif self.path == '/api/schedule-call':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                req_data = json_module.loads(post_data.decode('utf-8'))
                calls_list = req_data.get('calls') or []
                execute_now = req_data.get('execute_now', False)

                for c in calls_list:
                    if 'id' not in c or not c['id']:
                        import uuid
                        c['id'] = str(uuid.uuid4())
                    
                    if execute_now:
                        trigger_outbound_call(
                            phone_number=c.get('caller_phone'),
                            name=c.get('caller_name'),
                            email=c.get('caller_email'),
                            company=c.get('company'),
                            business_id=c.get('business_id'),
                            custom_variables=c.get('custom_variables')
                        )
                    else:
                        IN_MEMORY_SCHEDULED_CALLS.append(c)
                        url = f"{SUPABASE_URL}/rest/v1/scheduled_calls"
                        headers = {
                            'apikey': SUPABASE_SERVICE_ROLE_KEY,
                            'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                            'Content-Type': 'application/json'
                        }
                        sc_payload = json_module.dumps(c).encode('utf-8')
                        s_req = urllib.request.Request(url, data=sc_payload, method='POST', headers=headers)
                        try:
                            urllib.request.urlopen(s_req)
                        except Exception as se:
                            logging.warning(f"Error saving scheduled call to Supabase: {se}")

                self.send_response(200)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json_module.dumps({"status": "success", "scheduled_count": len(calls_list)}).encode())
            except Exception as e:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json_module.dumps({"error": str(e)}).encode())
        elif self.path == '/api/trigger-scheduled-now':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                req_data = json_module.loads(post_data.decode('utf-8'))
                sc_id = req_data.get('id')
                if sc_id:
                    url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?id=eq.{sc_id}&select=*"
                    headers = {'apikey': SUPABASE_SERVICE_ROLE_KEY, 'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}'}
                    s_req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(s_req) as resp:
                        data = json_module.loads(resp.read().decode('utf-8'))
                        if data and len(data) > 0:
                            sc = data[0]
                            trigger_outbound_call(
                                phone_number=sc.get('caller_phone'),
                                name=sc.get('caller_name'),
                                email=sc.get('caller_email'),
                                company=sc.get('company'),
                                business_id=sc.get('business_id'),
                                custom_variables=sc.get('custom_variables')
                            )
                            patch_url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?id=eq.{sc_id}"
                            patch_req = urllib.request.Request(patch_url, data=json_module.dumps({'status': 'completed'}).encode('utf-8'), method='PATCH')
                            patch_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                            patch_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                            patch_req.add_header('Content-Type', 'application/json')
                            try:
                                urllib.request.urlopen(patch_req)
                            except Exception:
                                pass
                self.send_response(200)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status":"success"}')
            except Exception as e:
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json_module.dumps({"error": str(e)}).encode())
                self._send_cors_headers()
                self.end_headers()
        elif self.path == '/api/webhook':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                wb_data = json_module.loads(post_data.decode('utf-8'))
                logging.info(f"Received Webhook notification: {wb_data}")
                
                webhook_type = str(wb_data.get("webhookType") or wb_data.get("event") or "").lower()
                wb_payload = wb_data.get("data") if isinstance(wb_data.get("data"), dict) else {}
                call_id = wb_payload.get("callId") or wb_data.get("callId")
                status = str(wb_payload.get("status") or wb_data.get("status") or "").lower()

                if webhook_type == 'call-missed' or status == 'missed':
                    logging.info("VideoSDK Webhook reported call-missed. Updating call log to missed.")
                    update_call_log_status_in_supabase(
                        call_id=call_id,
                        status='missed',
                        duration='0m 00s',
                        sentiment='Unanswered',
                        transcript=[{'speaker': 'system', 'name': 'System', 'text': 'Call was missed or unanswered by recipient.'}]
                    )
                elif webhook_type == 'call-answered' or status == 'answered':
                    update_call_log_status_in_supabase(
                        call_id=call_id,
                        status='in-progress',
                        duration='--',
                        sentiment=''
                    )
                elif webhook_type == 'call-hangup' or status == 'ended':
                    room_id = wb_payload.get("roomId") or wb_data.get("roomId")
                    parsed = parse_videosdk_transcript_payload(wb_data)
                    if not parsed:
                        parsed = fetch_videosdk_session_transcript_from_api(room_id=room_id, session_id=call_id)

                    update_call_log_status_in_supabase(
                        call_id=call_id,
                        status='completed',
                        duration='--',
                        sentiment='Completed',
                        transcript=parsed if parsed else None
                    )

                    # Trigger asynchronous 5-second delayed poll to catch late-indexed VideoSDK transcripts
                    threading.Thread(target=fetch_and_update_final_transcript_async, args=(call_id, room_id)).start()

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception as e:
                logging.error(f"Webhook processing error: {e}")
                self.send_response(200)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # Suppress generic request logs

def start_health_server():
    port = int(os.getenv("PORT", 8081))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Health check server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    try:
        # Start background scheduled call polling loop
        start_call_scheduler_loop()

        # Start HTTP API server for webhooks, instant call triggers, call logs, analytics & health checks
        port = int(os.getenv("PORT", 8081))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logging.info(f"AI Telephony API Server running on port {port}...")
        server.serve_forever()
    except Exception as e:
        traceback.print_exc()
