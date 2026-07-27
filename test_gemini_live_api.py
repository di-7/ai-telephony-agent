import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_live_model(model_name: str, api_key: str = None):
    api_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        print("ERROR: Please set a valid GOOGLE_API_KEY in your .env or pass it as an argument.")
        return False

    print(f"\n--- Testing Gemini Live API Model: '{model_name}' ---")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=types.Content(parts=[types.Part.from_text("You are a test assistant. Answer in one short sentence.")]),
        )

        async with client.aio.live.connect(model=model_name, config=config) as session:
            print("Connected successfully to Live API WebSocket session!")
            
            # Send a prompt to test model response
            await session.send(input="Hello! Are you online and working?", end_of_turn=True)
            print("Sent prompt to model. Waiting for response...")

            received_text = []
            async for response in session.receive():
                server_content = response.server_content
                if server_content and server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.text:
                            received_text.append(part.text)
                            print(f"[Model Output]: {part.text}")
                if server_content and server_content.turn_complete:
                    print("Turn complete received!")
                    break

            full_response = "".join(received_text).strip()
            if full_response:
                print(f"SUCCESS: Model '{model_name}' returned response: '{full_response}'")
                return True
            else:
                print(f"WARNING: Model '{model_name}' connected but returned no text.")
                return False

    except Exception as e:
        print(f"FAILED: Model '{model_name}' test error: {e}")
        return False

async def main():
    api_key_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Candidate model identifiers for Gemini Live API
    candidates = [
        "models/gemini-2.0-flash-exp",
        "models/gemini-2.0-flash-realtime-exp",
        "models/gemini-3.1-flash-live-preview",
        "models/gemini-2.0-flash",
    ]

    print("Gemini Live API Model Connection Tester")
    print("=======================================")

    results = {}
    for model in candidates:
        success = await test_live_model(model, api_key=api_key_arg)
        results[model] = success

    print("\n=======================================")
    print("TEST SUMMARY RESULTS:")
    for model, status in results.items():
        res_str = "WORKING ✅" if status else "FAILED / NOT SUPPORTED ❌"
        print(f"  - {model}: {res_str}")

if __name__ == "__main__":
    asyncio.run(main())
