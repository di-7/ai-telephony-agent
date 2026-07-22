import asyncio
import traceback
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from videosdk.agents import Agent, AgentSession, Pipeline, JobContext, RoomOptions, WorkerJob, Options
from videosdk.plugins.google import GeminiRealtime, GeminiLiveConfig
from dotenv import load_dotenv
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
    """Load call logs from JSON file."""
    try:
        if os.path.exists(CALL_LOG_FILE):
            with open(CALL_LOG_FILE, 'r') as f:
                return json_module.load(f)
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

# --- Supabase Configuration ---
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://zuxjdbrgfwpphswgxkiw.supabase.co')
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    'SUPABASE_SERVICE_ROLE_KEY',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp1eGpkYnJnZndwcGhzd2d4a2l3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NDQ4MjU1NCwiZXhwIjoyMTAwMDU4NTU0fQ.JfvwYSf8S8L5TCjYc7i2jdkNKVA-SrZsYGviiA5yt7A'
)

def add_call_log_to_supabase(entry):
    """Post new call log to Supabase via REST API."""
    import urllib.request
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_logs"
        payload = json_module.dumps({
            'caller_phone': entry['phone'],
            'caller_name': entry['name'],
            'caller_email': entry['email'],
            'caller_company': entry['company'],
            'source': entry['source'],
            'duration': entry['duration'],
            'status': entry['status'],
            'sentiment': entry['sentiment'],
            'transcript': entry['transcript']
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('apikey', SUPABASE_SERVICE_ROLE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_SERVICE_ROLE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')

        with urllib.request.urlopen(req) as resp:
            logging.info(f"Call log persisted to Supabase: status {resp.status}")
    except Exception as e:
        logging.error(f"Failed to post call log to Supabase: {e}")

def add_call_log(phone_number, name='', email='', company='', source='instant_call'):
    """Add a new call log entry to local backup and Supabase."""
    logs = load_call_logs()
    entry = {
        'id': str(int(time.time() * 1000)),
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

    # Persist to Supabase asynchronously
    threading.Thread(target=add_call_log_to_supabase, args=(entry,)).start()
    return entry

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

# --- Health check server (keeps Render free tier alive) ---
class HealthHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

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
        elif self.path == '/api/analytics':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            logs = load_call_logs()
            # Compute analytics
            total_calls = len(logs)
            completed = sum(1 for l in logs if l.get('status') == 'completed')
            success_rate = round((completed / total_calls * 100), 1) if total_calls > 0 else 0
            # Count sentiment
            delighted = sum(1 for l in logs if l.get('sentiment') == 'Delighted')
            interested = sum(1 for l in logs if l.get('sentiment') == 'Interested')
            sentiment_score = round(((delighted + interested * 0.7) / total_calls * 100), 1) if total_calls > 0 else 0
            # Call sources
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
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight for browser fetch()
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/make-call':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            import json
            try:
                data = json.loads(post_data)
                phone_number = data.get("to_number", "").strip()
                name = data.get("name", "there")
                visitor_email = data.get("email", "")
                company = data.get("company", "")
                
                # Ensure E.164 format (must start with +)
                if phone_number and not phone_number.startswith('+'):
                    phone_number = '+' + phone_number
                
                logging.info(f"Received request to call: {phone_number} from {name} ({visitor_email})")
                
                import urllib.request
                import urllib.error
                import os

                videosdk_token = os.getenv("VIDEOSDK_AUTH_TOKEN")
                gateway_id = os.getenv("SIP_GATEWAY_ID")
                resend_key = os.getenv("RESEND_API_KEY")

                if not videosdk_token or not gateway_id:
                    logging.error("Missing VIDEOSDK_AUTH_TOKEN or SIP_GATEWAY_ID in .env")
                    self.send_response(500)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Server misconfiguration. Missing API keys or Gateway ID."}')
                    return

                # --- 1. VideoSDK Outbound SIP Call API ---
                call_url = "https://api.videosdk.live/v2/sip/call"
                call_payload = json.dumps({
                    "gatewayId": gateway_id,
                    "sipCallTo": phone_number
                }).encode('utf-8')

                req = urllib.request.Request(call_url, data=call_payload, method="POST")
                req.add_header("Authorization", str(videosdk_token))
                req.add_header("Content-Type", "application/json")

                try:
                    with urllib.request.urlopen(req) as response:
                        api_response = response.read()
                        logging.info(f"VideoSDK call triggered successfully: {api_response}")
                except urllib.error.HTTPError as e:
                    error_body = e.read().decode('utf-8')
                    logging.error(f"VideoSDK API failed with status {e.code}: {error_body}")
                    
                    # Return error to user
                    self.send_response(400)
                    self._send_cors_headers()
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    
                    if e.code == 400 and "unverified" in error_body.lower():
                        error_msg = {"error": "This number is unverified. Please verify it in your VideoSDK dashboard or upgrade your account."}
                    else:
                        error_msg = {"error": f"Call failed: {error_body}"}
                    
                    self.wfile.write(json.dumps(error_msg).encode())
                    return
                except urllib.error.URLError as e:
                    logging.error(f"VideoSDK API failed: {e}")
                    self.send_response(500)
                    self._send_cors_headers()
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Network error occurred"}).encode())
                    return
                    
                # Send team alert email immediately (non-daemon so it completes)
                email_thread = threading.Thread(target=send_team_alert, args=(phone_number, name, visitor_email, company, resend_key))
                email_thread.start()

                # Log the call for dashboard analytics
                add_call_log(phone_number, name, visitor_email, company, source='cta_form' if visitor_email else 'instant_call')

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                
                response_data = {"status": "success", "message": f"Calling {phone_number}..."}
                self.wfile.write(json.dumps(response_data).encode())

            except Exception as e:
                logging.error(f"Failed to parse request: {e}")
                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b"Bad Request")

    def log_message(self, format, *args):
        pass  # Suppress generic request logs

def start_health_server():
    port = int(os.getenv("PORT", 8081))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Health check server running on port {port}")
    server.serve_forever()

# --- Agent definition ---
class MyVoiceAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="You are an AI assistant for Mixup. You are doing a 1-minute live demo. Your goal is to briefly take their general info (name, company) so our human team can revert back with a full demo. Keep responses extremely short and conversational. After about 50 seconds or when you have their info, wrap up by saying: That wraps up our quick demo! Our team will reach out to you soon. Thanks for your time!",
        )

    async def on_enter(self) -> None:
        await self.session.say("Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?")

    async def on_exit(self) -> None:
        pass

async def start_session(context: JobContext):
    # Configure the Gemini model for real-time voice
    model = GeminiRealtime(
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        api_key=os.getenv("GOOGLE_API_KEY"),
        config=GeminiLiveConfig(
            voice="Leda",
            response_modalities=["AUDIO"]
        )
    )
    pipeline = Pipeline(llm=model)
    session = AgentSession(agent=MyVoiceAgent(), pipeline=pipeline)

    try:
        await context.connect()
        await session.start()
        
        # Hard limit: disconnect after 60 seconds
        await asyncio.sleep(60)
        logging.info("1 minute demo time limit reached. Closing session.")
            
    finally:
        # End the meeting for ALL participants (including SIP caller)
        try:
            if context.room:
                await context.room.end()
                logging.info("Room ended for all participants.")
        except Exception as e:
            logging.warning(f"Could not end room: {e}")
        
        await session.close()
        await context.shutdown()

def make_context() -> JobContext:
    room_options = RoomOptions()
    return JobContext(room_options=room_options)

if __name__ == "__main__":
    try:
        # Start health check server in background thread
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()

        # Register the agent with a unique ID
        options = Options(
            agent_id="MyTelephonyAgent",  # CRITICAL: Unique identifier for routing
            register=True,               # REQUIRED: Register with VideoSDK for telephony
            max_processes=1,             # Free tier: limited CPU/RAM, only 1 process
            num_idle_processes=1,        # Keep the process warm and ready
            initialize_timeout=120.0,    # Give Render's free tier plenty of time to initialize
            host="0.0.0.0",
            port=int(os.getenv("AGENT_PORT", 8082)),
            )
        job = WorkerJob(entrypoint=start_session, jobctx=make_context, options=options)
        job.start()
    except Exception as e:
        traceback.print_exc()
