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

load_dotenv()

import json as json_module
import time
from datetime import datetime, timezone

# --- Supabase Configuration ---
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

# --- Call Log Storage (JSON file-based) ---
CALL_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'call_logs.json')

def load_call_logs():
    """Load call logs from Supabase cloud database with local file fallback."""
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
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
    "provider": "videosdk",
    "video_sdk_agent_id": ""
}

def load_agent_config_from_supabase(business_id=None):
    """Fetch the latest active agent configuration from Supabase agent_configs table (or fallback call_logs)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None

    # 1. Try dedicated agent_configs table with business_id filter
    if business_id:
        try:
            url = f"{SUPABASE_URL}/rest/v1/agent_configs?business_id=eq.{business_id}&select=*&limit=1"
            req = urllib.request.Request(url, headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json_module.loads(resp.read().decode('utf-8'))
                if data and len(data) > 0:
                    rec = data[0]
                    config = rec.get('config') if isinstance(rec.get('config'), dict) else json_module.loads(rec.get('config', '{}'))
                    if config and config.get('video_sdk_agent_id'):
                        logging.info(f"Loaded config from Supabase agent_configs for business_id={business_id}: provider={config.get('provider')}, agent_id={config.get('video_sdk_agent_id')}")
                        return config
        except Exception as e:
            logging.debug(f"Could not load business-specific agent config from agent_configs table: {e}")

    # 2. Try global/default agent_configs (no business_id filter)
    try:
        url = f"{SUPABASE_URL}/rest/v1/agent_configs?select=*&order=created_at.desc&limit=1"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_module.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                rec = data[0]
                config = rec.get('config') if isinstance(rec.get('config'), dict) else json_module.loads(rec.get('config', '{}'))
                if config and config.get('video_sdk_agent_id'):
                    logging.info(f"Loaded default config from Supabase agent_configs: provider={config.get('provider')}, agent_id={config.get('video_sdk_agent_id')}")
                    return config
    except Exception as e:
        logging.debug(f"Could not load default agent config from agent_configs table: {e}")

    # 3. Fallback to call_logs table (legacy)
    if business_id:
        try:
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
                    logging.info(f"Loaded agent config from Supabase call_logs fallback for business_id={business_id}")
                    return config
        except Exception as e:
            logging.debug(f"Could not load agent config from call_logs fallback: {e}")
    
    return None

def save_agent_config_to_supabase(config_data, business_id=None):
    """Persist agent configuration to Supabase agent_configs table."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return False
    b_id = business_id or "c16fc8ab-3bb2-44fe-88ed-560f950c8069"
    try:
        url = f"{SUPABASE_URL}/rest/v1/agent_configs?on_conflict=business_id"
        payload = {
            "business_id": b_id,
            "provider": config_data.get("provider", "videosdk"),
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

    """Load local agent configuration from agent_config.json."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json_module.load(f)
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
        logging.error(f"Failed to generate dynamic VideoSDK token via PyJWT: {e}")
        return os.getenv("VIDEOSDK_AUTH_TOKEN")

def create_videosdk_room_with_transcription(videosdk_token, custom_room_id=None):
    """Create a new VideoSDK room with real-time transcription enabled. Recording will be started via API when call is answered."""
    create_room_url = "https://api.videosdk.live/v2/rooms"
    req = urllib.request.Request(create_room_url, method="POST")
    req.add_header("Authorization", str(videosdk_token))
    req.add_header("Content-Type", "application/json")
    
    body = {
        "autoStartTranscription": True,
        "transcription": {
            "enabled": True,
            "summary": {
                "enabled": True,
                "prompt": "Summarize this telephony sales session, listing key interest areas and follow-up items."
            }
        }
    }
    # Recording is started via API when call-answered webhook is received
    # This allows us to control recording lifecycle and fetch recordings after call ends
    
    if custom_room_id:
        body["customRoomId"] = custom_room_id
        
    try:
        data = json_module.dumps(body).encode('utf-8')
        req.data = data
        with urllib.request.urlopen(req) as response:
            resp_body = response.read()
            resp_json = json_module.loads(resp_body.decode('utf-8'))
            room_id = resp_json.get("roomId") or resp_json.get("id")
            logging.info(f"Created VideoSDK room {room_id} with transcription enabled. Recording will start when call is answered.")
            return room_id
    except Exception as e:
        logging.error(f"Failed to create VideoSDK room: {e}")
        return None

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
    
    # Load agent configuration dynamically for this business
    agent_cfg = load_agent_config_from_supabase(business_id=business_id) or load_agent_config()
    provider = agent_cfg.get("provider", "videosdk")
    
    # Log the configuration being used
    logging.info(f"Using agent config for business_id={business_id}: provider={provider}, video_sdk_agent_id={agent_cfg.get('video_sdk_agent_id', 'NOT SET')}")

    import time
    custom_meeting_id = f"{phone_number.replace('+', '')}-{int(time.time())}"
    room_id = create_videosdk_room_with_transcription(videosdk_token, custom_meeting_id)

    call_body = {
        "gatewayId": gateway_id,
        "sipCallTo": phone_number
    }
    if room_id:
        call_body["destinationRoomId"] = room_id
    
    # Get the agent ID - either from business config or environment fallback
    target_agent_id = (agent_cfg.get("video_sdk_agent_id") or os.getenv("VIDEOSDK_AGENT_ID", "")).strip()
    
    if target_agent_id:
        call_body["agentId"] = target_agent_id
        logging.info(f"Routing call to VideoSDK Cloud Agent Builder ID: '{target_agent_id}' for business_id={business_id}")
    else:
        logging.warning(f"No agent ID configured for business_id={business_id}. Agent responses may not work properly.")

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
        # Store room_id in the call entry for later transcript fetching via webhook
        call_entry['room_id'] = room_id
        if target_agent_id:
            logging.info(f"VideoSDK Cloud Agent Builder ({target_agent_id}) is active for call {call_entry.get('id')}, room {room_id}")
        else:
            logging.warning(f"⚠️  NO AGENT ID CONFIGURED - Call {call_entry.get('id')} may not receive responses!")
            logging.warning(f"⚠️  Configure agent: POST /api/config with video_sdk_agent_id field")

    return {"success": True, "call_id": sdk_call_id, "room_id": room_id}

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
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
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
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception as e:
        logging.error(f"Failed to update call log in Supabase: {e}")

def update_call_log_status_in_supabase(call_id=None, status='completed', duration='--', sentiment='Completed', transcript=None):
    """Helper to update call status by call_id or sdk_id in Supabase."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not call_id:
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{call_id}"
        payload_data = {'status': status}
        if duration != '--':
            payload_data['duration'] = duration
        if sentiment:
            payload_data['sentiment'] = sentiment
        if transcript is not None:
            payload_data['transcript'] = json_module.dumps(transcript) if isinstance(transcript, list) else transcript

        req = urllib.request.Request(url, data=json_module.dumps(payload_data).encode('utf-8'), method='PATCH')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=5) as resp:
            logging.info(f"Updated call log status in Supabase for call_id {call_id} to '{status}'")
    except Exception as e:
        logging.warning(f"Could not update call log status in Supabase for {call_id}: {e}")

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
        name = (cfg.get("agent_name") or "").strip()
        return name if name else "AI Agent"
    except Exception:
        return "AI Agent"

def get_agent_name_from_supabase(b_id=None):
    """Fetch configured agent name dynamically from Supabase."""
    try:
        cfg = (load_agent_config_from_supabase(business_id=b_id) if b_id else load_agent_config()) or {}
        name = (cfg.get("agent_name") or "").strip()
        return name if name else "AI Agent"
    except Exception:
        return "AI Agent"

def parse_videosdk_transcript_payload(wb_data, caller_name=None, agent_name=None):
    """Parse diarized transcript items directly from VideoSDK Agent Builder API payload using dynamic caller and agent names."""
    if not wb_data:
        return []

    a_name = (agent_name or '').strip()
    agent_display_name = f"AI Agent ({a_name})" if a_name else "AI Agent"

    c_name = (caller_name or '').strip()
    if not c_name or c_name == 'Caller':
        c_name = 'Caller'

    raw_list = []
    if isinstance(wb_data, dict):
        data_val = wb_data.get('data')
        if isinstance(data_val, list) and len(data_val) > 0:
            if isinstance(data_val[0], dict):
                raw_list = data_val[0].get('segments') or data_val[0].get('transcripts') or data_val[0].get('transcript') or data_val
            else:
                raw_list = data_val
        elif isinstance(data_val, dict):
            raw_list = data_val.get('segments') or data_val.get('transcripts') or data_val.get('transcript') or data_val.get('messages') or []

        if not raw_list:
            raw_list = (
                wb_data.get('segments') or 
                wb_data.get('transcript') or 
                wb_data.get('transcripts') or 
                wb_data.get('messages') or 
                (wb_data.get('payload') or {}).get('transcript') or 
                (wb_data.get('payload') or {}).get('segments') or []
            )
    elif isinstance(wb_data, list):
        raw_list = wb_data

    parsed_transcript = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict):
                text = (item.get('text') or item.get('message') or item.get('content') or '').strip()
                if not text:
                    continue

                spk = str(item.get('speaker') or item.get('role') or item.get('type') or item.get('sender') or '').strip().lower()
                name_attr = (item.get('name') or '').strip()

                is_user = any(k in spk for k in ['user', 'customer', 'caller', 'human']) or spk.startswith('+') or any(c.isdigit() for c in spk)
                is_agent = any(k in spk for k in ['agent', 'assistant', 'bot', 'system', 'ai']) or 'agent' in name_attr.lower()

                if is_user and not is_agent:
                    speaker_role = 'customer'
                    speaker_name = name_attr or c_name
                else:
                    speaker_role = 'agent'
                    speaker_name = name_attr or agent_display_name

                parsed_transcript.append({
                    'speaker': speaker_role,
                    'name': speaker_name,
                    'text': text
                })
            elif isinstance(item, str) and item.strip():
                parsed_transcript.append({
                    'speaker': 'agent',
                    'name': agent_display_name,
                    'text': item.strip()
                })

    # Merge consecutive turns belonging to the exact same speaker
    merged = []
    for turn in parsed_transcript:
        if not merged:
            merged.append(turn)
        else:
            prev = merged[-1]
            if prev['speaker'] == turn['speaker']:
                prev['text'] += " " + turn['text']
            else:
                merged.append(turn)

    return merged

def start_meeting_recording(room_id):
    """Start meeting recording via VideoSDK API when call is answered."""
    try:
        token = get_videosdk_token()
        if not token or not room_id:
            logging.warning(f"Cannot start recording: missing token or room_id")
            return
        
        url = "https://api.videosdk.live/v2/recordings/start"
        payload = {
            "roomId": room_id,
            "config": {
                "layout": {
                    "type": "SPOTLIGHT",
                    "priority": "PIN",
                    "gridSize": 4
                },
                "theme": "DARK",
                "mode": "video-and-audio",
                "quality": "high",
                "orientation": "landscape"
            }
        }
        
        data = json_module.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', token)
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json_module.loads(resp.read().decode('utf-8'))
            logging.info(f"✅ Meeting recording started for room {room_id}: {result}")
            
    except Exception as e:
        logging.error(f"Failed to start meeting recording for room {room_id}: {e}")

def fetch_recording_and_transcribe(call_id, room_id):
    """Fetch recording and transcribe it after call ends (webhook-triggered, not polling)."""
    try:
        import time
        
        logging.info(f"Recording fetch triggered by webhook for call_id={call_id}, room_id={room_id}")
        
        # Wait for VideoSDK to process recording (increased to 90s for meeting recordings)
        time.sleep(90)
        
        token = get_videosdk_token()
        duration_str = '--'
        transcript = []
        session_id = None
        
        # Get session details
        if token and room_id:
            try:
                # Get session data
                url = f"https://api.videosdk.live/v2/sessions?roomId={room_id}"
                req = urllib.request.Request(url, headers={'Authorization': token})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_resp = json_module.loads(resp.read().decode('utf-8'))
                    data_list = raw_resp.get('data')
                    if isinstance(data_list, list) and len(data_list) > 0:
                        sess_obj = data_list[0]
                        session_id = sess_obj.get('id') or sess_obj.get('_id')
                        
                        # Calculate duration
                        start_s = sess_obj.get('start')
                        end_s = sess_obj.get('end')
                        if start_s and end_s:
                            from datetime import datetime
                            s_dt = datetime.fromisoformat(start_s.replace('Z', '+00:00'))
                            e_dt = datetime.fromisoformat(end_s.replace('Z', '+00:00'))
                            secs = int((e_dt - s_dt).total_seconds())
                            if secs > 0:
                                duration_str = f"{secs // 60}m {secs % 60:02d}s"
                        
                        logging.info(f"Session ID: {session_id}, Duration: {duration_str}")
                        
                        # Check for participants to extract transcript from agent traces
                        participants = sess_obj.get('participants', [])
                        for participant in participants:
                            if participant.get('type') == 'agent':
                                # This is the AI agent - transcript might be in device metadata
                                device_info = participant.get('deviceInfo', {})
                                sdk_metadata = device_info.get('sdkMetadata', {})
                                logging.info(f"Found agent participant with metadata: {sdk_metadata}")
                        
                        # Try to get recording via meeting recordings API
                        if session_id:
                            try:
                                # Use meeting recordings API instead of track recordings
                                rec_url = f"https://api.videosdk.live/v2/recordings?roomId={room_id}"
                                rec_req = urllib.request.Request(rec_url, headers={'Authorization': token})
                                with urllib.request.urlopen(rec_req, timeout=10) as rec_resp:
                                    rec_data = json_module.loads(rec_resp.read().decode('utf-8'))
                                    recordings = rec_data.get('data', [])
                                    logging.info(f"Found {len(recordings)} meeting recording(s) for room {room_id}")
                                    if recordings and len(recordings) > 0:
                                        rec_file = recordings[0].get('file', {})
                                        recording_url = rec_file.get('url') or rec_file.get('fileUrl')
                                        if recording_url:
                                            logging.info(f"✅ Recording URL found, attempting transcription...")
                                            transcript = generate_transcript_from_recording(recording_url, 'Caller', 'Duke')
                                            
                                            # Store recording URL in database for download access
                                            try:
                                                update_url = f"{SUPABASE_URL}/rest/v1/call_logs?id=eq.{call_id}"
                                                update_payload = json_module.dumps({'recording_url': recording_url}).encode('utf-8')
                                                update_req = urllib.request.Request(update_url, data=update_payload, method='PATCH')
                                                update_req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
                                                update_req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
                                                update_req.add_header('Content-Type', 'application/json')
                                                urllib.request.urlopen(update_req, timeout=5)
                                                logging.info(f"Stored recording URL for call {call_id}")
                                            except Exception as store_err:
                                                logging.warning(f"Could not store recording URL: {store_err}")
                                        else:
                                            logging.warning(f"Recording exists but no file URL available yet")
                                    else:
                                        logging.warning(f"No meeting recordings available. Check if recording was started via API.")
                            except Exception as rec_err:
                                logging.warning(f"Could not fetch meeting recording: {rec_err}")
                                
            except Exception as e:
                logging.error(f"Error fetching session data: {e}", exc_info=True)
        
        # If no transcript from recording, create a helpful message
        if not transcript or len(transcript) == 0:
            logging.info(f"No recording available for transcription. Recording may not have been started via API.")
            transcript = [{
                'speaker': 'system',
                'name': 'System',
                'text': f'No recording available. Automatic recording will start on next call when answered.'
            }]
        
        # Update call log with transcript and mark as completed
        entry = {
            'id': call_id,
            'duration': duration_str,
            'transcript': transcript,
            'status': 'completed',
            'sentiment': 'Completed'
        }
        update_call_log_in_supabase(entry)
        
        logging.info(f"✅ Call log updated for {call_id} with {len(transcript)} transcript turns")
        
    except Exception as e:
        logging.error(f"Error in fetch_recording_and_transcribe: {e}", exc_info=True)

def generate_transcript_from_recording(recording_url, caller_name='Caller', agent_name='Agent'):
    """Generate transcript from audio recording URL using Groq Whisper API."""
    try:
        import tempfile
        
        # Download the recording
        logging.info(f"Downloading recording from: {recording_url}")
        audio_data = urllib.request.urlopen(recording_url, timeout=60).read()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            tmp_file.write(audio_data)
            audio_path = tmp_file.name
        
        logging.info(f"Recording downloaded ({len(audio_data)} bytes), transcribing with Groq...")
        
        # Try Groq Whisper API (fastest and you already have it configured)
        groq_api_key = os.getenv('GROQ_API_KEY')
        if groq_api_key and not groq_api_key.startswith('your_'):
            try:
                transcript = transcribe_with_groq_whisper(audio_path, groq_api_key)
                if transcript:
                    os.unlink(audio_path)
                    return parse_transcript_text(transcript, caller_name, agent_name)
            except Exception as e:
                logging.warning(f"Groq Whisper failed: {e}")
        
        # Fallback to OpenAI Whisper API
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and not openai_key.startswith('your_'):
            try:
                transcript = transcribe_with_openai_whisper(audio_path, openai_key)
                if transcript:
                    os.unlink(audio_path)
                    return parse_transcript_text(transcript, caller_name, agent_name)
            except Exception as e:
                logging.warning(f"OpenAI Whisper failed: {e}")
        
        # Fallback to Google Speech-to-Text
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if google_api_key and not google_api_key.startswith('your_'):
            try:
                transcript = transcribe_with_google_speech(audio_path, google_api_key)
                if transcript:
                    os.unlink(audio_path)
                    return parse_transcript_text(transcript, caller_name, agent_name)
            except Exception as e:
                logging.warning(f"Google Speech-to-Text failed: {e}")
        
        # Cleanup
        os.unlink(audio_path)
        logging.warning("No transcription service available (set GROQ_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY)")
        return []
        
    except Exception as e:
        logging.error(f"Error generating transcript from recording: {e}")
        return []

def transcribe_with_groq_whisper(audio_path, api_key):
    """Transcribe audio using Groq Whisper API (fastest)."""
    try:
        from groq import Groq
        
        client = Groq(api_key=api_key)
        
        with open(audio_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), file.read()),
                model="whisper-large-v3-turbo",
                temperature=0,
                response_format="verbose_json",
            )
            
            logging.info(f"✅ Groq Whisper transcription completed")
            return transcription.text
            
    except Exception as e:
        logging.error(f"Groq Whisper transcription failed: {e}")
        return None

def transcribe_with_openai_whisper(audio_path, api_key):
    """Transcribe audio using OpenAI Whisper API."""
    try:
        url = "https://api.openai.com/v1/audio/transcriptions"
        
        # Read audio file
        with open(audio_path, 'rb') as audio_file:
            audio_content = audio_file.read()
        
        # Prepare multipart form data
        boundary = '----WebKitFormBoundary' + str(uuid.uuid4()).replace('-', '')
        
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="audio.mp3"\r\n'
            f'Content-Type: audio/mpeg\r\n\r\n'
        ).encode() + audio_content + (
            f'\r\n--{boundary}\r\n'
            f'Content-Disposition: form-data; name="model"\r\n\r\n'
            f'whisper-1\r\n'
            f'--{boundary}--\r\n'
        ).encode()
        
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Authorization', f'Bearer {api_key}')
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
        
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json_module.loads(resp.read().decode('utf-8'))
            return result.get('text', '')
            
    except Exception as e:
        logging.error(f"OpenAI Whisper transcription failed: {e}")
        return None

def transcribe_with_google_speech(audio_path, api_key):
    """Transcribe audio using Google Speech-to-Text API."""
    try:
        import base64
        
        # Read and encode audio
        with open(audio_path, 'rb') as audio_file:
            audio_content = base64.b64encode(audio_file.read()).decode('utf-8')
        
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
        
        payload = {
            "config": {
                "encoding": "MP3",
                "sampleRateHertz": 16000,
                "languageCode": "en-US",
                "enableAutomaticPunctuation": True
            },
            "audio": {
                "content": audio_content
            }
        }
        
        data = json_module.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json_module.loads(resp.read().decode('utf-8'))
            results = result.get('results', [])
            if results:
                alternatives = results[0].get('alternatives', [])
                if alternatives:
                    return alternatives[0].get('transcript', '')
        
        return None
            
    except Exception as e:
        logging.error(f"Google Speech-to-Text transcription failed: {e}")
        return None

def parse_transcript_text(text, caller_name='Caller', agent_name='Agent'):
    """Parse plain transcript text into structured format with speaker diarization."""
    # Simple heuristic: split by sentences and alternate speakers
    # This is basic - in reality, proper diarization would need timestamps
    
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in '.?!':
            if current.strip():
                sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    
    transcript = []
    for i, sentence in enumerate(sentences):
        # Simple alternating logic - agent speaks first (greeting), then alternate
        is_agent = (i % 2 == 0)
        transcript.append({
            'speaker': 'agent' if is_agent else 'customer',
            'name': agent_name if is_agent else caller_name,
            'text': sentence
        })
    
    return transcript

def send_team_alert(phone_number, name, email, company, resend_key):
    """Send email to team immediately using Resend SDK."""
    import resend
    import os

    if not resend_key:
        logging.warning("RESEND_API_KEY not set. Skipping team email.")
        return

    try:
        resend.api_key = resend_key

        html = f"<p>An AI demo call has just been triggered for <strong>{phone_number}</strong>.</p>"
        if email:
            html += f"<h3>CTA Form Details:</h3><ul><li>Name: {name}</li><li>Email: {email}</li><li>Company: {company}</li></ul>"
        else:
            html += "<p>They used the Instant Call Modal (no CTA form details provided).</p>"
            
        html += "<p>The call is limited to 1 minute. Please check your call transcripts and follow up with the prospect.</p>"

        r = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": [os.getenv("TEAM_EMAIL", "dukeindustries7@gmail.com")],
            "subject": f"AI Demo Call Started - {phone_number}",
            "html": html
        })
        logging.info(f"Team alert email sent: {r}")
    except Exception as e:
        logging.error(f"Failed to send team email via Resend: {e}")

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
                now_utc_str = urllib.parse.quote(now_dt.strftime('%Y-%m-%dT%H:%M:%SZ'))

                due_calls = []
                seen_ids = set()

                # 1. Query Supabase scheduled_calls table
                if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
                    try:
                        query_url = f"{SUPABASE_URL}/rest/v1/scheduled_calls?status=eq.pending&scheduled_at=lte.{now_utc_str}&select=*"
                        req = urllib.request.Request(query_url, headers={
                            "apikey": SUPABASE_SERVICE_ROLE_KEY,
                            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
                        })
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
        elif self.path.startswith('/api/config/'):
            # GET /api/config/{business_id} - get config for specific business
            parts = self.path.split('/')
            if len(parts) >= 4:
                business_id = parts[3]
                config = load_agent_config_from_supabase(business_id=business_id)
                if not config:
                    config = load_agent_config()
                self.send_response(200)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json_module.dumps(config).encode())
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
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
                business_id = new_cfg.get('business_id', None)
                save_agent_config_to_supabase(new_cfg, business_id=business_id)
                save_agent_config_local(new_cfg)
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
                self.wfile.write(json_module.dumps({"error": f"Failed to save configuration: {str(e)}"}).encode())
        elif self.path.startswith('/api/config/'):
            # POST /api/config/{business_id} - save config for specific business
            parts = self.path.split('/')
            if len(parts) >= 4:
                business_id = parts[3]
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                try:
                    new_cfg = json_module.loads(post_data)
                    new_cfg['business_id'] = business_id
                    save_agent_config_to_supabase(new_cfg, business_id=business_id)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json_module.dumps({"status": "success", "config": new_cfg, "business_id": business_id}).encode())
                except Exception as e:
                    logging.error(f"Failed to save config for business {business_id}: {e}")
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json_module.dumps({"error": f"Failed to save configuration: {str(e)}"}).encode())
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
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
                    room_id = wb_payload.get("roomId") or wb_data.get("roomId")
                    
                    # Start recording via API when call is answered
                    if room_id:
                        threading.Thread(target=start_meeting_recording, args=(room_id,)).start()
                    
                    update_call_log_status_in_supabase(
                        call_id=call_id,
                        status='in-progress',
                        duration='--',
                        sentiment=''
                    )
                elif webhook_type == 'call-hangup' or status == 'ended':
                    room_id = wb_payload.get("roomId") or wb_data.get("roomId")
                    
                    # Mark as processing (not completed yet)
                    update_call_log_status_in_supabase(
                        call_id=call_id,
                        status='processing',
                        duration='--',
                        sentiment='Processing',
                        transcript=[{
                            'speaker': 'system',
                            'name': 'System',
                            'text': 'Processing transcription...'
                        }]
                    )
                    
                    # Trigger recording fetch and transcription in background
                    if room_id and call_id:
                        threading.Thread(target=fetch_recording_and_transcribe, args=(call_id, room_id)).start()

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
