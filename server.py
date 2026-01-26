import os
import uuid
import base64
import asyncio
from typing import Dict
from datetime import datetime
from pathlib import Path
import pytz

from fastapi import FastAPI, WebSocket, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from loguru import logger
from dotenv import load_dotenv
import httpx
from pydantic import BaseModel

# Import bot function and services
from bot import bot
from whatsapp_service import send_whatsapp_message, format_payment_reminder_message
from email_service import send_email, format_payment_reminder_email

# Import authentication modules
from database import Database
from auth import create_access_token, get_current_user, require_super_admin

load_dotenv(override=True)

app = FastAPI()

# Initialize database
db = Database()
logger.info("Database initialized")

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


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

# Pydantic models for request bodies
class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"

class UpdateUserRequest(BaseModel):
    email: str = None
    is_active: bool = None

class ChangePasswordRequest(BaseModel):
    old_password: str = None  # Required for users changing their own password
    new_password: str


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Login endpoint - returns JWT token"""
    user = db.get_user_by_username(request.username)
    
    if not user or not db.verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if not user["is_active"]:
        raise HTTPException(status_code=401, detail="User account is disabled")
    
    # Create JWT token
    access_token = create_access_token({
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"]
    })
    
    logger.info(f"User logged in: {user['username']} (Role: {user['role']})")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"]
        }
    }


@app.get("/api/auth/me")
async def get_me(current_user = Depends(get_current_user)):
    """Get current user info from JWT token"""
    user = db.get_user_by_id(current_user["user_id"])
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "is_active": user["is_active"]
    }


@app.post("/api/users")
async def create_user(request: CreateUserRequest, current_user = Depends(require_super_admin)):
    """Create new user (super admin only)"""
    try:
        user_id = db.create_user(request.username, request.email, request.password, request.role)
        
        # Create user-specific transcript directory
        user_transcript_dir = Path(f"transcripts/user_{user_id}")
        user_transcript_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created transcript directory for user {user_id}")
        
        return {
            "id": user_id,
            "username": request.username,
            "email": request.email,
            "role": request.role,
            "message": "User created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/users")
async def get_users(current_user = Depends(require_super_admin)):
    """Get all users (super admin only)"""
    users = db.get_all_users()
    return {"users": users}


@app.put("/api/users/{user_id}")
async def update_user(user_id: int, request: UpdateUserRequest, current_user = Depends(require_super_admin)):
    """Update user (super admin only)"""
    try:
        db.update_user(user_id, email=request.email, is_active=request.is_active)
        user = db.get_user_by_id(user_id)
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "message": "User updated successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, current_user = Depends(require_super_admin)):
    """Soft delete user (super admin only)"""
    try:
        # Prevent deleting yourself
        if user_id == current_user["user_id"]:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
        db.delete_user(user_id)
        return {"message": "User deactivated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/change-password")
async def change_own_password(request: ChangePasswordRequest, current_user = Depends(get_current_user)):
    """Change own password (any authenticated user)"""
    try:
        user = db.get_user_by_id(current_user["user_id"])
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify old password
        if not request.old_password:
            raise HTTPException(status_code=400, detail="Old password is required")
        
        if not db.verify_password(request.old_password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        
        # Change password
        db.change_password(current_user["user_id"], request.new_password)
        
        logger.info(f"User {user['username']} changed their password")
        return {"message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/users/{user_id}/reset-password")
async def reset_user_password(user_id: int, request: ChangePasswordRequest, current_user = Depends(require_super_admin)):
    """Reset user password (super admin only)"""
    try:
        user = db.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Super admin doesn't need to provide old password
        db.change_password(user_id, request.new_password)
        
        logger.info(f"Super admin {current_user['username']} reset password for user {user['username']}")
        return {"message": f"Password reset successfully for user {user['username']}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# END AUTHENTICATION ENDPOINTS
# ============================================================================


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@app.get("/api/export/call_status")
async def export_call_status(
    status: str = "all",
    date_filter: str = "all",
    start_date: str = None,
    end_date: str = None,
    current_user = Depends(get_current_user)
):
    """
    Export call data filtered by status and date
    Returns CSV with: customer data + call status + created_at + call_outcomes + cutoff_date
    """
    try:
        import io
        import csv
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # Get data from database (same as transcripts export)
        data = db.get_export_data_with_transcripts(user_id=current_user["user_id"])
        
        if not data:
            raise HTTPException(status_code=404, detail="No data found for export")
        
        # Filter by status if specified
        if status != "all":
            data = [record for record in data if record["call_status"] == status]
        
        # Apply date filter
        if date_filter != "all":
            now = datetime.now()
            today = datetime(now.year, now.month, now.day)
            
            filtered_data = []
            for record in data:
                try:
                    # Parse the created_at timestamp
                    record_date = datetime.fromisoformat(record["created_at"].replace('Z', '+00:00'))
                    
                    if date_filter == "today":
                        if record_date >= today:
                            filtered_data.append(record)
                    elif date_filter == "yesterday":
                        yesterday = today - timedelta(days=1)
                        if yesterday <= record_date < today:
                            filtered_data.append(record)
                    elif date_filter == "last7days":
                        last7days = today - timedelta(days=7)
                        if record_date >= last7days:
                            filtered_data.append(record)
                    elif date_filter == "last30days":
                        last30days = today - timedelta(days=30)
                        if record_date >= last30days:
                            filtered_data.append(record)
                    elif date_filter == "custom":
                        if start_date and end_date:
                            start = datetime.fromisoformat(start_date)
                            end = datetime.fromisoformat(end_date)
                            end = end.replace(hour=23, minute=59, second=59)
                            if start <= record_date <= end:
                                filtered_data.append(record)
                        elif start_date:
                            start = datetime.fromisoformat(start_date)
                            if record_date >= start:
                                filtered_data.append(record)
                        elif end_date:
                            end = datetime.fromisoformat(end_date)
                            end = end.replace(hour=23, minute=59, second=59)
                            if record_date <= end:
                                filtered_data.append(record)
                except Exception as e:
                    logger.warning(f"Error parsing date for record: {e}")
                    continue
            
            data = filtered_data
        
        # Enrich with call outcomes from transcript files (same logic as transcripts export)
        transcript_base_dir = Path(f"transcripts/user_{current_user['user_id']}")
        
        for record in data:
            call_uuid = record["call_uuid"]
            invoice_number = record["invoice_number"]
            
            # Find transcript file
            transcript_file = None
            if transcript_base_dir.exists():
                # Look for transcript file matching invoice_number and call_uuid
                for file in transcript_base_dir.glob(f"{invoice_number}_*.txt"):
                    if call_uuid in file.stem:
                        transcript_file = file
                        break
            
            # Extract call outcomes and cutoff date from transcript
            call_outcomes = "N/A"
            cutoff_date = ""
            if transcript_file and transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Extract outcomes from summary
                    if "**CALL OUTCOMES:**" in content:
                        start = content.index("**CALL OUTCOMES:**") + len("**CALL OUTCOMES:**")
                        # Find end of outcomes section (before numbered list)
                        end = content.find("\n\n", start)
                        if end == -1:
                            end = content.find("1.", start)
                        if end == -1:
                            end = len(content)
                        
                        outcomes_text = content[start:end].strip()
                        # Extract just the outcome names (remove "- " and details after ":")
                        outcomes = []
                        for line in outcomes_text.split('\n'):
                            line = line.strip()
                            if line.startswith('- '):
                                outcome = line[2:].split(':')[0].strip()
                                if outcome:
                                    outcomes.append(outcome)
                                
                                # Extract cutoff date if outcome is CUT_OFF_DATE_PROVIDED
                                if outcome == "CUT_OFF_DATE_PROVIDED" and ':' in line:
                                    date_text = line.split(':', 1)[1].strip()
                                    # Try to parse the date
                                    try:
                                        from dateutil import parser as date_parser
                                        parsed_date = date_parser.parse(date_text, fuzzy=True)
                                        cutoff_date = parsed_date.strftime("%Y-%m-%d")
                                    except:
                                        cutoff_date = date_text  # Use raw text if parsing fails
                        
                        call_outcomes = ", ".join(outcomes) if outcomes else "N/A"
                except Exception as e:
                    logger.warning(f"Error reading transcript for {call_uuid}: {e}")
            
            record["call_outcomes"] = call_outcomes
            record["cutoff_date"] = cutoff_date
            # Remove call_uuid from export
            del record["call_uuid"]
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "customer_name", "phone_number", "whatsapp_number", "email",
            "invoice_number", "invoice_date", "total_amount", "outstanding_balance",
            "call_status", "created_at", "call_outcomes", "cutoff_date"
        ])
        
        writer.writeheader()
        writer.writerows(data)
        
        # Return as downloadable CSV
        csv_content = output.getvalue()
        output.close()
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=call_status_export_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting call status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/transcripts")
async def export_transcripts(
    date_filter: str = "all",
    start_date: str = None,
    end_date: str = None,
    search: str = None,
    outcome: str = "all",
    cutoff_date: str = None,
    current_user = Depends(get_current_user)
):
    """
    Export call data with transcript outcomes filtered by date, search, outcome, and cutoff date
    Returns CSV with: customer data + call status + created_at + call_outcomes
    """
    try:
        import io
        import csv
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # Get data from database
        data = db.get_export_data_with_transcripts(user_id=current_user["user_id"])
        
        if not data:
            raise HTTPException(status_code=404, detail="No data found for export")
        
        # Enrich with call outcomes from transcript files
        transcript_base_dir = Path(f"transcripts/user_{current_user['user_id']}")
        
        for record in data:
            call_uuid = record["call_uuid"]
            invoice_number = record["invoice_number"]
            
            # Find transcript file
            transcript_file = None
            if transcript_base_dir.exists():
                # Look for transcript file matching invoice_number and call_uuid
                for file in transcript_base_dir.glob(f"{invoice_number}_*.txt"):
                    if call_uuid in file.stem:
                        transcript_file = file
                        break
            
            # Extract call outcomes and cutoff date from transcript
            call_outcomes = "N/A"
            cutoff_date = ""
            if transcript_file and transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Extract outcomes from summary
                    if "**CALL OUTCOMES:**" in content:
                        start = content.index("**CALL OUTCOMES:**") + len("**CALL OUTCOMES:**")
                        # Find end of outcomes section (before numbered list)
                        end = content.find("\n\n", start)
                        if end == -1:
                            end = content.find("1.", start)
                        if end == -1:
                            end = len(content)
                        
                        outcomes_text = content[start:end].strip()
                        # Extract just the outcome names (remove "- " and details after ":")
                        outcomes = []
                        for line in outcomes_text.split('\n'):
                            line = line.strip()
                            if line.startswith('- '):
                                outcome = line[2:].split(':')[0].strip()
                                if outcome:
                                    outcomes.append(outcome)
                                
                                # Extract cutoff date if outcome is CUT_OFF_DATE_PROVIDED
                                if outcome == "CUT_OFF_DATE_PROVIDED" and ':' in line:
                                    date_text = line.split(':', 1)[1].strip()
                                    # Try to parse the date
                                    try:
                                        from dateutil import parser as date_parser
                                        parsed_date = date_parser.parse(date_text, fuzzy=True)
                                        cutoff_date = parsed_date.strftime("%Y-%m-%d")
                                    except:
                                        cutoff_date = date_text  # Use raw text if parsing fails
                        
                        call_outcomes = ", ".join(outcomes) if outcomes else "N/A"
                except Exception as e:
                    logger.warning(f"Error reading transcript for {call_uuid}: {e}")
            
            record["call_outcomes"] = call_outcomes
            record["cutoff_date"] = cutoff_date
            # Remove call_uuid from export
            del record["call_uuid"]
        
        # Apply filters after enriching data
        filtered_data = []
        
        for record in data:
            # Date filter
            if date_filter != "all":
                try:
                    record_date = datetime.fromisoformat(record["created_at"].replace('Z', '+00:00'))
                    now = datetime.now()
                    today = datetime(now.year, now.month, now.day)
                    
                    if date_filter == "today":
                        if record_date < today:
                            continue
                    elif date_filter == "yesterday":
                        yesterday = today - timedelta(days=1)
                        if not (yesterday <= record_date < today):
                            continue
                    elif date_filter == "last7days":
                        last7days = today - timedelta(days=7)
                        if record_date < last7days:
                            continue
                    elif date_filter == "last30days":
                        last30days = today - timedelta(days=30)
                        if record_date < last30days:
                            continue
                    elif date_filter == "custom":
                        if start_date and end_date:
                            start = datetime.fromisoformat(start_date)
                            end = datetime.fromisoformat(end_date)
                            end = end.replace(hour=23, minute=59, second=59)
                            if not (start <= record_date <= end):
                                continue
                        elif start_date:
                            start = datetime.fromisoformat(start_date)
                            if record_date < start:
                                continue
                        elif end_date:
                            end = datetime.fromisoformat(end_date)
                            end = end.replace(hour=23, minute=59, second=59)
                            if record_date > end:
                                continue
                except Exception as e:
                    logger.warning(f"Error parsing date for record: {e}")
                    continue
            
            # Search filter
            if search:
                search_lower = search.lower()
                if not (
                    search_lower in record.get("customer_name", "").lower() or
                    search_lower in record.get("invoice_number", "").lower() or
                    search_lower in record.get("phone_number", "").lower() or
                    search_lower in record.get("call_status", "").lower()
                ):
                    continue
            
            # Outcome filter
            if outcome != "all":
                record_outcomes = record.get("call_outcomes", "")
                if outcome not in record_outcomes:
                    continue
            
            # Cutoff date filter (only applies when outcome is CUT_OFF_DATE_PROVIDED)
            if cutoff_date and outcome == "CUT_OFF_DATE_PROVIDED":
                if record.get("cutoff_date") != cutoff_date:
                    continue
            
            filtered_data.append(record)
        
        data = filtered_data
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "customer_name", "phone_number", "whatsapp_number", "email",
            "invoice_number", "invoice_date", "total_amount", "outstanding_balance",
            "call_status", "created_at", "call_outcomes", "cutoff_date"
        ])
        
        writer.writeheader()
        writer.writerows(data)
        
        # Return as downloadable CSV
        csv_content = output.getvalue()
        output.close()
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=transcripts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting transcripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# END EXPORT ENDPOINTS
# ============================================================================


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
            "speaker": "abhilash",  # Male voice - matches the bot's voice
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
        balance_in_words = number_to_words(outstanding_balance) if outstanding_balance else "unknown"
        greeting_text = f"Hi, this is Farooq from Hummingbird's commercial team. I'm calling regarding the T A C due of rupees {balance_in_words} for the invoice dated {invoice_date}. When can we expect the payment?"
        
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
            
            # Persist to database
            db.update_call_status(call_uuid, "calling", plivo_call_uuid=plivo_call_uuid)
            
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
            
            # Persist to database
            db.update_call_status(call_uuid, "failed")
            
            return {
                "success": False,
                "call_uuid": call_uuid,
                "error": f"Plivo API error: {response.text}"
            }
    
    except Exception as e:
        logger.error(f"Error processing call {call_uuid}: {e}")
        if call_uuid in call_data_store:
            call_data_store[call_uuid]["status"] = "failed"
            
            # Persist to database
            db.update_call_status(call_uuid, "failed")
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
                    if status in ["completed", "failed", "declined", "invalid", "out_of_service", "nonexistent", "unallocated", "not_reachable"]:
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
            "speaker": "abhilash",  # Male voice - matches the bot's voice
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
async def start_call(request: Request, current_user = Depends(get_current_user)):
    """
    Initiate a new call with custom data (requires authentication)
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
        
        # Store call data with India timezone and user_id
        india_tz = pytz.timezone('Asia/Kolkata')
        created_at = datetime.now(india_tz).isoformat()
        
        call_data_store[call_uuid] = {
            "phone_number": phone_number,
            "custom_data": custom_data,
            "status": "initiated",
            "created_at": created_at,
            "plivo_call_uuid": None,
            "user_id": current_user["user_id"]  # Add user_id for data isolation
        }
        
        # Persist to database
        db.create_call(
            call_uuid=call_uuid,
            phone_number=phone_number,
            customer_name=custom_data.get("customer_name", ""),
            invoice_number=custom_data.get("invoice_number", ""),
            user_id=current_user["user_id"],
            custom_data=custom_data,
            created_at=created_at
        )
        
        # Insert customer data (standard columns only)
        db.insert_customer_data(
            call_uuid=call_uuid,
            customer_name=custom_data.get("customer_name", ""),
            phone_number=phone_number,
            whatsapp_number=custom_data.get("whatsapp_number", ""),
            email=custom_data.get("email", ""),
            invoice_number=custom_data.get("invoice_number", ""),
            invoice_date=custom_data.get("invoice_date", ""),
            total_amount=custom_data.get("total_amount", ""),
            outstanding_balance=custom_data.get("outstanding_balance", ""),
            created_at=created_at
        )
        
        logger.info(f"Initiating call {call_uuid} to {phone_number}")
        logger.info(f"Custom data received (customer info redacted for security)")
        
        # Generate Dynamic Greeting BEFORE initiating the call
        customer_name = custom_data.get("customer_name", "")
        invoice_number = custom_data.get("invoice_number", "unknown")
        outstanding_balance = custom_data.get("outstanding_balance", "")
        invoice_date = custom_data.get("invoice_date", "")
        
        # Build personalized greeting text
        balance_in_words = number_to_words(outstanding_balance) if outstanding_balance else "unknown"
        greeting_text = f"Hi, this is Farooq from Hummingbird's commercial team. I'm calling regarding the T A C due of rupees {balance_in_words} for the invoice dated {invoice_date}. When can we expect the payment?"
        
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
            
            # Persist to database
            db.update_call_status(call_uuid, "calling", plivo_call_uuid=plivo_call_uuid)
            
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
            
            # Persist to database
            db.update_call_status(call_uuid, "failed")
            
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
async def start_batch_calls(request: Request, current_user = Depends(get_current_user)):
    """
    Initiate a batch of calls sequentially (requires authentication)
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
        
        logger.info(f"Received batch request for {len(calls)} calls from user {current_user['user_id']}")
        
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
                
                # Store call data with India timezone and user_id
                india_tz = pytz.timezone('Asia/Kolkata')
                created_at = datetime.now(india_tz).isoformat()
                
                call_data_store[call_uuid] = {
                    "phone_number": phone_number,
                    "custom_data": custom_data,
                    "status": "queued",
                    "created_at": created_at,
                    "plivo_call_uuid": None,
                    "user_id": current_user["user_id"]  # Add user_id for data isolation
                }
                
                # Persist to database
                db.create_call(
                    call_uuid=call_uuid,
                    phone_number=phone_number,
                    customer_name=custom_data.get("customer_name", ""),
                    invoice_number=custom_data.get("invoice_number", ""),
                    user_id=current_user["user_id"],
                    custom_data=custom_data,
                    created_at=created_at
                )
                
                # Insert customer data (standard columns only)
                db.insert_customer_data(
                    call_uuid=call_uuid,
                    customer_name=custom_data.get("customer_name", ""),
                    phone_number=phone_number,
                    whatsapp_number=custom_data.get("whatsapp_number", ""),
                    email=custom_data.get("email", ""),
                    invoice_number=custom_data.get("invoice_number", ""),
                    invoice_date=custom_data.get("invoice_date", ""),
                    total_amount=custom_data.get("total_amount", ""),
                    outstanding_balance=custom_data.get("outstanding_balance", ""),
                    created_at=created_at
                )
                
                # Update status to queued in database
                db.update_call_status(call_uuid, "queued")
                
                # Add to queue
                call_queue.append({
                    "call_uuid": call_uuid,
                    "phone_number": phone_number,
                    "custom_data": custom_data
                })
                
                call_uuids.append(call_uuid)
        
        logger.info(f"Added {len(call_uuids)} calls to queue for user {current_user['user_id']}")
        
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
            
            # Persist to database
            db.update_call_status(call_uuid, "greeting_playing")
            
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
        hangup_cause_name = form_data.get("HangupCauseName", "")
        hangup_cause_code = form_data.get("HangupCauseCode", "")
        hangup_source = form_data.get("HangupSource", "Unknown")
        call_status = form_data.get("CallStatus", "")
        ended_at = datetime.now().isoformat()
        
        # Update call data
        call_data_store[call_uuid]["hangup_cause"] = hangup_cause
        call_data_store[call_uuid]["hangup_source"] = hangup_source
        call_data_store[call_uuid]["ended_at"] = ended_at
        
        # Only update status if not already completed (avoid overwriting WebSocket status)
        current_status = call_data_store[call_uuid].get("status")
        if current_status not in ["completed", "in_progress"]:
            # Map hangup causes to specific statuses
            if hangup_cause_name == "Rejected" or hangup_cause_code == "3020":
                status = "declined"
                logger.info(f"Call {call_uuid} was declined/rejected by user (Code: {hangup_cause_code})")
            elif hangup_cause_name == "Invalid Destination Address" or hangup_cause_code == "2000":
                status = "invalid"
                logger.info(f"Call {call_uuid} has invalid number format (Code: {hangup_cause_code})")
            elif hangup_cause_name == "Destination Out Of Service" or hangup_cause_code == "2010":
                status = "out_of_service"
                logger.info(f"Call {call_uuid} destination is out of service (Code: {hangup_cause_code})")
            elif hangup_cause_name == "User does not exist anywhere" or hangup_cause_code == "3120":
                status = "nonexistent"
                logger.info(f"Call {call_uuid} destination number does not exist (Code: {hangup_cause_code})")
            elif hangup_cause_name == "Unallocated number" or hangup_cause_code == "3050":
                status = "unallocated"
                logger.info(f"Call {call_uuid} destination number is unallocated (Code: {hangup_cause_code})")
            elif hangup_cause_name == "No Answer" or hangup_cause_code == "3000":
                status = "not_reachable"
                logger.info(f"Call {call_uuid} destination not reachable/no answer (Code: {hangup_cause_code})")
            else:
                # Set status to completed for all other cases
                status = "completed"
            
            call_data_store[call_uuid]["status"] = status
            
            # Persist to database
            db.update_call_status(call_uuid, status, ended_at=ended_at, 
                                hangup_cause=hangup_cause, hangup_source=hangup_source)
            
            logger.info(f"Call {call_uuid} marked as {status} via hangup webhook")
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
        # Add user_id to custom_data for transcript organization
        websocket.state.custom_data["user_id"] = call_data_store[call_uuid].get("user_id")
        websocket.state.call_uuid = call_uuid
        call_data_store[call_uuid]["status"] = "in_progress"
        
        # Persist to database
        db.update_call_status(call_uuid, "in_progress")
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
            ended_at = datetime.now().isoformat()
            call_data_store[call_uuid]["status"] = "completed"
            call_data_store[call_uuid]["ended_at"] = ended_at
            
            # Persist to database
            db.update_call_status(call_uuid, "completed", ended_at=ended_at)
        
        # Clean up dynamic greeting file
        dynamic_greeting_path = GREETINGS_DIR / f"{call_uuid}.wav"
        if dynamic_greeting_path.exists():
            try:
                dynamic_greeting_path.unlink()
                logger.info(f"Deleted dynamic greeting for call {call_uuid}")
            except Exception as e:
                logger.error(f"Error deleting greeting file for {call_uuid}: {e}")


@app.get("/calls")
async def list_calls(user_id: int = None, current_user = Depends(get_current_user)):
    """
    List calls with their current status from database (persistent call history)
    - Regular users: see only their own calls
    - Super admin: can see all calls or filter by user_id parameter
    """
    # Determine which user's calls to show
    if current_user["role"] == "super_admin":
        if user_id == 0:
            # user_id=0 means "all users" for super admin
            filter_user_id = None
        elif user_id is not None:
            # Super admin viewing specific user's calls
            filter_user_id = user_id
        else:
            # No user_id specified, show super admin's own calls
            filter_user_id = current_user["user_id"]
    else:
        # Regular user can only see their own calls
        filter_user_id = current_user["user_id"]
    
    # Get calls from database
    db_calls = db.get_calls(user_id=filter_user_id)
    
    # Merge with in-memory data for active calls (to get real-time status)
    calls_list = []
    for db_call in db_calls:
        call_uuid = db_call["call_uuid"]
        
        # If call is in memory, use memory status (more up-to-date for active calls)
        if call_uuid in call_data_store:
            memory_data = call_data_store[call_uuid]
            calls_list.append({
                "call_uuid": call_uuid,
                "phone_number": db_call["phone_number"],
                "status": memory_data.get("status", db_call["status"]),
                "created_at": db_call["created_at"],
                "ended_at": memory_data.get("ended_at", db_call["ended_at"]),
                "customer_name": db_call["customer_name"] or "Unknown",
                "invoice_number": db_call["invoice_number"] or "N/A",
                "user_id": db_call["user_id"]
            })
        else:
            # Use database data for completed calls
            calls_list.append({
                "call_uuid": call_uuid,
                "phone_number": db_call["phone_number"],
                "status": db_call["status"],
                "created_at": db_call["created_at"],
                "ended_at": db_call["ended_at"],
                "customer_name": db_call["customer_name"] or "Unknown",
                "invoice_number": db_call["invoice_number"] or "N/A",
                "user_id": db_call["user_id"]
            })
    
    return {"calls": calls_list}


@app.get("/transcripts")
async def list_transcripts(user_id: int = None, current_user = Depends(get_current_user)):
    """
    List transcript files with metadata
    - Regular users: see only their own transcripts
    - Super admin: can see all transcripts or filter by user_id parameter
    """
    import re
    from datetime import datetime as dt
    
    try:
        # Determine which user's transcripts to show
        if current_user["role"] == "super_admin":
            if user_id is not None and user_id != 0:
                # Super admin viewing specific user's transcripts
                filter_user_ids = [user_id]
            elif user_id == 0:
                # user_id=0 means "all users" for super admin
                filter_user_ids = None  # Will scan all user folders
            else:
                # No user_id specified, show super admin's own transcripts
                filter_user_ids = [current_user["user_id"]]
        else:
            # Regular user can only see their own transcripts
            filter_user_ids = [current_user["user_id"]]
        
        transcripts = []
        transcripts_base_dir = Path("transcripts")
        
        # Check if directory exists
        if not transcripts_base_dir.exists():
            return {"transcripts": []}
        
        # Determine which user folders to scan
        if filter_user_ids is None:
            # Scan all user folders
            user_folders = [d for d in transcripts_base_dir.iterdir() if d.is_dir() and d.name.startswith("user_")]
        else:
            # Scan specific user folders
            user_folders = [transcripts_base_dir / f"user_{uid}" for uid in filter_user_ids if (transcripts_base_dir / f"user_{uid}").exists()]
        
        # Iterate through user folders and their transcript files
        for user_folder in user_folders:
            # Extract user_id from folder name (user_123 -> 123)
            try:
                folder_user_id = int(user_folder.name.replace("user_", ""))
            except:
                continue
            
            for transcript_file in user_folder.glob("*.txt"):
                try:
                    # Parse filename: invoicenumber_calluuid.txt
                    filename = transcript_file.name
                    parts = filename.replace(".txt", "").split("_", 1)
                    
                    # Get sanitized invoice number from filename (fallback)
                    invoice_number_from_filename = parts[0] if len(parts) > 0 else "unknown"
                    call_uuid = parts[1] if len(parts) > 1 else "unknown"
                    
                    # Read file to extract metadata
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Extract metadata from file
                    metadata = {
                        "filename": filename,
                        "invoice_number": invoice_number_from_filename,  # Will be overwritten if found in content
                        "call_uuid": call_uuid,
                        "file_size": transcript_file.stat().st_size,
                        "created_at": datetime.fromtimestamp(transcript_file.stat().st_ctime).isoformat(),
                        "modified_at": datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat(),
                        "user_id": folder_user_id  # Add user_id to metadata
                    }
                    
                    # Try to extract customer name from content
                    if "Customer Name:" in content:
                        start = content.index("Customer Name:") + len("Customer Name:")
                        end = content.index("\n", start)
                        metadata["customer_name"] = content[start:end].strip()
                    else:
                        metadata["customer_name"] = "N/A"
                    
                    # Try to extract ORIGINAL invoice number from content (with slashes intact)
                    if "Invoice Number:" in content:
                        start = content.index("Invoice Number:") + len("Invoice Number:")
                        end = content.index("\n", start)
                        metadata["invoice_number"] = content[start:end].strip()
                    
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
                                # Extract date from the CUT_OFF_DATE_PROVIDED line specifically
                                if "- CUT_OFF_DATE_PROVIDED:" in content:
                                    try:
                                        cutoff_line_start = content.index("- CUT_OFF_DATE_PROVIDED:")
                                        cutoff_line_end = content.index("\n", cutoff_line_start)
                                        cutoff_line = content[cutoff_line_start:cutoff_line_end]
                                        
                                        # Extract text after the colon
                                        date_text = cutoff_line.split(":", 1)[1].strip()
                                        
                                        # Use python-dateutil to parse the date
                                        from dateutil import parser as date_parser
                                        try:
                                            parsed_date = date_parser.parse(date_text, fuzzy=True)
                                            metadata["cut_off_date"] = parsed_date.strftime("%Y-%m-%d")
                                            logger.info(f"Extracted cutoff date from transcript {filename}: {metadata['cut_off_date']}")
                                        except Exception as e:
                                            logger.warning(f"Could not parse cutoff date from '{date_text}': {e}")
                                            metadata["cut_off_date"] = None
                                    except Exception as e:
                                        logger.warning(f"Error extracting cutoff date from transcript {filename}: {e}")
                                        metadata["cut_off_date"] = None
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
        transcripts_base_dir = Path("transcripts")
        
        # Search for the file in all user subdirectories
        transcript_file = None
        for user_folder in transcripts_base_dir.glob("user_*"):
            if user_folder.is_dir():
                potential_file = user_folder / filename
                if potential_file.exists():
                    transcript_file = potential_file
                    break
        
        if transcript_file is None:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Security check: ensure file is in transcripts directory
        if not transcript_file.resolve().is_relative_to(transcripts_base_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid filename")
        
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


# Serve React build files
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Mount static files from React build
frontend_build_path = os.path.join(os.path.dirname(__file__), "frontend", "build")
if os.path.exists(frontend_build_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_build_path, "static")), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        """Serve React app for all non-API routes"""
        # Skip API routes and backend endpoints
        if (full_path.startswith("api/") or 
            full_path.startswith("health") or 
            full_path.startswith("calls") or 
            full_path.startswith("transcripts") or 
            full_path.startswith("start") or 
            full_path.startswith("webhook") or
            full_path.startswith("audio/") or
            full_path.startswith("plivo_") or
            full_path.startswith("whatsapp/") or
            full_path.startswith("email/")):
            raise HTTPException(status_code=404)
        
        # Serve index.html for all other routes (React Router)
        index_path = os.path.join(frontend_build_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404)


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
