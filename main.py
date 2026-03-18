import asyncio
import traceback
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from videosdk.agents import Agent, AgentSession, RealTimePipeline, JobContext, RoomOptions, WorkerJob, Options
from videosdk.plugins.google import GeminiRealtime, GeminiLiveConfig
from dotenv import load_dotenv
import os
import logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

def delayed_team_alert(phone_number, name, email, company, resend_key):
    import time
    import urllib.request
    import json
    import os
    import logging

    logging.info(f"Starting 65s timer for post-demo email alert for {phone_number}")
    time.sleep(65)

    if not resend_key:
        return

    url = "https://api.resend.com/emails"
    
    html = f"<p>A 1-minute AI demo call has just been completed for <strong>{phone_number}</strong>.</p>"
    if email:
        html += f"<h3>CTA Form Details:</h3><ul><li>Name: {name}</li><li>Email: {email}</li><li>Company: {company}</li></ul>"
    else:
        html += "<p>They used the Instant Call Modal (No CTA form details provided).</p>"
        
    html += "<p>Please check your call transcripts and follow up with the prospect.</p>"
    
    payload = json.dumps({
        "from": "Mixup Demo <onboarding@resend.dev>",
        "to": os.getenv("TEAM_EMAIL", "dukeindustries7@gmail.com"),
        "subject": f"AI Demo Finished - {phone_number}",
        "html": html
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {resend_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req) as response:
            logging.info(f"Team target email sent after delay: {response.read()}")
    except Exception as e:
        logging.error(f"Failed to send delayed team email via Resend: {e}")

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
                except urllib.error.URLError as e:
                    logging.error(f"VideoSDK API failed: {e}")
                    
                import threading
                threading.Thread(target=delayed_team_alert, args=(phone_number, name, visitor_email, company, resend_key), daemon=True).start()

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
            instructions="You are an AI assistant for Mixup. You are doing a 1-minute live demo. Your goal is to briefly take their general info (name, company) so our human team can revert back with a full demo. Keep responses extremely short and conversational.",
        )

    async def on_enter(self) -> None:
        await self.session.say("Hi! Thanks for checking out our site. I'm an AI assistant. Should I have my human team reach out to schedule a full demo?")

    async def on_exit(self) -> None:
        # Avoid saying goodbye twice if we already said it in the timeout block
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
    pipeline = RealTimePipeline(model=model)
    session = AgentSession(agent=MyVoiceAgent(), pipeline=pipeline)

    try:
        await context.connect()
        await session.start()
        
        # Restrict demo to exactly 1 minute
        try:
            await asyncio.wait_for(asyncio.Event().wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logging.info("1 minute demo time limit reached.")
            await session.say("That concludes our 1 minute demo! I'll have the team email you with those details. Have a great day!")
            await asyncio.sleep(4) # Let the audio finish playing
            
    finally:
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
