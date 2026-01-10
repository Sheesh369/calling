# import os
# import uuid
# import base64
# import asyncio
# from typing import Dict
# from datetime import datetime
# from pathlib import Path

# from fastapi import FastAPI, WebSocket, Request, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse, Response, FileResponse
# from loguru import logger
# from dotenv import load_dotenv
# import httpx

# # Import bot function and services
# from bot import bot
# from whatsapp_service import send_whatsapp_message, format_payment_reminder_message
# from email_service import send_email, format_payment_reminder_email

# load_dotenv(override=True)

# app = FastAPI()

# # CORS middleware for Streamlit frontend
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# @app.on_event("startup")
# async def startup_event():
#     """Initialize queue lock and start background tasks"""
#     global queue_lock
#     queue_lock = asyncio.Lock()
#     # Start the queue processor
#     asyncio.create_task(process_call_queue())
#     logger.info("Call queue processor started")

# # In-memory storage for call data
# call_data_store: Dict[str, dict] = {}

# # Call queue for sequential processing
# call_queue = []
# queue_lock = None  # Will be initialized in startup
# is_processing_queue = False

# # Plivo credentials
# PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
# PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
# PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

# # Sarvam AI credentials
# SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# # Server configuration
# SERVER_URL = os.getenv("SERVER_URL", "https://seagull-winning-personally.ngrok-free.app")

# # Audio file paths
# GREETING_AUDIO_PATH = os.getenv("GREETING_AUDIO_PATH", "output.wav")
# GREETINGS_DIR = Path("greetings")
# GREETINGS_DIR.mkdir(exist_ok=True)  # Create greetings directory if it doesn't exist


# @app.get("/health")
# async def health_check():
#     """Health check endpoint"""
#     return {
#         "status": "healthy",
#         "timestamp": datetime.now().isoformat(),
#         "plivo_configured": bool(PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN),
#         "whatsapp_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN")),
#         "email_configured": bool(os.getenv("SMTP_USERNAME")),
#         "audio_file_exists": os.path.exists(GREETING_AUDIO_PATH)
#     }


# @app.get("/audio/greeting.wav")
# async def serve_greeting_audio():
#     """Serve the greeting audio file."""
#     if not os.path.exists(GREETING_AUDIO_PATH):
#         logger.error(f"Audio file not found at: {GREETING_AUDIO_PATH}")
#         raise HTTPException(status_code=404, detail="Audio file not found")
    
#     logger.info(f"Serving audio file from: {GREETING_AUDIO_PATH}")
#     return FileResponse(GREETING_AUDIO_PATH, media_type="audio/wav")


# @app.get("/audio/greeting/{call_uuid}.wav")
# async def serve_dynamic_greeting(call_uuid: str):
#     """Serve dynamic greeting audio for a specific call"""
#     file_path = GREETINGS_DIR / f"{call_uuid}.wav"
    
#     if not file_path.exists():
#         logger.warning(f"Dynamic greeting not found for {call_uuid}, using default")
#         # Fallback to default greeting
#         if os.path.exists(GREETING_AUDIO_PATH):
#             return FileResponse(GREETING_AUDIO_PATH, media_type="audio/wav")
#         raise HTTPException(status_code=404, detail="Audio file not found")
    
#     logger.info(f"Serving dynamic greeting for call {call_uuid}")
#     return FileResponse(file_path, media_type="audio/wav")


# def number_to_words(amount_str: str) -> str:
#     """Convert numeric amount to words for TTS"""
#     try:
#         # Remove currency symbols and commas
#         amount_str = str(amount_str).replace("₹", "").replace("rupees", "").replace(",", "").replace("+", "").strip()
#         num = int(float(amount_str))
#     except (ValueError, TypeError):
#         return str(amount_str)
    
#     if num == 0:
#         return "zero"
    
#     # Handle negative numbers
#     if num < 0:
#         return "minus " + number_to_words(abs(num))
    
#     # Indian numbering system
#     ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
#     teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", 
#              "sixteen", "seventeen", "eighteen", "nineteen"]
#     tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    
#     def convert_below_thousand(n):
#         if n == 0:
#             return ""
#         elif n < 10:
#             return ones[n]
#         elif n < 20:
#             return teens[n - 10]
#         elif n < 100:
#             return tens[n // 10] + (" " + ones[n % 10] if n % 10 != 0 else "")
#         else:
#             return ones[n // 100] + " hundred" + (" " + convert_below_thousand(n % 100) if n % 100 != 0 else "")
    
#     # Indian numbering: crore, lakh, thousand, hundred
#     if num >= 10000000:  # Crore
#         crore = num // 10000000
#         remainder = num % 10000000
#         result = convert_below_thousand(crore) + " crore"
#         if remainder > 0:
#             result += " " + number_to_words(remainder)
#         return result
#     elif num >= 100000:  # Lakh
#         lakh = num // 100000
#         remainder = num % 100000
#         result = convert_below_thousand(lakh) + " lakh"
#         if remainder > 0:
#             result += " " + number_to_words(remainder)
#         return result
#     elif num >= 1000:  # Thousand
#         thousand = num // 1000
#         remainder = num % 1000
#         result = convert_below_thousand(thousand) + " thousand"
#         if remainder > 0:
#             result += " " + convert_below_thousand(remainder)
#         return result
#     else:
#         return convert_below_thousand(num)


# async def generate_greeting_audio(text: str, call_uuid: str) -> str:
#     """Generate TTS audio using Sarvam AI and save to file"""
#     try:
#         logger.info(f"Generating greeting for call {call_uuid}: {text}")
        
#         url = "https://api.sarvam.ai/text-to-speech"
        
#         payload = {
#             "inputs": [text],
#             "target_language_code": "en-IN",
#             "speaker": "anushka",  # Female voice - matches the bot's voice
#             "pitch": 0,
#             "pace": 1.0,
#             "loudness": 1.5,
#             "speech_sample_rate": 8000,
#             "enable_preprocessing": True,
#             "model": "bulbul:v2"
#         }
        
#         headers = {
#             "Content-Type": "application/json", 
#             "API-Subscription-Key": SARVAM_API_KEY
#         }
        
#         async with httpx.AsyncClient() as client:
#             response = await client.post(url, json=payload, headers=headers, timeout=30.0)
#             response.raise_for_status()
#             response_data = response.json()
        
#         # Audio is returned as base64 encoded string in the 'audios' list
#         audio_base64 = response_data["audios"][0]
#         audio_data = base64.b64decode(audio_base64)
            
#         file_path = GREETINGS_DIR / f"{call_uuid}.wav"
        
#         # Write to file
#         with open(file_path, "wb") as f:
#             f.write(audio_data)
        
#         logger.info(f"Successfully generated greeting audio for call {call_uuid}")
#         return str(file_path)
        
#     except httpx.HTTPStatusError as e:
#         logger.error(f"Sarvam AI API error for call {call_uuid}: {e.response.status_code} - {e.response.text}")
#         return None
#     except Exception as e:
#         logger.error(f"Error generating greeting audio for call {call_uuid}: {e}")
#         return None


# async def process_single_call(call_data: dict) -> dict:
#     """Process a single call from the queue"""
#     phone_number = call_data["phone_number"]
#     custom_data = call_data["custom_data"]
#     call_uuid = call_data["call_uuid"]
    
#     try:
#         logger.info(f"Processing call {call_uuid} to {phone_number}")
        
#         # Generate Dynamic Greeting
#         customer_name = custom_data.get("customer_name", "")
#         invoice_number = custom_data.get("invoice_number", "unknown")
#         outstanding_balance = custom_data.get("outstanding_balance", "")
#         invoice_date = custom_data.get("invoice_date", "")
        
#         # Build personalized greeting text
#         if invoice_number.lower() == "unknown":
#             greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding your outstanding invoice."
#         else:
#             spoken_invoice = invoice_number.replace("-", "").replace("/", "")
#             greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding an outstanding invoice {spoken_invoice}"
            
#             if outstanding_balance:
#                 balance_in_words = number_to_words(outstanding_balance)
#                 greeting_text += f" for rupees {balance_in_words}"
            
#             if invoice_date:
#                 greeting_text += f", which was dated on {invoice_date}"
            
#             greeting_text += ". I wanted to check on the status of this payment."
        
#         logger.info(f"Greeting text: {greeting_text}")
        
#         # Store greeting text in call_data_store for bot to access
#         call_data_store[call_uuid]["greeting_text"] = greeting_text
        
#         # Generate the audio file
#         generated_path = await generate_greeting_audio(greeting_text, call_uuid)
        
#         if not generated_path:
#             logger.warning(f"Greeting generation failed for {call_uuid}, will use default")
        
#         # Make Plivo API call
#         plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
#         answer_url = f"{SERVER_URL}/plivo_answer/{call_uuid}"
        
#         plivo_payload = {
#             "from": PLIVO_PHONE_NUMBER,
#             "to": phone_number,
#             "answer_url": answer_url,
#             "answer_method": "POST"
#         }
        
#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 plivo_url,
#                 json=plivo_payload,
#                 auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
#                 timeout=30.0
#             )
        
#         if response.status_code in [200, 201, 202]:
#             plivo_response = response.json()
#             plivo_call_uuid = plivo_response.get("request_uuid") or plivo_response.get("message_uuid")
            
#             call_data_store[call_uuid]["plivo_call_uuid"] = plivo_call_uuid
#             call_data_store[call_uuid]["status"] = "calling"
            
#             logger.info(f"Call initiated successfully: {call_uuid} (Plivo: {plivo_call_uuid})")
            
#             return {
#                 "success": True,
#                 "call_uuid": call_uuid,
#                 "plivo_call_uuid": plivo_call_uuid,
#                 "phone_number": phone_number,
#                 "status": "calling"
#             }
#         else:
#             logger.error(f"Plivo API error: {response.status_code} - {response.text}")
#             call_data_store[call_uuid]["status"] = "failed"
#             return {
#                 "success": False,
#                 "call_uuid": call_uuid,
#                 "error": f"Plivo API error: {response.text}"
#             }
    
#     except Exception as e:
#         logger.error(f"Error processing call {call_uuid}: {e}")
#         if call_uuid in call_data_store:
#             call_data_store[call_uuid]["status"] = "failed"
#         return {
#             "success": False,
#             "call_uuid": call_uuid,
#             "error": str(e)
#         }


# async def process_call_queue():
#     """Background task to process calls from queue sequentially"""
#     global is_processing_queue
    
#     logger.info("Call queue processor started")
    
#     while True:
#         try:
#             async with queue_lock:
#                 if not call_queue:
#                     is_processing_queue = False
#                     await asyncio.sleep(1)
#                     continue
                
#                 is_processing_queue = True
#                 call_data = call_queue.pop(0)
            
#             # Process the call
#             result = await process_single_call(call_data)
#             logger.info(f"Call processed: {result}")
            
#             # Wait for call to complete by monitoring call_data_store
#             call_uuid = call_data["call_uuid"]
#             max_wait_time = 600  # 10 minutes max
#             elapsed_time = 0
            
#             while elapsed_time < max_wait_time:
#                 await asyncio.sleep(2)  # Check every 2 seconds
#                 elapsed_time += 2
                
#                 if call_uuid in call_data_store:
#                     status = call_data_store[call_uuid].get("status")
#                     if status in ["completed", "failed"]:
#                         logger.info(f"Call {call_uuid} finished with status: {status}")
#                         break
            
#             # Small delay before next call
#             await asyncio.sleep(1)
            
#         except Exception as e:
#             logger.error(f"Error in process_call_queue: {e}")
#             await asyncio.sleep(1)
#     """Generate TTS audio using Sarvam AI and save to file"""
#     try:
#         logger.info(f"Generating greeting for call {call_uuid}: {text}")
        
#         url = "https://api.sarvam.ai/text-to-speech"
        
#         payload = {
#             "inputs": [text],
#             "target_language_code": "en-IN",
#             "speaker": "anushka",  # Female voice - matches the bot's voice
#             "pitch": 0,
#             "pace": 1.0,
#             "loudness": 1.5,
#             "speech_sample_rate": 8000,
#             "enable_preprocessing": True,
#             "model": "bulbul:v2"
#         }
        
#         headers = {
#             "Content-Type": "application/json", 
#             "API-Subscription-Key": SARVAM_API_KEY
#         }
        
#         async with httpx.AsyncClient() as client:
#             response = await client.post(url, json=payload, headers=headers, timeout=30.0)
#             response.raise_for_status()
#             response_data = response.json()
        
#         # Audio is returned as base64 encoded string in the 'audios' list
#         audio_base64 = response_data["audios"][0]
#         audio_data = base64.b64decode(audio_base64)
            
#         file_path = GREETINGS_DIR / f"{call_uuid}.wav"
        
#         # Write to file
#         with open(file_path, "wb") as f:
#             f.write(audio_data)
        
#         logger.info(f"Successfully generated greeting audio for call {call_uuid}")
#         return str(file_path)
        
#     except httpx.HTTPStatusError as e:
#         logger.error(f"Sarvam AI API error for call {call_uuid}: {e.response.status_code} - {e.response.text}")
#         return None
#     except Exception as e:
#         logger.error(f"Error generating greeting audio for call {call_uuid}: {e}")
#         return None



# VERIFY_TOKEN = "aaqil123"  # Set this to the same value you provide in Meta dashboard


# @app.get("/webhook")
# async def verify_webhook(request: Request):
#     params = dict(request.query_params)
#     mode = params.get("hub.mode")
#     token = params.get("hub.verify_token")
#     challenge = params.get("hub.challenge")

#     if mode == "subscribe" and token == VERIFY_TOKEN:
#         return PlainTextResponse(content=challenge, status_code=200)
#     else:
#         raise HTTPException(status_code=403, detail="Verification failed")


# @app.post("/webhook")
# async def receive_message(request: Request):
#     body = await request.json()
#     print("Received message:", body)  # Log the incoming payload
#     return JSONResponse(content={"status": "received"}, status_code=200)


# @app.post("/start")
# async def start_call(request: Request):
#     """
#     Initiate a new call with custom data
#     Expected JSON body:
#     {
#         "phone_number": "+919876543210",
#         "body": {
#             "customer_name": "John Doe",
#             "invoice_number": "INV-001",
#             "invoice_date": "2024-01-01",
#             "total_amount": "rupees 5000",
#             "outstanding_balance": "rupees 5000"
#         }
#     }
#     """
#     try:
#         data = await request.json()
#         phone_number = data.get("phone_number")
#         custom_data = data.get("body", {})
        
#         if not phone_number:
#             raise HTTPException(status_code=400, detail="phone_number is required")
        
#         # Generate unique call UUID
#         call_uuid = str(uuid.uuid4())
        
#         # Store call data
#         call_data_store[call_uuid] = {
#             "phone_number": phone_number,
#             "custom_data": custom_data,
#             "status": "initiated",
#             "created_at": datetime.now().isoformat(),
#             "plivo_call_uuid": None
#         }
        
#         logger.info(f"Initiating call {call_uuid} to {phone_number}")
#         logger.info(f"Custom data: {custom_data}")
        
#         # Generate Dynamic Greeting BEFORE initiating the call
#         customer_name = custom_data.get("customer_name", "")
#         invoice_number = custom_data.get("invoice_number", "unknown")
#         outstanding_balance = custom_data.get("outstanding_balance", "")
#         invoice_date = custom_data.get("invoice_date", "")
        
#         # Build personalized greeting text
#         if invoice_number.lower() == "unknown":
#             greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding your outstanding invoice."
#         else:
#             # Remove special characters for TTS
#             spoken_invoice = invoice_number.replace("-", "").replace("/", "")
            
#             # Build greeting with available information
#             greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding an outstanding invoice {spoken_invoice}"
            
#             if outstanding_balance:
#                 # Convert balance to words for TTS
#                 balance_in_words = number_to_words(outstanding_balance)
#                 greeting_text += f" for rupees {balance_in_words}"
            
#             if invoice_date:
#                 greeting_text += f", which was dated on {invoice_date}"
            
#             greeting_text += ". I wanted to check on the status of this payment."
        
#         logger.info(f"Greeting text: {greeting_text}")
        
#         # Generate the audio file
#         generated_path = await generate_greeting_audio(greeting_text, call_uuid)
        
#         if not generated_path:
#             logger.warning(f"Greeting generation failed for {call_uuid}, will use default")
        
#         # Make Plivo API call to initiate the call
#         plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
        
#         # Construct the answer URL with call UUID
#         answer_url = f"{SERVER_URL}/plivo_answer/{call_uuid}"
        
#         plivo_payload = {
#             "from": PLIVO_PHONE_NUMBER,
#             "to": phone_number,
#             "answer_url": answer_url,
#             "answer_method": "POST"
#         }
        
#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 plivo_url,
#                 json=plivo_payload,
#                 auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
#                 timeout=30.0
#             )
        
#         if response.status_code in [200, 201, 202]:
#             plivo_response = response.json()
#             plivo_call_uuid = plivo_response.get("request_uuid") or plivo_response.get("message_uuid")
            
#             call_data_store[call_uuid]["plivo_call_uuid"] = plivo_call_uuid
#             call_data_store[call_uuid]["status"] = "calling"
            
#             logger.info(f"Call initiated successfully: {call_uuid} (Plivo: {plivo_call_uuid})")
            
#             return JSONResponse({
#                 "success": True,
#                 "call_uuid": call_uuid,
#                 "plivo_call_uuid": plivo_call_uuid,
#                 "phone_number": phone_number,
#                 "status": "calling"
#             })
#         else:
#             logger.error(f"Plivo API error: {response.status_code} - {response.text}")
#             call_data_store[call_uuid]["status"] = "failed"
#             raise HTTPException(
#                 status_code=response.status_code,
#                 detail=f"Failed to initiate call: {response.text}"
#             )
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error starting call: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.post("/start_batch")
# async def start_batch_calls(request: Request):
#     """
#     Initiate a batch of calls sequentially
#     Expected JSON body:
#     {
#         "calls": [
#             {
#                 "phone_number": "+919876543210",
#                 "body": {
#                     "customer_name": "John Doe",
#                     "invoice_number": "INV-001",
#                     ...
#                 }
#             },
#             ...
#         ]
#     }
#     """
#     try:
#         data = await request.json()
#         calls = data.get("calls", [])
        
#         if not calls:
#             raise HTTPException(status_code=400, detail="calls array is required")
        
#         logger.info(f"Received batch request for {len(calls)} calls")
        
#         # Add all calls to queue
#         call_uuids = []
#         async with queue_lock:
#             for call_data in calls:
#                 phone_number = call_data.get("phone_number")
#                 custom_data = call_data.get("body", {})
                
#                 if not phone_number:
#                     logger.warning("Skipping call with missing phone_number")
#                     continue
                
#                 # Generate unique call UUID
#                 call_uuid = str(uuid.uuid4())
                
#                 # Store call data
#                 call_data_store[call_uuid] = {
#                     "phone_number": phone_number,
#                     "custom_data": custom_data,
#                     "status": "queued",
#                     "created_at": datetime.now().isoformat(),
#                     "plivo_call_uuid": None
#                 }
                
#                 # Add to queue
#                 call_queue.append({
#                     "call_uuid": call_uuid,
#                     "phone_number": phone_number,
#                     "custom_data": custom_data
#                 })
                
#                 call_uuids.append(call_uuid)
        
#         logger.info(f"Added {len(call_uuids)} calls to queue")
        
#         return JSONResponse({
#             "success": True,
#             "message": f"Added {len(call_uuids)} calls to queue",
#             "call_uuids": call_uuids,
#             "queue_length": len(call_queue)
#         })
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error starting batch calls: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.post("/plivo_answer/{call_uuid}")
# async def plivo_answer(call_uuid: str, request: Request):
#     """
#     Plivo answer URL - returns XML to play audio greeting and connect call to WebSocket
#     """
#     try:
#         logger.info(f"Plivo answer callback for call {call_uuid}")
        
#         if call_uuid not in call_data_store:
#             logger.error(f"Call UUID {call_uuid} not found")
#             return JSONResponse(
#                 content={"error": "Call not found"},
#                 status_code=404
#             )
        
#         # Update call status
#         call_data_store[call_uuid]["status"] = "connected"
        
#         # Track greeting start time and set status to greeting_playing
#         call_data_store[call_uuid]["greeting_start_time"] = datetime.now().isoformat()
#         call_data_store[call_uuid]["status"] = "greeting_playing"
        
#         # Get custom data for this call
#         custom_data = call_data_store[call_uuid].get("custom_data", {})
        
#         # Construct WebSocket URL
#         ws_url = f"{SERVER_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/ws/{call_uuid}"
        
#         # Construct audio URL - use dynamic greeting if available
#         dynamic_greeting_path = GREETINGS_DIR / f"{call_uuid}.wav"
#         if dynamic_greeting_path.exists():
#             audio_url = f"{SERVER_URL}/audio/greeting/{call_uuid}.wav"
#             logger.info(f"Using dynamic greeting for call {call_uuid}")
#         else:
#             audio_url = f"{SERVER_URL}/audio/greeting.wav"
#             logger.warning(f"Dynamic greeting not found for {call_uuid}, using default")
        
#         logger.info(f"Audio URL: {audio_url}")
#         logger.info(f"WebSocket URL: {ws_url}")
        
#         # Return Plivo XML to play audio greeting and connect to WebSocket
#         xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
# <Response>
#     <Play>{audio_url}</Play>
#     <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
#         {ws_url}
#     </Stream>
# </Response>"""
        
#         logger.info(f"Returning Plivo XML for call {call_uuid}")
        
#         return Response(
#             content=xml_response,
#             media_type="application/xml"
#         )
    
#     except Exception as e:
#         logger.error(f"Error in plivo_answer: {e}")
#         return JSONResponse(
#             content={"error": str(e)},
#             status_code=500
#         )


# @app.websocket("/ws/{call_uuid}")
# async def websocket_endpoint(websocket: WebSocket, call_uuid: str):
#     """
#     WebSocket endpoint for Pipecat bot
#     """
#     await websocket.accept()
#     logger.info(f"WebSocket connection established for call {call_uuid}")
    
#     # Store custom data in websocket state for bot to access
#     if call_uuid in call_data_store:
#         websocket.state.custom_data = call_data_store[call_uuid].get("custom_data", {})
#         # Add greeting_text to custom_data so bot knows what was said
#         websocket.state.custom_data["greeting_text"] = call_data_store[call_uuid].get("greeting_text", "")
#         websocket.state.call_uuid = call_uuid
#         call_data_store[call_uuid]["status"] = "in_progress"
#     else:
#         logger.warning(f"Call UUID {call_uuid} not found in store")
#         websocket.state.custom_data = {}
#         websocket.state.call_uuid = call_uuid
    
#     try:
#         # Import runner arguments - use WebSocketRunnerArguments for WebSocket connections
#         from pipecat.runner.types import WebSocketRunnerArguments
        
#         # Create runner arguments
#         runner_args = WebSocketRunnerArguments(
#             websocket=websocket
#         )
#         runner_args.handle_sigint = False
        
#         # Run the bot
#         await bot(runner_args)
        
#     except Exception as e:
#         logger.error(f"Error in WebSocket for call {call_uuid}: {e}")
#     finally:
#         logger.info(f"WebSocket closed for call {call_uuid}")
#         if call_uuid in call_data_store:
#             call_data_store[call_uuid]["status"] = "completed"
#             call_data_store[call_uuid]["ended_at"] = datetime.now().isoformat()
        
#         # Clean up dynamic greeting file
#         dynamic_greeting_path = GREETINGS_DIR / f"{call_uuid}.wav"
#         if dynamic_greeting_path.exists():
#             try:
#                 dynamic_greeting_path.unlink()
#                 logger.info(f"Deleted dynamic greeting for call {call_uuid}")
#             except Exception as e:
#                 logger.error(f"Error deleting greeting file for {call_uuid}: {e}")


# @app.get("/calls")
# async def list_calls():
#     """
#     List all calls with their current status
#     """
#     return {
#         "calls": [
#             {
#                 "call_uuid": call_uuid,
#                 "phone_number": data["phone_number"],
#                 "status": data["status"],
#                 "created_at": data["created_at"],
#                 "ended_at": data.get("ended_at"),
#                 "customer_name": data.get("custom_data", {}).get("customer_name", "Unknown"),
#                 "invoice_number": data.get("custom_data", {}).get("invoice_number", "N/A")
#             }
#             for call_uuid, data in call_data_store.items()
#         ]
#     }


# @app.get("/transcripts")
# async def list_transcripts():
#     """
#     List all transcript files with metadata
#     Returns a list of transcripts with parsed metadata
#     """
#     import re
#     from datetime import datetime as dt
    
#     try:
#         transcripts_dir = Path("transcripts")
        
#         # Check if directory exists
#         if not transcripts_dir.exists():
#             return {"transcripts": []}
        
#         transcripts = []
        
#         # Iterate through all .txt files in transcripts directory
#         for transcript_file in transcripts_dir.glob("*.txt"):
#             try:
#                 # Parse filename: invoicenumber_calluuid.txt
#                 filename = transcript_file.name
#                 parts = filename.replace(".txt", "").split("_", 1)
                
#                 invoice_number = parts[0] if len(parts) > 0 else "unknown"
#                 call_uuid = parts[1] if len(parts) > 1 else "unknown"
                
#                 # Read file to extract metadata
#                 with open(transcript_file, "r", encoding="utf-8") as f:
#                     content = f.read()
                
#                 # Extract metadata from file
#                 metadata = {
#                     "filename": filename,
#                     "invoice_number": invoice_number,
#                     "call_uuid": call_uuid,
#                     "file_size": transcript_file.stat().st_size,
#                     "created_at": datetime.fromtimestamp(transcript_file.stat().st_ctime).isoformat(),
#                     "modified_at": datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat(),
#                 }
                
#                 # Try to extract customer name from content
#                 if "Customer Name:" in content:
#                     start = content.index("Customer Name:") + len("Customer Name:")
#                     end = content.index("\n", start)
#                     metadata["customer_name"] = content[start:end].strip()
#                 else:
#                     metadata["customer_name"] = "N/A"
                
#                 # Check if summary exists
#                 metadata["has_summary"] = "CALL SUMMARY (Generated by AI)" in content
                
#                 # Extract status
#                 if "Status: Completed" in content:
#                     metadata["status"] = "completed"
#                 else:
#                     metadata["status"] = "in_progress"
                
#                 # Extract call outcome from summary
#                 metadata["call_outcome"] = "UNKNOWN"
#                 metadata["cut_off_date"] = None
#                 if "**CALL OUTCOME:**" in content:
#                     try:
#                         start = content.index("**CALL OUTCOME:**") + len("**CALL OUTCOME:**")
#                         end = content.index("\n", start)
#                         outcome = content[start:end].strip()
#                         metadata["call_outcome"] = outcome
                        
#                         # Extract cut-off date if outcome is CUT_OFF_DATE_PROVIDED
#                         if outcome == "CUT_OFF_DATE_PROVIDED":
#                             # Look for date patterns in the summary
                            
#                             # Get the summary section
#                             if "CALL SUMMARY" in content:
#                                 summary_start = content.index("CALL SUMMARY")
#                                 summary_section = content[summary_start:]
                                
#                                 # Look for common date patterns
#                                 # Pattern 1: "January 6, 2026" or "Jan 6, 2026"
#                                 date_pattern1 = r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})'
#                                 # Pattern 2: "2026-01-06" or "01/06/2026"
#                                 date_pattern2 = r'(\d{4})-(\d{2})-(\d{2})'
#                                 date_pattern3 = r'(\d{2})/(\d{2})/(\d{4})'
                                
#                                 match = re.search(date_pattern1, summary_section, re.IGNORECASE)
#                                 if match:
#                                     try:
#                                         date_str = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
#                                         parsed_date = dt.strptime(date_str, "%B %d, %Y")
#                                         metadata["cut_off_date"] = parsed_date.strftime("%Y-%m-%d")
#                                     except:
#                                         try:
#                                             date_str = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
#                                             parsed_date = dt.strptime(date_str, "%b %d, %Y")
#                                             metadata["cut_off_date"] = parsed_date.strftime("%Y-%m-%d")
#                                         except:
#                                             pass
                                
#                                 if not metadata["cut_off_date"]:
#                                     match = re.search(date_pattern2, summary_section)
#                                     if match:
#                                         metadata["cut_off_date"] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
#                     except:
#                         pass
                
#                 transcripts.append(metadata)
                
#             except Exception as e:
#                 logger.error(f"Error parsing transcript file {transcript_file}: {e}")
#                 continue
        
#         # Sort by created_at descending (most recent first)
#         transcripts.sort(key=lambda x: x["created_at"], reverse=True)
        
#         return {"transcripts": transcripts}
    
#     except Exception as e:
#         logger.error(f"Error listing transcripts: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/transcripts/{filename}")
# async def get_transcript(filename: str):
#     """
#     Get the full content of a specific transcript file
#     Returns the transcript with conversation and summary
#     """
#     try:
#         transcripts_dir = Path("transcripts")
#         transcript_file = transcripts_dir / filename
        
#         # Security check: ensure file is in transcripts directory
#         if not transcript_file.resolve().is_relative_to(transcripts_dir.resolve()):
#             raise HTTPException(status_code=400, detail="Invalid filename")
        
#         if not transcript_file.exists():
#             raise HTTPException(status_code=404, detail="Transcript not found")
        
#         # Read file content
#         with open(transcript_file, "r", encoding="utf-8") as f:
#             content = f.read()
        
#         # Parse the content into sections
#         sections = {
#             "metadata": "",
#             "conversation": "",
#             "summary": ""
#         }
        
#         # Split content into sections
#         if "CONVERSATION:" in content:
#             parts = content.split("CONVERSATION:")
#             sections["metadata"] = parts[0].strip()
            
#             if len(parts) > 1:
#                 conversation_part = parts[1]
                
#                 # Look for summary section - handle both with and without equals signs
#                 summary_markers = [
#                     "=== CALL SUMMARY (Generated by AI) ===",
#                     "CALL SUMMARY (Generated by AI)"
#                 ]
                
#                 summary_found = False
#                 for marker in summary_markers:
#                     if marker in conversation_part:
#                         conv_parts = conversation_part.split(marker)
#                         sections["conversation"] = conv_parts[0].strip()
#                         if len(conv_parts) > 1:
#                             # Remove leading/trailing equals signs and whitespace
#                             summary_content = conv_parts[1].strip()
#                             # Remove any leading/trailing equals sign lines
#                             summary_lines = summary_content.split('\n')
#                             summary_lines = [line for line in summary_lines if line.strip() and not all(c == '=' for c in line.strip())]
#                             sections["summary"] = '\n'.join(summary_lines).strip()
#                         else:
#                             sections["summary"] = ""
#                         summary_found = True
#                         break
                
#                 if not summary_found:
#                     sections["conversation"] = conversation_part.strip()
        
#         return {
#             "filename": filename,
#             "full_content": content,
#             "sections": sections,
#             "file_size": transcript_file.stat().st_size,
#             "created_at": datetime.fromtimestamp(transcript_file.stat().st_ctime).isoformat(),
#             "modified_at": datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat(),
#         }
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error reading transcript {filename}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.post("/whatsapp/send")
# async def send_whatsapp(request: Request):
#     """
#     Send WhatsApp message
#     Expected JSON body:
#     {
#         "phone_number": "919876543210",
#         "body": {
#             "customer_name": "John Doe",
#             "invoice_number": "INV-001",
#             "invoice_date": "2024-01-01",
#             "total_amount": "rupees 5000",
#             "outstanding_balance": "rupees 5000"
#         }
#     }
#     """
#     try:
#         data = await request.json()
#         phone_number = data.get("phone_number")
#         custom_data = data.get("body", {})
        
#         if not phone_number:
#             raise HTTPException(status_code=400, detail="phone_number is required")
        
#         # Remove + from phone number if present (WhatsApp API expects without +)
#         phone_number = phone_number.replace("+", "")
        
#         # Format the payment reminder message
#         message_text = format_payment_reminder_message(custom_data)
        
#         # Send WhatsApp message
#         result = send_whatsapp_message(phone_number, message_text)
        
#         if result.get("success"):
#             logger.info(f"WhatsApp message sent to {phone_number}")
#             return JSONResponse({
#                 "success": True,
#                 "message_id": result.get("message_id"),
#                 "phone_number": phone_number,
#                 "customer_name": custom_data.get("customer_name"),
#                 "status": "sent"
#             })
#         else:
#             logger.error(f"Failed to send WhatsApp: {result.get('error')}")
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to send WhatsApp message: {result.get('error')}"
#             )
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error sending WhatsApp: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.post("/email/send")
# async def send_email_reminder(request: Request):
#     """
#     Send Email reminder
#     Expected JSON body:
#     {
#         "email": "customer@example.com",
#         "body": {
#             "customer_name": "John Doe",
#             "invoice_number": "INV-001",
#             "invoice_date": "2024-01-01",
#             "total_amount": "rupees 5000",
#             "outstanding_balance": "rupees 5000"
#         }
#     }
#     """
#     try:
#         data = await request.json()
#         email = data.get("email")
#         custom_data = data.get("body", {})
        
#         if not email:
#             raise HTTPException(status_code=400, detail="email is required")
        
#         # Format the payment reminder email
#         subject, html_body, text_body = format_payment_reminder_email(custom_data)
        
#         # Send email
#         result = send_email(email, subject, html_body, text_body)
        
#         if result.get("success"):
#             logger.info(f"Email sent to {email}")
#             return JSONResponse({
#                 "success": True,
#                 "email": email,
#                 "customer_name": custom_data.get("customer_name"),
#                 "subject": subject,
#                 "status": "sent"
#             })
#         else:
#             logger.error(f"Failed to send email: {result.get('error')}")
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to send email: {result.get('error')}"
#             )
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error sending email: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# if __name__ == "__main__":
#     import uvicorn
    
#     port = int(os.getenv("PORT", 7860))
#     logger.info(f"Starting server on port {port}")
#     logger.info(f"Server URL: {SERVER_URL}")
#     logger.info(f"Plivo configured: {bool(PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN)}")
#     logger.info(f"WhatsApp configured: {bool(os.getenv('WHATSAPP_ACCESS_TOKEN'))}")
#     logger.info(f"Email configured: {bool(os.getenv('SMTP_USERNAME'))}")
#     logger.info(f"Greeting audio path: {GREETING_AUDIO_PATH}")
#     logger.info(f"Audio file exists: {os.path.exists(GREETING_AUDIO_PATH)}")
    
#     uvicorn.run(
#         app,
#         host="0.0.0.0",
#         port=port,
#         log_level="info"
#     )




import os
import uuid
import base64
import asyncio
from typing import Dict
from datetime import datetime
from pathlib import Path
import pytz

from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from loguru import logger
from dotenv import load_dotenv
import httpx

# Import bot function and services
from bot import bot
from whatsapp_service import send_whatsapp_message, format_payment_reminder_message
from email_service import send_email, format_payment_reminder_email

load_dotenv(override=True)

app = FastAPI()

# CORS middleware for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize queue lock and start background tasks"""
    global queue_lock
    queue_lock = asyncio.Lock()
    # Start the queue processor
    asyncio.create_task(process_call_queue())
    logger.info("Call queue processor started")

# In-memory storage for call data
call_data_store: Dict[str, dict] = {}

# Call queue for sequential processing
call_queue = []
queue_lock = None  # Will be initialized in startup
is_processing_queue = False

# Plivo credentials
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

# Sarvam AI credentials
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# Server configuration
SERVER_URL = os.getenv("SERVER_URL", "https://seagull-winning-personally.ngrok-free.app")

# Audio file paths
GREETING_AUDIO_PATH = os.getenv("GREETING_AUDIO_PATH", "output.wav")
GREETINGS_DIR = Path("greetings")
GREETINGS_DIR.mkdir(exist_ok=True)  # Create greetings directory if it doesn't exist


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    india_tz = pytz.timezone('Asia/Kolkata')
    return {
        "status": "healthy",
        "timestamp": datetime.now(india_tz).isoformat(),
        "plivo_configured": bool(PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN),
        "whatsapp_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN")),
        "email_configured": bool(os.getenv("SMTP_USERNAME")),
        "audio_file_exists": os.path.exists(GREETING_AUDIO_PATH)
    }


@app.get("/audio/greeting.wav")
async def serve_greeting_audio():
    """Serve the greeting audio file."""
    if not os.path.exists(GREETING_AUDIO_PATH):
        logger.error(f"Audio file not found at: {GREETING_AUDIO_PATH}")
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    logger.info(f"Serving audio file from: {GREETING_AUDIO_PATH}")
    return FileResponse(GREETING_AUDIO_PATH, media_type="audio/wav")


@app.get("/audio/greeting/{call_uuid}.wav")
async def serve_dynamic_greeting(call_uuid: str):
    """Serve dynamic greeting audio for a specific call"""
    file_path = GREETINGS_DIR / f"{call_uuid}.wav"
    
    if not file_path.exists():
        logger.warning(f"Dynamic greeting not found for {call_uuid}, using default")
        # Fallback to default greeting
        if os.path.exists(GREETING_AUDIO_PATH):
            return FileResponse(GREETING_AUDIO_PATH, media_type="audio/wav")
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    logger.info(f"Serving dynamic greeting for call {call_uuid}")
    return FileResponse(file_path, media_type="audio/wav")


def number_to_words(amount_str: str) -> str:
    """Convert numeric amount to words for TTS"""
    try:
        # Remove currency symbols and commas
        amount_str = str(amount_str).replace("₹", "").replace("rupees", "").replace(",", "").replace("+", "").strip()
        num = int(float(amount_str))
    except (ValueError, TypeError):
        return str(amount_str)
    
    if num == 0:
        return "zero"
    
    # Handle negative numbers
    if num < 0:
        return "minus " + number_to_words(abs(num))
    
    # Indian numbering system
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", 
             "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    
    def convert_below_thousand(n):
        if n == 0:
            return ""
        elif n < 10:
            return ones[n]
        elif n < 20:
            return teens[n - 10]
        elif n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 != 0 else "")
        else:
            return ones[n // 100] + " hundred" + (" " + convert_below_thousand(n % 100) if n % 100 != 0 else "")
    
    # Indian numbering: crore, lakh, thousand, hundred
    if num >= 10000000:  # Crore
        crore = num // 10000000
        remainder = num % 10000000
        result = convert_below_thousand(crore) + " crore"
        if remainder > 0:
            result += " " + number_to_words(remainder)
        return result
    elif num >= 100000:  # Lakh
        lakh = num // 100000
        remainder = num % 100000
        result = convert_below_thousand(lakh) + " lakh"
        if remainder > 0:
            result += " " + number_to_words(remainder)
        return result
    elif num >= 1000:  # Thousand
        thousand = num // 1000
        remainder = num % 1000
        result = convert_below_thousand(thousand) + " thousand"
        if remainder > 0:
            result += " " + convert_below_thousand(remainder)
        return result
    else:
        return convert_below_thousand(num)


async def generate_greeting_audio(text: str, call_uuid: str) -> str:
    """Generate TTS audio using Sarvam AI and save to file"""
    try:
        logger.info(f"Generating greeting for call {call_uuid}: {text}")
        
        url = "https://api.sarvam.ai/text-to-speech"
        
        payload = {
            "inputs": [text],
            "target_language_code": "en-IN",
            "speaker": "anushka",  # Female voice - matches the bot's voice
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v2"
        }
        
        headers = {
            "Content-Type": "application/json", 
            "API-Subscription-Key": SARVAM_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            response_data = response.json()
        
        # Audio is returned as base64 encoded string in the 'audios' list
        audio_base64 = response_data["audios"][0]
        audio_data = base64.b64decode(audio_base64)
            
        file_path = GREETINGS_DIR / f"{call_uuid}.wav"
        
        # Write to file
        with open(file_path, "wb") as f:
            f.write(audio_data)
        
        logger.info(f"Successfully generated greeting audio for call {call_uuid}")
        return str(file_path)
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Sarvam AI API error for call {call_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Error generating greeting audio for call {call_uuid}: {e}")
        return None


async def process_single_call(call_data: dict) -> dict:
    """Process a single call from the queue"""
    phone_number = call_data["phone_number"]
    custom_data = call_data["custom_data"]
    call_uuid = call_data["call_uuid"]
    
    try:
        logger.info(f"Processing call {call_uuid} to {phone_number}")
        
        # Generate Dynamic Greeting
        customer_name = custom_data.get("customer_name", "")
        invoice_number = custom_data.get("invoice_number", "unknown")
        outstanding_balance = custom_data.get("outstanding_balance", "")
        invoice_date = custom_data.get("invoice_date", "")
        
        # Build personalized greeting text
        if invoice_number.lower() == "unknown":
            greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding your outstanding invoice."
        else:
            spoken_invoice = invoice_number.replace("-", "").replace("/", "")
            greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding an outstanding invoice {spoken_invoice}"
            
            if outstanding_balance:
                balance_in_words = number_to_words(outstanding_balance)
                greeting_text += f" for rupees {balance_in_words}"
            
            if invoice_date:
                greeting_text += f", which was dated on {invoice_date}"
            
            greeting_text += ". I wanted to check on the status of this payment."
        
        logger.info(f"Greeting text: {greeting_text}")
        
        # Store greeting text in call_data_store for bot to access
        call_data_store[call_uuid]["greeting_text"] = greeting_text
        
        # Generate the audio file
        generated_path = await generate_greeting_audio(greeting_text, call_uuid)
        
        if not generated_path:
            logger.warning(f"Greeting generation failed for {call_uuid}, will use default")
        
        # Make Plivo API call
        plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
        answer_url = f"{SERVER_URL}/plivo_answer/{call_uuid}"
        hangup_url = f"{SERVER_URL}/plivo_hangup/{call_uuid}"
        
        plivo_payload = {
            "from": PLIVO_PHONE_NUMBER,
            "to": phone_number,
            "answer_url": answer_url,
            "answer_method": "POST",
            "hangup_url": hangup_url,
            "hangup_method": "POST"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                plivo_url,
                json=plivo_payload,
                auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
                timeout=30.0
            )
        
        if response.status_code in [200, 201, 202]:
            plivo_response = response.json()
            plivo_call_uuid = plivo_response.get("request_uuid") or plivo_response.get("message_uuid")
            
            call_data_store[call_uuid]["plivo_call_uuid"] = plivo_call_uuid
            call_data_store[call_uuid]["status"] = "calling"
            
            logger.info(f"Call initiated successfully: {call_uuid} (Plivo: {plivo_call_uuid})")
            
            return {
                "success": True,
                "call_uuid": call_uuid,
                "plivo_call_uuid": plivo_call_uuid,
                "phone_number": phone_number,
                "status": "calling"
            }
        else:
            logger.error(f"Plivo API error: {response.status_code} - {response.text}")
            call_data_store[call_uuid]["status"] = "failed"
            return {
                "success": False,
                "call_uuid": call_uuid,
                "error": f"Plivo API error: {response.text}"
            }
    
    except Exception as e:
        logger.error(f"Error processing call {call_uuid}: {e}")
        if call_uuid in call_data_store:
            call_data_store[call_uuid]["status"] = "failed"
        return {
            "success": False,
            "call_uuid": call_uuid,
            "error": str(e)
        }


async def process_call_queue():
    """Background task to process calls from queue sequentially"""
    global is_processing_queue
    
    logger.info("Call queue processor started")
    
    while True:
        try:
            async with queue_lock:
                if not call_queue:
                    is_processing_queue = False
                    await asyncio.sleep(1)
                    continue
                
                is_processing_queue = True
                call_data = call_queue.pop(0)
            
            # Process the call
            result = await process_single_call(call_data)
            logger.info(f"Call processed: {result}")
            
            # Wait for call to complete by monitoring call_data_store
            call_uuid = call_data["call_uuid"]
            max_wait_time = 600  # 10 minutes max
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                await asyncio.sleep(2)  # Check every 2 seconds
                elapsed_time += 2
                
                if call_uuid in call_data_store:
                    status = call_data_store[call_uuid].get("status")
                    if status in ["completed", "failed"]:
                        logger.info(f"Call {call_uuid} finished with status: {status}")
                        break
            
            # Small delay before next call
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error in process_call_queue: {e}")
            await asyncio.sleep(1)
    """Generate TTS audio using Sarvam AI and save to file"""
    try:
        logger.info(f"Generating greeting for call {call_uuid}: {text}")
        
        url = "https://api.sarvam.ai/text-to-speech"
        
        payload = {
            "inputs": [text],
            "target_language_code": "en-IN",
            "speaker": "anushka",  # Female voice - matches the bot's voice
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v2"
        }
        
        headers = {
            "Content-Type": "application/json", 
            "API-Subscription-Key": SARVAM_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            response_data = response.json()
        
        # Audio is returned as base64 encoded string in the 'audios' list
        audio_base64 = response_data["audios"][0]
        audio_data = base64.b64decode(audio_base64)
            
        file_path = GREETINGS_DIR / f"{call_uuid}.wav"
        
        # Write to file
        with open(file_path, "wb") as f:
            f.write(audio_data)
        
        logger.info(f"Successfully generated greeting audio for call {call_uuid}")
        return str(file_path)
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Sarvam AI API error for call {call_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Error generating greeting audio for call {call_uuid}: {e}")
        return None



VERIFY_TOKEN = "aaqil123"  # Set this to the same value you provide in Meta dashboard


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge, status_code=200)
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print("Received message:", body)  # Log the incoming payload
    return JSONResponse(content={"status": "received"}, status_code=200)


@app.post("/start")
async def start_call(request: Request):
    """
    Initiate a new call with custom data
    Expected JSON body:
    {
        "phone_number": "+919876543210",
        "body": {
            "customer_name": "John Doe",
            "invoice_number": "INV-001",
            "invoice_date": "2024-01-01",
            "total_amount": "rupees 5000",
            "outstanding_balance": "rupees 5000"
        }
    }
    """
    try:
        data = await request.json()
        phone_number = data.get("phone_number")
        custom_data = data.get("body", {})
        
        if not phone_number:
            raise HTTPException(status_code=400, detail="phone_number is required")
        
        # Generate unique call UUID
        call_uuid = str(uuid.uuid4())
        
        # Store call data with India timezone
        india_tz = pytz.timezone('Asia/Kolkata')
        call_data_store[call_uuid] = {
            "phone_number": phone_number,
            "custom_data": custom_data,
            "status": "initiated",
            "created_at": datetime.now(india_tz).isoformat(),
            "plivo_call_uuid": None
        }
        
        logger.info(f"Initiating call {call_uuid} to {phone_number}")
        logger.info(f"Custom data: {custom_data}")
        
        # Generate Dynamic Greeting BEFORE initiating the call
        customer_name = custom_data.get("customer_name", "")
        invoice_number = custom_data.get("invoice_number", "unknown")
        outstanding_balance = custom_data.get("outstanding_balance", "")
        invoice_date = custom_data.get("invoice_date", "")
        
        # Build personalized greeting text
        if invoice_number.lower() == "unknown":
            greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding your outstanding invoice."
        else:
            # Remove special characters for TTS
            spoken_invoice = invoice_number.replace("-", "").replace("/", "")
            
            # Build greeting with available information
            greeting_text = f"Hi{' ' + customer_name if customer_name else ''}, this is Sara from Hummingbird, calling regarding an outstanding invoice {spoken_invoice}"
            
            if outstanding_balance:
                # Convert balance to words for TTS
                balance_in_words = number_to_words(outstanding_balance)
                greeting_text += f" for rupees {balance_in_words}"
            
            if invoice_date:
                greeting_text += f", which was dated on {invoice_date}"
            
            greeting_text += ". I wanted to check on the status of this payment."
        
        logger.info(f"Greeting text: {greeting_text}")
        
        # Generate the audio file
        generated_path = await generate_greeting_audio(greeting_text, call_uuid)
        
        if not generated_path:
            logger.warning(f"Greeting generation failed for {call_uuid}, will use default")
        
        # Make Plivo API call to initiate the call
        plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
        
        # Construct the answer URL and hangup URL with call UUID
        answer_url = f"{SERVER_URL}/plivo_answer/{call_uuid}"
        hangup_url = f"{SERVER_URL}/plivo_hangup/{call_uuid}"
        
        plivo_payload = {
            "from": PLIVO_PHONE_NUMBER,
            "to": phone_number,
            "answer_url": answer_url,
            "answer_method": "POST",
            "hangup_url": hangup_url,
            "hangup_method": "POST"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                plivo_url,
                json=plivo_payload,
                auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
                timeout=30.0
            )
        
        if response.status_code in [200, 201, 202]:
            plivo_response = response.json()
            plivo_call_uuid = plivo_response.get("request_uuid") or plivo_response.get("message_uuid")
            
            call_data_store[call_uuid]["plivo_call_uuid"] = plivo_call_uuid
            call_data_store[call_uuid]["status"] = "calling"
            
            logger.info(f"Call initiated successfully: {call_uuid} (Plivo: {plivo_call_uuid})")
            
            return JSONResponse({
                "success": True,
                "call_uuid": call_uuid,
                "plivo_call_uuid": plivo_call_uuid,
                "phone_number": phone_number,
                "status": "calling"
            })
        else:
            logger.error(f"Plivo API error: {response.status_code} - {response.text}")
            call_data_store[call_uuid]["status"] = "failed"
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to initiate call: {response.text}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/start_batch")
async def start_batch_calls(request: Request):
    """
    Initiate a batch of calls sequentially
    Expected JSON body:
    {
        "calls": [
            {
                "phone_number": "+919876543210",
                "body": {
                    "customer_name": "John Doe",
                    "invoice_number": "INV-001",
                    ...
                }
            },
            ...
        ]
    }
    """
    try:
        data = await request.json()
        calls = data.get("calls", [])
        
        if not calls:
            raise HTTPException(status_code=400, detail="calls array is required")
        
        logger.info(f"Received batch request for {len(calls)} calls")
        
        # Add all calls to queue
        call_uuids = []
        async with queue_lock:
            for call_data in calls:
                phone_number = call_data.get("phone_number")
                custom_data = call_data.get("body", {})
                
                if not phone_number:
                    logger.warning("Skipping call with missing phone_number")
                    continue
                
                # Generate unique call UUID
                call_uuid = str(uuid.uuid4())
                
                # Store call data with India timezone
                india_tz = pytz.timezone('Asia/Kolkata')
                call_data_store[call_uuid] = {
                    "phone_number": phone_number,
                    "custom_data": custom_data,
                    "status": "queued",
                    "created_at": datetime.now(india_tz).isoformat(),
                    "plivo_call_uuid": None
                }
                
                # Add to queue
                call_queue.append({
                    "call_uuid": call_uuid,
                    "phone_number": phone_number,
                    "custom_data": custom_data
                })
                
                call_uuids.append(call_uuid)
        
        logger.info(f"Added {len(call_uuids)} calls to queue")
        
        return JSONResponse({
            "success": True,
            "message": f"Added {len(call_uuids)} calls to queue",
            "call_uuids": call_uuids,
            "queue_length": len(call_queue)
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting batch calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/plivo_answer/{call_uuid}")
async def plivo_answer(call_uuid: str, request: Request):
    """
    Plivo answer URL - returns XML to play audio greeting and connect call to WebSocket
    """
    try:
        logger.info(f"Plivo answer callback for call {call_uuid}")
        
        if call_uuid not in call_data_store:
            logger.error(f"Call UUID {call_uuid} not found")
            return JSONResponse(
                content={"error": "Call not found"},
                status_code=404
            )
        
        # Get current status
        current_status = call_data_store[call_uuid].get("status")
        logger.info(f"Current status for call {call_uuid}: {current_status}")
        
        # Only update status if call is in early stages (not yet in progress or completed)
        # Include "greeting_playing" to allow Plivo's second call after greeting finishes
        if current_status in ["initiated", "calling", "queued", "connected", "greeting_playing"]:
            # Update call status
            call_data_store[call_uuid]["status"] = "connected"
            
            # Track greeting start time and set status to greeting_playing
            call_data_store[call_uuid]["greeting_start_time"] = datetime.now().isoformat()
            call_data_store[call_uuid]["status"] = "greeting_playing"
            logger.info(f"Updated call {call_uuid} status to greeting_playing")
        else:
            # Call already progressed past greeting stage - don't change status
            logger.info(f"Call {call_uuid} already in state {current_status}, not updating status")
        
        # Get custom data for this call
        custom_data = call_data_store[call_uuid].get("custom_data", {})
        
        # Construct WebSocket URL
        ws_url = f"{SERVER_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/ws/{call_uuid}"
        
        # Construct audio URL - use dynamic greeting if available
        dynamic_greeting_path = GREETINGS_DIR / f"{call_uuid}.wav"
        if dynamic_greeting_path.exists():
            audio_url = f"{SERVER_URL}/audio/greeting/{call_uuid}.wav"
            logger.info(f"Using dynamic greeting for call {call_uuid}")
        else:
            audio_url = f"{SERVER_URL}/audio/greeting.wav"
            logger.warning(f"Dynamic greeting not found for {call_uuid}, using default")
        
        logger.info(f"Audio URL: {audio_url}")
        logger.info(f"WebSocket URL: {ws_url}")
        
        # Return Plivo XML to play audio greeting and connect to WebSocket
        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
        {ws_url}
    </Stream>
</Response>"""
        
        logger.info(f"Returning Plivo XML for call {call_uuid}")
        
        return Response(
            content=xml_response,
            media_type="application/xml"
        )
    
    except Exception as e:
        logger.error(f"Error in plivo_answer: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.post("/plivo_hangup/{call_uuid}")
async def plivo_hangup(call_uuid: str, request: Request):
    """
    Plivo hangup webhook - receives call termination details
    Handles calls that end before or during WebSocket connection
    """
    try:
        # Parse form data from Plivo
        form_data = await request.form()
        
        logger.info(f"Hangup webhook for call {call_uuid}")
        logger.info(f"Hangup data: {dict(form_data)}")
        
        if call_uuid not in call_data_store:
            logger.warning(f"Call UUID {call_uuid} not found in hangup webhook")
            return Response(status_code=200)
        
        # Extract hangup information
        hangup_cause = form_data.get("HangupCause", "")
        hangup_source = form_data.get("HangupSource", "Unknown")
        call_status = form_data.get("CallStatus", "")
        
        # Update call data
        call_data_store[call_uuid]["hangup_cause"] = hangup_cause
        call_data_store[call_uuid]["hangup_source"] = hangup_source
        call_data_store[call_uuid]["ended_at"] = datetime.now().isoformat()
        
        # Only update status if not already completed (avoid overwriting WebSocket status)
        current_status = call_data_store[call_uuid].get("status")
        if current_status not in ["completed", "in_progress"]:
            # Set status to completed so queue can move on
            call_data_store[call_uuid]["status"] = "completed"
            logger.info(f"Call {call_uuid} marked as completed via hangup webhook")
        else:
            logger.info(f"Call {call_uuid} already in status '{current_status}', not overwriting")
        
        logger.info(f"Call {call_uuid} ended - Hangup Cause: {hangup_cause}, Source: {hangup_source}")
        
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"Error in hangup webhook: {e}")
        return Response(status_code=200)


@app.websocket("/ws/{call_uuid}")
async def websocket_endpoint(websocket: WebSocket, call_uuid: str):
    """
    WebSocket endpoint for Pipecat bot
    """
    await websocket.accept()
    logger.info(f"WebSocket connection established for call {call_uuid}")
    
    # Store custom data in websocket state for bot to access
    if call_uuid in call_data_store:
        websocket.state.custom_data = call_data_store[call_uuid].get("custom_data", {})
        # Add greeting_text to custom_data so bot knows what was said
        websocket.state.custom_data["greeting_text"] = call_data_store[call_uuid].get("greeting_text", "")
        websocket.state.call_uuid = call_uuid
        call_data_store[call_uuid]["status"] = "in_progress"
    else:
        logger.warning(f"Call UUID {call_uuid} not found in store")
        websocket.state.custom_data = {}
        websocket.state.call_uuid = call_uuid
    
    try:
        # Import runner arguments - use WebSocketRunnerArguments for WebSocket connections
        from pipecat.runner.types import WebSocketRunnerArguments
        
        # Create runner arguments
        runner_args = WebSocketRunnerArguments(
            websocket=websocket
        )
        runner_args.handle_sigint = False
        
        # Run the bot
        await bot(runner_args)
        
    except Exception as e:
        logger.error(f"Error in WebSocket for call {call_uuid}: {e}")
    finally:
        logger.info(f"WebSocket closed for call {call_uuid}")
        if call_uuid in call_data_store:
            call_data_store[call_uuid]["status"] = "completed"
            call_data_store[call_uuid]["ended_at"] = datetime.now().isoformat()
        
        # Clean up dynamic greeting file
        dynamic_greeting_path = GREETINGS_DIR / f"{call_uuid}.wav"
        if dynamic_greeting_path.exists():
            try:
                dynamic_greeting_path.unlink()
                logger.info(f"Deleted dynamic greeting for call {call_uuid}")
            except Exception as e:
                logger.error(f"Error deleting greeting file for {call_uuid}: {e}")


@app.get("/calls")
async def list_calls():
    """
    List all calls with their current status
    """
    return {
        "calls": [
            {
                "call_uuid": call_uuid,
                "phone_number": data["phone_number"],
                "status": data["status"],
                "created_at": data["created_at"],
                "ended_at": data.get("ended_at"),
                "customer_name": data.get("custom_data", {}).get("customer_name", "Unknown"),
                "invoice_number": data.get("custom_data", {}).get("invoice_number", "N/A")
            }
            for call_uuid, data in call_data_store.items()
        ]
    }


@app.get("/transcripts")
async def list_transcripts():
    """
    List all transcript files with metadata
    Returns a list of transcripts with parsed metadata
    """
    import re
    from datetime import datetime as dt
    
    try:
        transcripts_dir = Path("transcripts")
        
        # Check if directory exists
        if not transcripts_dir.exists():
            return {"transcripts": []}
        
        transcripts = []
        
        # Iterate through all .txt files in transcripts directory
        for transcript_file in transcripts_dir.glob("*.txt"):
            try:
                # Parse filename: invoicenumber_calluuid.txt
                filename = transcript_file.name
                parts = filename.replace(".txt", "").split("_", 1)
                
                invoice_number = parts[0] if len(parts) > 0 else "unknown"
                call_uuid = parts[1] if len(parts) > 1 else "unknown"
                
                # Read file to extract metadata
                with open(transcript_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Extract metadata from file
                metadata = {
                    "filename": filename,
                    "invoice_number": invoice_number,
                    "call_uuid": call_uuid,
                    "file_size": transcript_file.stat().st_size,
                    "created_at": datetime.fromtimestamp(transcript_file.stat().st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat(),
                }
                
                # Try to extract customer name from content
                if "Customer Name:" in content:
                    start = content.index("Customer Name:") + len("Customer Name:")
                    end = content.index("\n", start)
                    metadata["customer_name"] = content[start:end].strip()
                else:
                    metadata["customer_name"] = "N/A"
                
                # Check if summary exists
                metadata["has_summary"] = "CALL SUMMARY (Generated by AI)" in content
                
                # Extract status
                if "Status: Completed" in content:
                    metadata["status"] = "completed"
                else:
                    metadata["status"] = "in_progress"
                
                # Extract call outcomes from summary (now supports multiple outcomes)
                metadata["call_outcomes"] = []
                metadata["cut_off_date"] = None
                if "**CALL OUTCOMES:**" in content:
                    try:
                        start = content.index("**CALL OUTCOMES:**") + len("**CALL OUTCOMES:**")
                        # Find the end of the outcomes section (before the numbered list starts)
                        end = content.index("\n1.", start) if "\n1." in content[start:] else len(content)
                        outcomes_section = content[start:end].strip()
                        
                        # Parse each outcome line (format: "- OUTCOME_NAME: details")
                        for line in outcomes_section.split('\n'):
                            line = line.strip()
                            if line.startswith('-'):
                                # Extract outcome name (before the colon)
                                outcome_part = line[1:].strip()  # Remove the dash
                                if ':' in outcome_part:
                                    outcome_name = outcome_part.split(':')[0].strip()
                                else:
                                    outcome_name = outcome_part.strip()
                                
                                if outcome_name:
                                    metadata["call_outcomes"].append(outcome_name)
                        
                        # Extract cut-off date if CUT_OFF_DATE_PROVIDED is one of the outcomes
                        if "CUT_OFF_DATE_PROVIDED" in metadata["call_outcomes"]:
                            # Look for date patterns in the summary
                            
                            # Get the summary section
                            if "CALL SUMMARY" in content:
                                summary_start = content.index("CALL SUMMARY")
                                summary_section = content[summary_start:]
                                
                                # Look for common date patterns
                                # Pattern 1: "January 6, 2026" or "Jan 6, 2026"
                                date_pattern1 = r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})'
                                # Pattern 2: "2026-01-06" or "01/06/2026"
                                date_pattern2 = r'(\d{4})-(\d{2})-(\d{2})'
                                date_pattern3 = r'(\d{2})/(\d{2})/(\d{4})'
                                
                                match = re.search(date_pattern1, summary_section, re.IGNORECASE)
                                if match:
                                    try:
                                        date_str = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
                                        parsed_date = dt.strptime(date_str, "%B %d, %Y")
                                        metadata["cut_off_date"] = parsed_date.strftime("%Y-%m-%d")
                                    except:
                                        try:
                                            date_str = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
                                            parsed_date = dt.strptime(date_str, "%b %d, %Y")
                                            metadata["cut_off_date"] = parsed_date.strftime("%Y-%m-%d")
                                        except:
                                            pass
                                
                                if not metadata["cut_off_date"]:
                                    match = re.search(date_pattern2, summary_section)
                                    if match:
                                        metadata["cut_off_date"] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                    except Exception as e:
                        logger.error(f"Error parsing outcomes: {e}")
                        # Fallback to empty list
                        metadata["call_outcomes"] = []
                
                transcripts.append(metadata)
                
            except Exception as e:
                logger.error(f"Error parsing transcript file {transcript_file}: {e}")
                continue
        
        # Sort by created_at descending (most recent first)
        transcripts.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {"transcripts": transcripts}
    
    except Exception as e:
        logger.error(f"Error listing transcripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transcripts/{filename}")
async def get_transcript(filename: str):
    """
    Get the full content of a specific transcript file
    Returns the transcript with conversation and summary
    """
    try:
        transcripts_dir = Path("transcripts")
        transcript_file = transcripts_dir / filename
        
        # Security check: ensure file is in transcripts directory
        if not transcript_file.resolve().is_relative_to(transcripts_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        if not transcript_file.exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Read file content
        with open(transcript_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse the content into sections
        sections = {
            "metadata": "",
            "conversation": "",
            "summary": ""
        }
        
        # Split content into sections
        if "CONVERSATION:" in content:
            parts = content.split("CONVERSATION:")
            sections["metadata"] = parts[0].strip()
            
            if len(parts) > 1:
                conversation_part = parts[1]
                
                # Look for summary section - handle both with and without equals signs
                summary_markers = [
                    "=== CALL SUMMARY (Generated by AI) ===",
                    "CALL SUMMARY (Generated by AI)"
                ]
                
                summary_found = False
                for marker in summary_markers:
                    if marker in conversation_part:
                        conv_parts = conversation_part.split(marker)
                        sections["conversation"] = conv_parts[0].strip()
                        if len(conv_parts) > 1:
                            # Remove leading/trailing equals signs and whitespace
                            summary_content = conv_parts[1].strip()
                            # Remove any leading/trailing equals sign lines
                            summary_lines = summary_content.split('\n')
                            summary_lines = [line for line in summary_lines if line.strip() and not all(c == '=' for c in line.strip())]
                            sections["summary"] = '\n'.join(summary_lines).strip()
                        else:
                            sections["summary"] = ""
                        summary_found = True
                        break
                
                if not summary_found:
                    sections["conversation"] = conversation_part.strip()
        
        return {
            "filename": filename,
            "full_content": content,
            "sections": sections,
            "file_size": transcript_file.stat().st_size,
            "created_at": datetime.fromtimestamp(transcript_file.stat().st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading transcript {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/whatsapp/send")
async def send_whatsapp(request: Request):
    """
    Send WhatsApp message
    Expected JSON body:
    {
        "phone_number": "919876543210",
        "body": {
            "customer_name": "John Doe",
            "invoice_number": "INV-001",
            "invoice_date": "2024-01-01",
            "total_amount": "rupees 5000",
            "outstanding_balance": "rupees 5000"
        }
    }
    """
    try:
        data = await request.json()
        phone_number = data.get("phone_number")
        custom_data = data.get("body", {})
        
        if not phone_number:
            raise HTTPException(status_code=400, detail="phone_number is required")
        
        # Remove + from phone number if present (WhatsApp API expects without +)
        phone_number = phone_number.replace("+", "")
        
        # Format the payment reminder message
        message_text = format_payment_reminder_message(custom_data)
        
        # Send WhatsApp message
        result = send_whatsapp_message(phone_number, message_text)
        
        if result.get("success"):
            logger.info(f"WhatsApp message sent to {phone_number}")
            return JSONResponse({
                "success": True,
                "message_id": result.get("message_id"),
                "phone_number": phone_number,
                "customer_name": custom_data.get("customer_name"),
                "status": "sent"
            })
        else:
            logger.error(f"Failed to send WhatsApp: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send WhatsApp message: {result.get('error')}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending WhatsApp: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/email/send")
async def send_email_reminder(request: Request):
    """
    Send Email reminder
    Expected JSON body:
    {
        "email": "customer@example.com",
        "body": {
            "customer_name": "John Doe",
            "invoice_number": "INV-001",
            "invoice_date": "2024-01-01",
            "total_amount": "rupees 5000",
            "outstanding_balance": "rupees 5000"
        }
    }
    """
    try:
        data = await request.json()
        email = data.get("email")
        custom_data = data.get("body", {})
        
        if not email:
            raise HTTPException(status_code=400, detail="email is required")
        
        # Format the payment reminder email
        subject, html_body, text_body = format_payment_reminder_email(custom_data)
        
        # Send email
        result = send_email(email, subject, html_body, text_body)
        
        if result.get("success"):
            logger.info(f"Email sent to {email}")
            return JSONResponse({
                "success": True,
                "email": email,
                "customer_name": custom_data.get("customer_name"),
                "subject": subject,
                "status": "sent"
            })
        else:
            logger.error(f"Failed to send email: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {result.get('error')}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 7860))
    logger.info(f"Starting server on port {port}")
    logger.info(f"Server URL: {SERVER_URL}")
    logger.info(f"Plivo configured: {bool(PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN)}")
    logger.info(f"WhatsApp configured: {bool(os.getenv('WHATSAPP_ACCESS_TOKEN'))}")
    logger.info(f"Email configured: {bool(os.getenv('SMTP_USERNAME'))}")
    logger.info(f"Greeting audio path: {GREETING_AUDIO_PATH}")
    logger.info(f"Audio file exists: {os.path.exists(GREETING_AUDIO_PATH)}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
