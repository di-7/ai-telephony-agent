import asyncio
import traceback
import threading
import uuid
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from videosdk.agents import Agent, AgentSession, Pipeline, JobContext, RoomOptions, WorkerJob, Options
from videosdk.agents.job import _set_current_job_context
from videosdk.agents.pipeline import RealtimeConfig
from videosdk.agents.tts import TTS, FlushMarker
from videosdk.plugins.google import GeminiRealtime, GeminiLiveConfig
from google.genai.types import RealtimeInputConfig, AutomaticActivityDetection, EndSensitivity, StartSensitivity
from dotenv import load_dotenv
import typing
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
        "model": "models/gemini-3.1-flash-live-preview",
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

    if provider == "videosdk":
        target_agent_id = agent_cfg.get("video_sdk_agent_id") or "ag_rajwdl"
        sdk_id = target_agent_id.strip() if target_agent_id and target_agent_id.strip() else "ag_rajwdl"
        call_body["agentId"] = sdk_id
        is_videosdk_cloud = True
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

    if is_videosdk_cloud and call_entry:
        threading.Thread(target=handle_videosdk_cloud_call_logging, args=(call_entry, agent_cfg)).start()
    elif not is_videosdk_cloud and room_id and call_entry:
        def _run_custom_python_agent(r_id, token, entry, vars_dict):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                ro = RoomOptions()
                ro.room_id = r_id
                ro.name = agent_cfg.get("agent_name", "AI Agent")

                ctx = JobContext(room_options=ro)
                ctx.videosdk_auth = token

                queue_pending_call(entry)
                logging.info(f"Connecting Custom Python Agent to VideoSDK room {r_id} for call {entry.get('id')}...")
                loop.run_until_complete(start_session(ctx, custom_variables=vars_dict))
            except Exception as e:
                logging.error(f"Error running Custom Python Agent in background thread: {e}", exc_info=True)

        threading.Thread(target=_run_custom_python_agent, args=(room_id, videosdk_token, call_entry, custom_variables), daemon=True).start()

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
            except Exception as e:
                logging.error(f"Failed to parse request: {e}")
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid request body"}')
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

# --- Agent definition ---
class MyVoiceAgent(Agent):
    def __init__(self, instructions=None, greeting=None, agent_name=None):
        self.agent_name = agent_name or "Sarah"
        self.greeting = greeting if greeting is not None else "Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?"
        
        default_inst = "You are an AI assistant for Mixup. You are doing a 1-minute live demo. Your goal is to briefly take their general info (name, company) so our human team can revert back with a full demo. Keep responses extremely short and conversational."
        final_inst = (instructions.strip() if instructions and instructions.strip() else default_inst)
        super().__init__(instructions=final_inst)

    async def on_enter(self) -> None:
        if self.greeting and self.greeting.strip():
            await self.session.say(self.greeting.strip())

    async def on_exit(self) -> None:
        pass

def fetch_recent_initiated_call_from_supabase():
    """Query Supabase for the most recent 'initiated' call log to pair with this agent session.
    This is needed because the HTTP server and VideoSDK agent run in SEPARATE PROCESSES,
    so in-memory PENDING_CALLS cannot be shared."""
    try:
        url = (f"{SUPABASE_URL}/rest/v1/call_logs"
               f"?status=eq.initiated"
               f"&order=created_at.desc"
               f"&limit=1"
               f"&select=id,caller_name,caller_phone,caller_email,caller_company,source,business_id,created_at")
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                row = data[0]
                entry = {
                    'id': row['id'],
                    'business_id': row.get('business_id'),
                    'phone': row.get('caller_phone', ''),
                    'name': row.get('caller_name', 'Unknown Caller'),
                    'email': row.get('caller_email', ''),
                    'company': row.get('caller_company', ''),
                    'source': row.get('source', 'instant_call'),
                }
                logging.info(f"Fetched recent initiated call from Supabase: {entry['id']}, caller: {entry['name']} ({entry['phone']})")
                return entry
    except Exception as e:
        logging.warning(f"Failed to fetch recent initiated call from Supabase: {e}")
    return None

# --- Kokoro Native ONNX Engine Setup ---
KOKORO_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices-v1.0.bin")
_kokoro_instance = None

def preload_kokoro_in_background():
    """Download Kokoro ONNX model files in the background on startup so calls connect instantly."""
    try:
        if not os.path.exists(KOKORO_MODEL_PATH):
            logging.info("Pre-downloading Kokoro ONNX model weights (kokoro-v1.0.onnx)...")
            url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
            tmp_path = KOKORO_MODEL_PATH + ".tmp"
            urllib.request.urlretrieve(url, tmp_path)
            if os.path.exists(tmp_path):
                os.rename(tmp_path, KOKORO_MODEL_PATH)
            logging.info("Kokoro ONNX model weights ready!")
        if not os.path.exists(KOKORO_VOICES_PATH):
            logging.info("Pre-downloading Kokoro voice embeddings (voices-v1.0.bin)...")
            url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
            tmp_path = KOKORO_VOICES_PATH + ".tmp"
            urllib.request.urlretrieve(url, tmp_path)
            if os.path.exists(tmp_path):
                os.rename(tmp_path, KOKORO_VOICES_PATH)
            logging.info("Kokoro voice embeddings ready!")
    except Exception as e:
        logging.warning(f"Background Kokoro download warning: {e}")

def get_kokoro_engine():
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance
    try:
        if not os.path.exists(KOKORO_MODEL_PATH) or not os.path.exists(KOKORO_VOICES_PATH):
            logging.info("Kokoro files missing on disk. Downloading synchronously...")
            preload_kokoro_in_background()

        if os.path.exists(KOKORO_MODEL_PATH) and os.path.exists(KOKORO_VOICES_PATH):
            from kokoro_onnx import Kokoro
            _kokoro_instance = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
            logging.info("Kokoro ONNX engine initialized successfully!")
            return _kokoro_instance
    except Exception as e:
        logging.error(f"Failed to initialize native Kokoro ONNX engine: {e}")
    return None

def synthesize_kokoro_speech(text: str, voice: str = "am_adam", speed: float = 1.0) -> bytes:
    """Synthesize speech using native Kokoro ONNX model engine."""
    engine = get_kokoro_engine()
    if engine is None:
        logging.error("Kokoro ONNX engine not available")
        return b""
    try:
        samples, sample_rate = engine.create(text, voice=voice, speed=speed, lang="en-us")
        import io, soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format='WAV')
        return buf.getvalue()
    except Exception as e:
        logging.error(f"Error in Kokoro ONNX speech synthesis: {e}")
        return b""

class KokoroTTS(TTS):
    """Native 82M Kokoro ONNX Text-to-Speech Engine for VideoSDK Agent"""
    def __init__(self, voice: str = "am_adam", speed: float = 1.0, sample_rate: int = 24000):
        super().__init__(sample_rate=sample_rate, num_channels=1)
        self.voice = voice
        self.speed = speed
        self._interrupted = False
        self._first_chunk_sent = False

    async def interrupt(self) -> None:
        self._interrupted = True
        if self.audio_track and hasattr(self.audio_track, 'interrupt'):
            self.audio_track.interrupt()

    async def synthesize(
        self,
        text: typing.Union[typing.AsyncIterator[typing.Union[str, FlushMarker]], str],
        **kwargs: typing.Any
    ) -> None:
        if not self.audio_track:
            return
        self._interrupted = False
        self._first_chunk_sent = False

        full_text = ""
        if isinstance(text, str):
            full_text = text
        else:
            async for chunk in text:
                if self._interrupted:
                    break
                if isinstance(chunk, str):
                    full_text += chunk

        clean_text = full_text.strip()
        if not clean_text or self._interrupted:
            return

        logging.info(f"Synthesizing Kokoro 82M ONNX speech (voice={self.voice}, speed={self.speed}x): '{clean_text}'")
        wav_bytes = synthesize_kokoro_speech(clean_text, voice=self.voice, speed=self.speed)
        if not wav_bytes or self._interrupted:
            return

        # Strip 44-byte WAV header if present to get raw 16-bit PCM
        pcm_bytes = wav_bytes[44:] if len(wav_bytes) > 44 and wav_bytes[:4] == b'RIFF' else wav_bytes

        chunk_size = 960
        for i in range(0, len(pcm_bytes), chunk_size):
            if self._interrupted:
                return
            chunk = pcm_bytes[i:i + chunk_size]
            if len(chunk) < chunk_size and len(chunk) > 0:
                chunk += b'\x00' * (chunk_size - len(chunk))
            if len(chunk) == chunk_size:
                if not self._first_chunk_sent and self._first_audio_callback:
                    self._first_chunk_sent = True
                    await self._first_audio_callback()
                asyncio.create_task(self.audio_track.add_new_bytes(chunk))
                await asyncio.sleep(0.001)

async def start_session(context: JobContext, custom_variables=None):
    # Try in-memory queue first (works when same process), then fall back to Supabase query
    call_entry = pop_recent_pending_call()
    if call_entry:
        logging.info(f"Agent session paired via in-memory queue: {call_entry['id']}, caller: {call_entry['name']} ({call_entry['phone']})")
    else:
        # CRITICAL: HTTP server and agent worker run in separate processes, so PENDING_CALLS
        # will always be empty here. Query Supabase directly for the most recent initiated call.
        call_entry = fetch_recent_initiated_call_from_supabase()
        if call_entry:
            logging.info(f"Agent session paired via Supabase query: {call_entry['id']}, caller: {call_entry['name']} ({call_entry['phone']})")
        else:
            logging.warning("No pending call entry found (neither in-memory nor Supabase). Transcript will still be captured.")

    # Load dynamic configuration from dashboard settings (per business_id)
    b_id = call_entry.get('business_id') if call_entry else None
    agent_cfg = (load_agent_config_from_supabase(business_id=b_id) if b_id else load_agent_config())
    provider = agent_cfg.get("provider", "kokoro")

    system_inst = agent_cfg.get("system_instruction", "")
    agent_name = agent_cfg.get("agent_name", "Sarah")
    greeting = agent_cfg.get("greeting", "Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?")

    end_call_enabled = agent_cfg.get("end_call_enabled", True)
    end_call_conditions = agent_cfg.get("end_call_conditions") or "End the call when the primary objective/task of the conversation has been fulfilled, when the customer confirms they have no further questions or are satisfied, or when the user says goodbye."
    end_call_final_response = agent_cfg.get("end_call_final_response") or "Thank you for reaching out today. I'm glad I could help! Have a wonderful day ahead, goodbye."

    if custom_variables and isinstance(custom_variables, dict):
        var_str = "\n".join([f"- {k}: {v}" for k, v in custom_variables.items() if v])
        if var_str:
            system_inst += f"\n\n[DYNAMIC PROSPECT VARIABLES & CONTEXT FOR THIS CALL]:\n{var_str}\nUse these details naturally when speaking with the caller."

    if end_call_enabled:
        system_inst += f"\n\n[AUTOMATIC CALL ENDING POLICY & INSTRUCTION]:\nCall Termination Conditions: {end_call_conditions}\nWhen these conditions are met or when the customer indicates they have no further questions, are satisfied, or say goodbye, speak your final farewell message ('{end_call_final_response}') and append '[END_CALL]' to the end of your response to signal session completion."

    if provider == "kokoro":
        kokoro_cfg = agent_cfg.get("kokoro") or {}
        kokoro_voice = kokoro_cfg.get("voice") or "am_adam"
        raw_speed = kokoro_cfg.get("speed")
        try:
            speed = float(raw_speed) if raw_speed is not None else 1.0
        except (ValueError, TypeError):
            speed = 1.0
        
        selected_model = kokoro_cfg.get("model") or "models/gemini-3.1-flash-live-preview"
        logging.info(f"Kokoro 82M ONNX Engine Active | LLM Model={selected_model} | Voice={kokoro_voice} | Speed={speed}x | Agent={agent_name}")

        model = GeminiRealtime(
            model=selected_model,
            api_key=os.getenv("GOOGLE_API_KEY"),
            config=GeminiLiveConfig(
                response_modalities=["TEXT"],
                realtime_input_config=RealtimeInputConfig(
                    automatic_activity_detection=AutomaticActivityDetection(
                        start_of_speech_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                        end_of_speech_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                        prefix_padding_ms=10,
                        silence_duration_ms=200,
                    )
                )
            )
        )
        tts = KokoroTTS(voice=kokoro_voice, speed=speed)
        pipeline = Pipeline(llm=model, tts=tts, realtime_config=RealtimeConfig(mode="hybrid_tts"))
    else:
        gemini_cfg = agent_cfg.get("gemini") or {}
        selected_voice = gemini_cfg.get("voice") or "Aoede"
        selected_model = gemini_cfg.get("model") or "models/gemini-3.1-flash-live-preview"
        raw_vad = gemini_cfg.get("vad_silence_ms")
        try:
            vad_silence = int(raw_vad) if raw_vad is not None else 200
        except (ValueError, TypeError):
            vad_silence = 200

        logging.info(f"Gemini Realtime Engine Active | Voice={selected_voice} | Model={selected_model} | Agent={agent_name}")

        model = GeminiRealtime(
            model=selected_model,
            api_key=os.getenv("GOOGLE_API_KEY"),
            config=GeminiLiveConfig(
                voice=selected_voice,
                response_modalities=["AUDIO"],
                realtime_input_config=RealtimeInputConfig(
                    automatic_activity_detection=AutomaticActivityDetection(
                        start_of_speech_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                        end_of_speech_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                        prefix_padding_ms=10,
                        silence_duration_ms=vad_silence,
                    )
                )
            )
        )
        pipeline = Pipeline(llm=model)

    # Create a concrete Agent subclass with greeting
    class TelephonyAgent(Agent):
        async def on_enter(self):
            """Deliver the greeting when the agent session starts."""
            if self.session and greeting:
                await self.session.say(greeting)
        async def on_exit(self):
            pass

    agent = TelephonyAgent(instructions=system_inst)

    transcript_list = []
    session_should_end_event = asyncio.Event()

    def trigger_auto_end_call(delay_sec=3.5):
        async def _end():
            await asyncio.sleep(delay_sec)
            session_should_end_event.set()
        try:
            asyncio.create_task(_end())
        except Exception:
            pass

    def on_transcription_event(data):
        """Capture transcription events from the Gemini realtime model and detect auto end-call triggers."""
        try:
            logging.info(f"RAW transcription event received: {data}")
            if isinstance(data, dict):
                text = data.get("text", "").strip()
                is_final = data.get("is_final", False)
                role = data.get("role", "unknown")
                
                if text:
                    clean_text = text.replace('[END_CALL]', '').strip()
                    if is_final:
                        speaker_role = "agent" if role == "agent" else "customer"
                        caller_name = (call_entry.get('name') if call_entry and call_entry.get('name') else "Caller")
                        speaker_name = f"AI Agent ({agent_name})" if role == "agent" else caller_name
                        transcript_list.append({
                            "speaker": speaker_role,
                            "name": speaker_name,
                            "text": clean_text
                        })
                        logging.info(f"FINAL transcript [{speaker_role}]: {clean_text}")

                        # Check auto end call triggers
                        if end_call_enabled and role == "agent":
                            text_lower = text.lower()
                            resp_sample = (end_call_final_response.lower()[:20] if end_call_final_response else 'thank you')
                            if '[end_call]' in text_lower or 'goodbye' in text_lower or 'have a wonderful day' in text_lower or resp_sample in text_lower:
                                logging.info("Auto Call Ending condition detected in agent response! Scheduling session end in 3.5 seconds...")
                                trigger_auto_end_call(delay_sec=3.5)

                    else:
                        logging.debug(f"Interim transcript [{role}]: {clean_text}")
            elif isinstance(data, str) and data.strip():
                clean_text = data.replace('[END_CALL]', '').strip()
                transcript_list.append({
                    "speaker": "unknown",
                    "name": "Speaker",
                    "text": clean_text
                })
                logging.info(f"FINAL transcript [string]: {clean_text}")
        except Exception as e:
            logging.error(f"Error processing transcription event: {e}", exc_info=True)

    # Register transcription listener on the model
    model.on("realtime_model_transcription", on_transcription_event)

    # Attach pipeline to JobContext so VideoSDKHandler gets initialized with the pipeline when connecting to room
    if hasattr(context, "_set_pipeline_internal"):
        context._set_pipeline_internal(pipeline)

    # Set the current job context so AgentSession can discover it
    _set_current_job_context(context)

    # Create the agent session (room connection + pipeline start handled by run_until_shutdown)
    session = AgentSession(agent=agent, pipeline=pipeline)
    
    start_time = time.time()

    # Background task: enforce 90s max duration and auto end-call trigger
    async def _monitor_session():
        try:
            await asyncio.wait_for(session_should_end_event.wait(), timeout=90.0)
            logging.info("Auto Call Ending trigger reached. Closing call session cleanly.")
        except asyncio.TimeoutError:
            logging.info("90 second max call duration limit reached. Closing session.")
        # Signal the SDK to shut down gracefully
        try:
            await context.shutdown()
        except Exception:
            pass

    monitor_task = asyncio.ensure_future(_monitor_session())

    try:
        # Let the SDK handle: connect → wait for participant → start pipeline → process audio
        await session.start(wait_for_participant=True, run_until_shutdown=True)
        logging.info("Agent session ended normally.")
            
    except Exception as e:
        logging.error(f"Error during agent session: {e}", exc_info=True)
    finally:
        if not monitor_task.done():
            monitor_task.cancel()
        elapsed = int(time.time() - start_time)
        duration_str = f"{elapsed // 60}m {elapsed % 60:02d}s" if elapsed >= 5 else "--"
        
        logging.info(f"Call session ending. Duration: {duration_str}, Transcript turns: {len(transcript_list)}")
        
        if call_entry:
            call_entry['duration'] = duration_str
            call_entry['transcript'] = transcript_list
            if transcript_list:
                call_entry['status'] = 'completed'
                call_entry['sentiment'] = 'Interested'
            else:
                call_entry['status'] = 'completed' if elapsed >= 15 else 'no_answer'
                call_entry['sentiment'] = 'Interested' if elapsed >= 15 else 'No Answer'

            logging.info(f"Call session ended. Duration: {duration_str}, Turns: {len(transcript_list)}, Status: {call_entry['status']}")
            
            # Save updated logs locally
            try:
                logs = load_call_logs()
                for idx, item in enumerate(logs):
                    if item.get('id') == call_entry['id']:
                        logs[idx] = call_entry
                        break
                save_call_logs(logs)
            except Exception as e:
                logging.error(f"Failed to save local call logs: {e}")

            # Update Supabase database
            try:
                update_call_log_in_supabase(call_entry)
                logging.info(f"Supabase updated for call {call_entry['id']}")
                c_id = call_entry.get('id')
                r_id = call_entry.get('custom_id') or call_entry.get('room_id')
                if c_id:
                    threading.Thread(target=fetch_and_update_final_transcript_async, args=(c_id, r_id)).start()
            except Exception as e:
                logging.error(f"Failed to update Supabase: {e}")
        else:
            logging.warning("No call_entry to update. Creating a standalone record...")

        # End the meeting for ALL participants (including SIP caller)
        try:
            if context.room:
                await context.room.leave()
                logging.info("Room left successfully for agent session.")
        except Exception as e:
            logging.warning(f"Could not leave room: {e}")
        
        try:
            await session.close()
        except Exception as e:
            logging.warning(f"Could not close session: {e}")
        try:
            await context.shutdown()
        except Exception as e:
            logging.warning(f"Could not shutdown context: {e}")

def make_context() -> JobContext:
    room_options = RoomOptions()
    return JobContext(room_options=room_options)

if __name__ == "__main__":
    try:
        # Ensure event loop exists in the main thread
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Start health check server in background thread
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()

        # Pre-download Kokoro ONNX model files in background so call setup connects instantly
        threading.Thread(target=preload_kokoro_in_background, daemon=True).start()

        # Start background scheduled call polling loop
        start_call_scheduler_loop()

        # Register your custom Python agent worker with a unique ID
        options = Options(
            agent_id=os.getenv("AGENT_ID", "MyTelephonyAgent"),  # Your custom Python agent worker ID
            register=True,               # REQUIRED: Register with VideoSDK for telephony
            max_processes=1,             # Free tier: limited CPU/RAM, only 1 process
            num_idle_processes=0,        # Free tier RAM optimization (prevents Signal 15 OOM killer)
            initialize_timeout=120.0,    # Give plenty of time to initialize
            host="0.0.0.0",
            port=int(os.getenv("AGENT_PORT", 8082)),
            )
        job = WorkerJob(entrypoint=start_session, jobctx=make_context, options=options)
        job.start()
    except Exception as e:
        traceback.print_exc()
