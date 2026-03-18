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

# --- Health check server (keeps Render free tier alive) ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"AI Telephony Agent is running")
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight for browser fetch()
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/make-call':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            import json
            try:
                data = json.loads(post_data)
                phone_number = data.get("to_number", "").strip()
                
                # Ensure E.164 format (must start with +)
                if phone_number and not phone_number.startswith('+'):
                    phone_number = '+' + phone_number
                
                logging.info(f"Received request to call: {phone_number}")
                
                import urllib.request
                import urllib.error
                import json
                import os

                videosdk_token = os.getenv("VIDEOSDK_AUTH_TOKEN")
                gateway_id = os.getenv("SIP_GATEWAY_ID")

                if not videosdk_token or not gateway_id:
                    logging.error("Missing VIDEOSDK_AUTH_TOKEN or SIP_GATEWAY_ID in .env")
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Server misconfiguration. Missing API keys or Gateway ID."}')
                    return

                # --- VideoSDK Outbound SIP Call API ---
                url = "https://api.videosdk.live/v2/sip/call"
                payload = json.dumps({
                    "gatewayId": gateway_id,
                    "sipCallTo": phone_number
                    # If you need a specific room, you can pass "destinationRoomId" as well.
                }).encode('utf-8')

                req = urllib.request.Request(url, data=payload, method="POST")
                req.add_header("Authorization", str(videosdk_token))
                req.add_header("Content-Type", "application/json")

                try:
                    with urllib.request.urlopen(req) as response:
                        api_response = response.read()
                        logging.info(f"VideoSDK call triggered successfully: {api_response}")
                except urllib.error.URLError as e:
                    logging.error(f"VideoSDK API failed: {e}")
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Failed to trigger outbound call via VideoSDK."}')
                    return
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                response = {"status": "success", "message": f"Calling {phone_number}..."}
                self.wfile.write(json.dumps(response).encode())

            except Exception as e:
                logging.error(f"Failed to parse request: {e}")
                self.send_response(400)
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
            instructions="You are an expert AI sales representative for Mixup, a company that provides AI-powered agentic calls for businesses. Keep your responses concise, friendly, and under 2 sentences. Your goal is to show off how natural an AI voice can sound and answer basic questions about Mixup's outbound calling and inbound reception services.",
        )

    async def on_enter(self) -> None:
        await self.session.say("Hello! I'm your real-time assistant. How can I help you today?")

    async def on_exit(self) -> None:
        await self.session.say("Goodbye! It was great talking with you!")

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
        await asyncio.Event().wait()
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
