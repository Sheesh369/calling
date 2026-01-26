import os
import re
import json
import asyncio
from datetime import datetime
from pathlib import Path
import pytz

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.frames.frames import Frame, TextFrame, BotStoppedSpeakingFrame, EndFrame, TTSSpeakFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from openai import OpenAI
import httpx
from dateutil import parser as date_parser

load_dotenv(override=True)


# Global variables
_last_detected_language = Language.EN
current_transcript_file = None


# Language detection functions
def detect_language(text: str) -> Language:
    """Detect language based on Unicode script ranges and return base Language enum"""
    global _last_detected_language
    
    if not text:
        return _last_detected_language
    
    # Remove whitespace, punctuation, numbers for detection
    text_for_detection = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', text)
    
    # If only punctuation/symbols remain, use last detected language
    if not text_for_detection:
        return _last_detected_language
    
    # Tamil: U+0B80–U+0BFF
    if re.search(r'[\u0B80-\u0BFF]', text_for_detection):
        _last_detected_language = Language.TA
        return Language.TA
    
    # Telugu: U+0C00–U+0C7F
    if re.search(r'[\u0C00-\u0C7F]', text_for_detection):
        _last_detected_language = Language.TE
        return Language.TE
    
    # Kannada: U+0C80–U+0CFF
    if re.search(r'[\u0C80-\u0CFF]', text_for_detection):
        _last_detected_language = Language.KN
        return Language.KN
    
    # Malayalam: U+0D00–U+0D7F
    if re.search(r'[\u0D00-\u0D7F]', text_for_detection):
        _last_detected_language = Language.ML
        return Language.ML
    
    # Hindi/Devanagari: U+0900–U+097F
    if re.search(r'[\u0900-\u097F]', text_for_detection):
        _last_detected_language = Language.HI
        return Language.HI
    
    # Default to English
    _last_detected_language = Language.EN
    return Language.EN


# Filter functions for each language
async def tamil_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.TA
    return True


async def english_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.EN
    return True


async def hindi_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.HI
    return True


async def telugu_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.TE
    return True


async def malayalam_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.ML
    return True


async def kannada_filter(frame: Frame) -> bool:
    if isinstance(frame, TextFrame):
        text_content = re.sub(r'[\s\d\.,!?;:\'"\-()]+', '', frame.text)
        if not text_content:
            return False
        return detect_language(frame.text) == Language.KN
    return True


# End-of-call detector processor
class EndCallDetector(FrameProcessor):
    """Detects end-of-call keywords and triggers call hang-up via Plivo API"""
    
    END_CALL_KEYWORDS = [
        "have a good day",
        "have a great day",
        "have a nice day",
        "have a wonderful day",
        "goodbye",
        "good bye",
        "bye",
        "take care",
        # Human agent escalation keywords
        "speak to a human",
        "talk to a human",
        "human agent",
        "speak to someone",
        "talk to someone",
        "real person",
        "speak to manager",
        "talk to manager",
        "supervisor",
        "connect me to",
        "transfer me to",
    ]
    
    def __init__(self, call_id: str = None):
        super().__init__()
        self.call_id = call_id
        self._hang_up_triggered = False
        self._goodbye_detected = False
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # Check if this is an assistant text frame and we haven't triggered hang-up yet
        if isinstance(frame, TextFrame) and not self._hang_up_triggered:
            text_lower = frame.text.lower()
            
            # Check if any end-call keyword is in the text
            for keyword in self.END_CALL_KEYWORDS:
                if keyword in text_lower:
                    logger.info(f"End-call keyword detected: '{keyword}' - Will hang up after message completes")
                    self._goodbye_detected = True
                    break
        
        # Check if bot stopped speaking after goodbye was detected
        if isinstance(frame, BotStoppedSpeakingFrame) and self._goodbye_detected and not self._hang_up_triggered:
            logger.info("Bot finished speaking goodbye message - Triggering call hang-up")
            self._hang_up_triggered = True
            # Schedule hang-up with a small delay to ensure audio is fully delivered
            asyncio.create_task(self._hang_up_call())
        
        await self.push_frame(frame, direction)
    
    async def _hang_up_call(self):
        """Hang up the call via Plivo API after a delay"""
        try:
            # Wait 3 seconds to ensure the audio is fully delivered to Plivo and played
            logger.info("Waiting 3 seconds before hanging up to ensure audio delivery...")
            await asyncio.sleep(3)
            
            if not self.call_id:
                logger.error("Cannot hang up call: call_id not provided")
                return
            
            auth_id = os.getenv("PLIVO_AUTH_ID")
            auth_token = os.getenv("PLIVO_AUTH_TOKEN")
            
            if not auth_id or not auth_token:
                logger.error("Cannot hang up call: Plivo credentials not found")
                return
            
            # Call Plivo API to hang up the call
            url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/{self.call_id}/"
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    url,
                    auth=(auth_id, auth_token),
                    timeout=10.0
                )
            
            if response.status_code == 204:
                logger.info(f"Successfully hung up call {self.call_id}")
            else:
                logger.warning(f"Plivo hang-up response: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error hanging up call: {e}")




async def generate_call_summary(transcript_file: str):
    """
    Generate AI summary using OpenAI and append to transcript file
    """
    try:
        logger.info(f"Generating summary for transcript: {transcript_file}")
        
        # Read the transcript file
        if not os.path.exists(transcript_file):
            logger.error(f"Transcript file not found: {transcript_file}")
            return
        
        with open(transcript_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract invoice date from metadata (for validation later)
        invoice_date = None
        if "Invoice Date:" in content:
            try:
                start = content.index("Invoice Date:") + len("Invoice Date:")
                end = content.index("\n", start)
                invoice_date = content[start:end].strip()
                logger.info(f"Extracted invoice date from transcript: {invoice_date}")
            except:
                pass
        
        # Extract conversation part (between CONVERSATION markers)
        conversation_start = content.find("CONVERSATION:")
        if conversation_start == -1:
            logger.warning(f"No conversation found in transcript: {transcript_file}")
            return
        
        # Extract ONLY the conversation content (USER/ASSISTANT messages)
        # Skip the metadata section to avoid sending customer PII to OpenAI
        conversation_section = content[conversation_start:]
        
        # Further extract only USER/ASSISTANT lines (no metadata)
        conversation_lines = []
        for line in conversation_section.split('\n'):
            # Only include lines that are actual conversation
            # Format: [timestamp] USER: text or [timestamp] ASSISTANT: text
            if 'USER:' in line or 'ASSISTANT:' in line:
                # Remove timestamp and keep only the speaker and message
                if '] USER:' in line:
                    conversation_lines.append('USER:' + line.split('] USER:')[1])
                elif '] ASSISTANT:' in line:
                    conversation_lines.append('ASSISTANT:' + line.split('] ASSISTANT:')[1])
        
        conversation_content = '\n'.join(conversation_lines)
        
        # PRE-VALIDATION: Check if conversation is meaningful (language-agnostic)
        # A meaningful conversation has either:
        # - At least 3 messages OR
        # - At least one message with 15+ characters
        is_meaningful = False
        if len(conversation_lines) >= 3:
            is_meaningful = True
        else:
            for line in conversation_lines:
                # Extract just the message content (after "USER:" or "ASSISTANT:")
                if 'USER:' in line:
                    message = line.split('USER:', 1)[1].strip()
                elif 'ASSISTANT:' in line:
                    message = line.split('ASSISTANT:', 1)[1].strip()
                else:
                    continue
                
                if len(message) >= 15:
                    is_meaningful = True
                    break
        
        # Check for actual USER/ASSISTANT conversation messages
        if len(conversation_lines) == 0:  # No actual conversation
            logger.warning(f"Empty conversation in transcript: {transcript_file}")
            summary_text = "**CALL OUTCOMES:**\n- FAILED\n\nNo conversation recorded - call failed or customer did not answer."
        elif not is_meaningful:
            # Not a meaningful conversation - skip AI processing
            logger.warning(f"Non-meaningful conversation in transcript: {transcript_file} (too short or no substantial messages)")
            summary_text = "**CALL OUTCOMES:**\n- NO_COMMITMENT\n\nConversation was too brief or did not contain meaningful dialogue."
        else:
            # Create enhanced prompt for OpenAI with call outcome classification
            prompt = f"""Analyze this customer service call about payment reminder.

CRITICAL INSTRUCTIONS:
- ONLY report what ACTUALLY happened in this conversation
- Do NOT make assumptions about what was said before or after
- If the customer did not explicitly commit to a payment date, mark as NO_COMMITMENT
- Be precise and factual

{conversation_content}

Determine ALL APPLICABLE CALL OUTCOMES (there may be multiple):
- CUT_OFF_DATE_PROVIDED: Customer committed to pay by a specific date
- INVOICE_DETAILS_NEEDED: Customer requested invoice copy/details/resend
- LEDGER_NEEDED: Customer requested ledger/statement/account details
- HUMAN_AGENT_NEEDED: Customer requested to speak with human agent/manager
- ALREADY_PAID: Customer claims payment was already made
- NO_COMMITMENT: Customer refused or didn't commit to payment

IMPORTANT: A call can have MULTIPLE outcomes. For example, a customer might request a ledger AND commit to a payment date.

Then provide your normal summary with these 5 points:
1. Whether the customer was reached and verified
2. Customer's response to the payment reminder
3. Any commitments or next steps discussed (if customer mentioned a date, that's the PAYMENT CUT-OFF DATE)
4. Overall outcome of the call
5. Language used in the conversation (if multiple languages, mention the switch)

Format your response EXACTLY like this:

**CALL OUTCOMES:**
- [outcome category 1]: [brief detail if applicable]
- [outcome category 2]: [brief detail if applicable]
(list all applicable outcomes)

1. **Customer Verified**: ...
2. **Customer Response**: ...
3. **Commitments and Next Steps**: ...
4. **Overall Outcome**: ...
5. **Language**: ...

Keep the summary brief and professional."""

            # Call OpenAI API
            client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary_text = response.choices[0].message.content
            logger.info(f"Summary generated successfully for {transcript_file}")
            
            # POST-AI VALIDATION: Ensure CUT_OFF_DATE_PROVIDED has a valid date
            if "CUT_OFF_DATE_PROVIDED" in summary_text:
                logger.info("Validating that CUT_OFF_DATE_PROVIDED has an extractable date...")
                
                # Try to extract date from CUT_OFF_DATE_PROVIDED line
                cutoff_date_found = False
                if "CUT_OFF_DATE_PROVIDED:" in summary_text or "- CUT_OFF_DATE_PROVIDED:" in summary_text:
                    try:
                        # Find the CUT_OFF_DATE_PROVIDED line
                        if "- CUT_OFF_DATE_PROVIDED:" in summary_text:
                            cutoff_line_start = summary_text.index("- CUT_OFF_DATE_PROVIDED:")
                        else:
                            cutoff_line_start = summary_text.index("CUT_OFF_DATE_PROVIDED:")
                        
                        cutoff_line_end = summary_text.index("\n", cutoff_line_start) if "\n" in summary_text[cutoff_line_start:] else len(summary_text)
                        cutoff_line = summary_text[cutoff_line_start:cutoff_line_end]
                        
                        # Extract text after the colon
                        if ":" in cutoff_line:
                            date_text = cutoff_line.split(":", 1)[1].strip()
                            
                            # Try to parse with python-dateutil
                            try:
                                parsed_date = date_parser.parse(date_text, fuzzy=True)
                                cutoff_date_found = True
                                logger.info(f"Successfully extracted cutoff date: {parsed_date.strftime('%Y-%m-%d')}")
                            except:
                                logger.warning(f"Could not parse date from: {date_text}")
                    except Exception as e:
                        logger.warning(f"Error extracting date from CUT_OFF_DATE_PROVIDED line: {e}")
                
                # If no valid date found, remove CUT_OFF_DATE_PROVIDED and add NO_COMMITMENT
                if not cutoff_date_found:
                    logger.warning("CUT_OFF_DATE_PROVIDED found but no valid date extracted. Correcting summary...")
                    
                    # Remove CUT_OFF_DATE_PROVIDED outcome
                    summary_lines = summary_text.split('\n')
                    corrected_lines = []
                    
                    for line in summary_lines:
                        if "CUT_OFF_DATE_PROVIDED" in line:
                            continue
                        corrected_lines.append(line)
                    
                    # Add NO_COMMITMENT if not already present
                    if "NO_COMMITMENT" not in summary_text:
                        # Find the CALL OUTCOMES section and add NO_COMMITMENT
                        for i, line in enumerate(corrected_lines):
                            if "**CALL OUTCOMES:**" in line:
                                corrected_lines.insert(i + 1, "- NO_COMMITMENT: No valid payment date could be extracted")
                                break
                    
                    summary_text = '\n'.join(corrected_lines)
                    logger.info("Summary corrected: CUT_OFF_DATE_PROVIDED removed, NO_COMMITMENT added")
            
            # VALIDATION: Check if cut-off date == invoice date
            if invoice_date and "CUT_OFF_DATE_PROVIDED" in summary_text:
                logger.info("Validating cut-off date against invoice date...")
                
                # Normalize invoice date using python-dateutil
                invoice_date_normalized = None
                try:
                    invoice_date_normalized = date_parser.parse(invoice_date, fuzzy=True).date()
                    logger.info(f"Parsed invoice date: {invoice_date_normalized}")
                except Exception as e:
                    logger.warning(f"Could not parse invoice date '{invoice_date}': {e}")
                
                # Extract cut-off date from summary (look in CUT_OFF_DATE_PROVIDED line)
                cutoff_date_normalized = None
                if "CUT_OFF_DATE_PROVIDED:" in summary_text or "- CUT_OFF_DATE_PROVIDED:" in summary_text:
                    try:
                        # Find the CUT_OFF_DATE_PROVIDED line
                        if "- CUT_OFF_DATE_PROVIDED:" in summary_text:
                            cutoff_line_start = summary_text.index("- CUT_OFF_DATE_PROVIDED:")
                        else:
                            cutoff_line_start = summary_text.index("CUT_OFF_DATE_PROVIDED:")
                        
                        cutoff_line_end = summary_text.index("\n", cutoff_line_start) if "\n" in summary_text[cutoff_line_start:] else len(summary_text)
                        cutoff_line = summary_text[cutoff_line_start:cutoff_line_end]
                        
                        # Extract text after the colon
                        if ":" in cutoff_line:
                            date_text = cutoff_line.split(":", 1)[1].strip()
                            
                            # Parse with python-dateutil
                            try:
                                cutoff_date_normalized = date_parser.parse(date_text, fuzzy=True).date()
                                logger.info(f"Parsed cutoff date: {cutoff_date_normalized}")
                            except Exception as e:
                                logger.warning(f"Could not parse cutoff date from '{date_text}': {e}")
                    except Exception as e:
                        logger.warning(f"Error extracting cutoff date: {e}")
                
                # Compare dates
                if invoice_date_normalized and cutoff_date_normalized:
                    logger.info(f"Invoice date: {invoice_date_normalized}, Cut-off date: {cutoff_date_normalized}")
                    
                    if invoice_date_normalized == cutoff_date_normalized:
                        logger.warning("Cut-off date matches invoice date! Correcting summary...")
                        
                        # Remove CUT_OFF_DATE_PROVIDED outcome
                        summary_lines = summary_text.split('\n')
                        corrected_lines = []
                        skip_next = False
                        
                        for line in summary_lines:
                            if "CUT_OFF_DATE_PROVIDED" in line:
                                skip_next = True
                                continue
                            if skip_next and line.strip().startswith('-'):
                                skip_next = False
                                continue
                            corrected_lines.append(line)
                        
                        # Add NO_COMMITMENT if not already present
                        if "NO_COMMITMENT" not in summary_text:
                            # Find the CALL OUTCOMES section and add NO_COMMITMENT
                            for i, line in enumerate(corrected_lines):
                                if "**CALL OUTCOMES:**" in line:
                                    corrected_lines.insert(i + 1, "- NO_COMMITMENT: Customer mentioned invoice date instead of commitment date")
                                    break
                        
                        summary_text = '\n'.join(corrected_lines)
                        logger.info("Summary corrected: CUT_OFF_DATE_PROVIDED removed, NO_COMMITMENT added")
        
        # Append summary to transcript file
        with open(transcript_file, "a", encoding="utf-8") as f:
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("=== CALL SUMMARY (Generated by AI) ===\n")
            f.write("=" * 70 + "\n\n")
            f.write(summary_text)
            f.write("\n\n" + "=" * 70 + "\n")
        
        logger.info(f"Summary appended to transcript: {transcript_file}")
        
    except Exception as e:
        logger.error(f"Error generating summary for {transcript_file}: {e}")
        # Append error message to transcript
        try:
            with open(transcript_file, "a", encoding="utf-8") as f:
                f.write("\n\n" + "=" * 70 + "\n")
                f.write("=== CALL SUMMARY (Generated by AI) ===\n")
                f.write("=" * 70 + "\n\n")
                f.write(f"Error generating summary: {str(e)}\n")
                f.write("\n" + "=" * 70 + "\n")
        except:
            pass


async def run_bot(transport: BaseTransport, handle_sigint: bool, custom_data: dict = None, call_uuid: str = None, call_data: dict = None):
    global current_transcript_file
    
    # Get user_id from custom_data (for organizing transcripts by user)
    user_id = custom_data.get("user_id", "unknown") if custom_data else "unknown"
    
    # Create user-specific transcripts directory
    transcripts_dir = Path(f"transcripts/user_{user_id}")
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get invoice number from custom data (fallback to "unknown" if not provided)
    invoice_number = custom_data.get("invoice_number", "unknown") if custom_data else "unknown"
    
    # Sanitize invoice number - replace invalid filename characters
    # Replace / \ : * ? " < > | with underscore to prevent directory creation
    safe_invoice_number = invoice_number.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    
    call_id = call_uuid or "unknown"
    
    # Create transcript filename: invoiceid_call_uuid.txt
    transcript_filename = transcripts_dir / f"{safe_invoice_number}_{call_id}.txt"
    current_transcript_file = str(transcript_filename)
    
    logger.info(f"Transcript will be saved to: {current_transcript_file}")
    
    # Get current date in India timezone (IST)
    india_tz = pytz.timezone('Asia/Kolkata')
    today = datetime.now(india_tz)
    today_str = today.strftime("%A, %B %d, %Y")  # e.g., "Monday, January 5, 2026"
    logger.info(f"Current date in India: {today_str}")
    
    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model="gemini-2.5-flash",
        params=GoogleLLMService.InputParams(
            temperature=0.7,
            max_tokens=4096
        )
    )

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="saarika:v2.5"
    )

    # Create TTS services for each language
    tamil_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.TA)
    )

    english_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.EN)
    )

    hindi_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.HI)
    )

    telugu_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.TE)
    )

    malayalam_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.ML)
    )

    kannada_tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        model="bulbul:v2",
        voice_id="abhilash",
        params=SarvamTTSService.InputParams(pace=0.9, language=Language.KN)
    )

    # Build system prompt (based on BOTO.py with new features added)
    system_content = (
        f"CURRENT DATE AND TIME: Today is {today_str} (India time).\n\n"
        "You are a friendly multilingual assistant Sara calling from Hummingbird to remind customers about pending payments. "
        "IMPORTANT: The greeting has already been delivered. Do NOT repeat 'Hello! This is Sara from Hummingbird' or any introduction. Start directly with verifying the customer or discussing the invoice. "
        "\n\n"
        "IMPORTANT LANGUAGE RULES: "
        "- Always start the conversation in English and continue in English. "
        "- ONLY change language if the user explicitly requests it (e.g., 'Can we speak in Tamil?', 'Tamil la pesunga', 'Hindi mein baat karte hain'). "
        "- Do NOT automatically detect or switch languages based on the user's response. "
        "- Once you switch to a requested language, speak ONLY in that language - do not mix languages. "
        "- If the user requests another language change, switch completely to that new language. "
        "Supported languages: English, Tamil, Hindi, Telugu, Malayalam, and Kannada. "
        "\n\n"
        "CRITICAL: When speaking Tamil, use everyday colloquial spoken Tamil (like how people talk in casual conversation), NOT formal literary Tamil. "
        "- Use simple, everyday words that people use in regular phone conversations "
        "- Speak like a friendly local person, not like reading from a book "
        "- Use casual phrases like 'pa', 'nga', 'la' naturally "
        "- Avoid heavy Sanskrit words or formal literary constructions "
        "- Think: How would someone from Chennai or Coimbatore speak on a casual business call? "
        "The same applies to other regional languages - always use colloquial, spoken form, not formal written form. "
        "\n\n"
        "CRITICAL FOR TEXT-TO-SPEECH (TTS): "
        "- ALWAYS write out ALL numbers as words (e.g., 'two thousand eight hundred' not '2,800') "
        "- For invoice numbers with letters, spell them out (e.g., '27EXT2425/7334' becomes 'two seven E X T two four two five slash seven three three four') "
        "- Write 'EXT' as 'E X T' (spell it out with spaces) so TTS pronounces each letter "
        "- For dates, say 'November fourteenth, two thousand twenty-four' not '14-11-2024' "
        "- For rupees, say 'rupees two thousand eight hundred' not '₹2,800' "
        "- Everything should sound natural when read aloud by a TTS system "
        "\n\n"
    )

    # Add custom data to system prompt if available
    if custom_data:
        logger.info(f"Custom data received for call (customer info redacted for security)")
        system_content += "CUSTOM CALL DATA:\n"
        system_content += json.dumps(custom_data, indent=2)
        system_content += "\n\nUse this custom data to personalize the conversation. Reference the customer name, invoice details, and amounts naturally during the call.\n\n"
        
        # Add greeting context if available (NEW FEATURE)
        greeting_text = custom_data.get("greeting_text", "")
        if greeting_text:
            system_content += (
                f"IMPORTANT - GREETING ALREADY PLAYED: \"{greeting_text}\"\n"
                f"Do NOT repeat this information. Start by verifying the customer or responding to their reaction.\n\n"
            )
    else:
        system_content += (
            "INVOICE DETAILS YOU ARE CALLING ABOUT: "
            "- Customer Name: TI Cycle of India "
            "- Invoice Number: 27EXT2425/7334 (say as: two seven E X T two four two five slash seven three three four) "
            "- Invoice Date: November 14, 2024 (say as: November fourteenth, two thousand twenty-four) "
            "- Invoice Status: OVERDUE "
            "- Subtotal: ₹2,500 (say as: rupees two thousand five hundred) "
            "- CGST: ₹150 (say as: rupees one hundred fifty) "
            "- SGST: ₹150 (say as: rupees one hundred fifty) "
            "- IGST: ₹0 (say as: zero) "
            "- Total Amount: ₹2,800 (say as: rupees two thousand eight hundred) "
            "- Outstanding Balance: ₹2,800 (say as: rupees two thousand eight hundred) "
            "\n\n"
        )

    system_content += (
        "CRITICAL CONFIRMATION RULES: "
        "- When customer gives a payment date, DO NOT ask for confirmation "
        "- Immediately respond: 'We'll expect the payment on [date]. Have a great day!' "
        "- NO reconfirmation questions like 'correct?' or 'is that right?' "
        "\n\n"
        "Your task: Ask when payment can be made. When they give a date, immediately say: 'We'll expect the payment on [date]. Have a great day!' and end the call. "
        "\n\n"
        "HUMAN AGENT ESCALATION: "
        "If the customer requests to speak with a human agent, manager, supervisor, or real person, respond with: "
        "'I understand. I'll have our team call you back shortly. Thanks, Have a great day.' "
        "Then the call will end automatically. "
        "\n\n"
        "Be brief and direct. Get the payment date and end the call. Stay in English unless explicitly asked to change. Never mix languages. Always write numbers as words for TTS."
    )

    messages = [
        {
            "role": "system",
            "content": system_content,
        },
    ]

    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    # Initialize transcript processor
    transcript = TranscriptProcessor()
    
    # Event handler to save transcript to file
    @transcript.event_handler("on_transcript_update")
    async def save_transcript(processor, frame):
        """Save transcript updates to file in real-time"""
        try:
            with open(current_transcript_file, "a", encoding="utf-8") as f:
                for message in frame.messages:
                    timestamp = message.timestamp or datetime.now().isoformat()
                    speaker = message.role.upper()
                    content = message.content
                    
                    # Write to file
                    f.write(f"[{timestamp}] {speaker}: {content}\n")
                    
                    # Also log to console
                    logger.info(f"{speaker}: {content}")
        except Exception as e:
            logger.error(f"Error saving transcript: {e}")

    # Get call_id for EndCallDetector from call_data parameter
    # Note: call_data is passed from bot() function
    call_id = call_data.get("call_id") if call_data else None

    # User idle detection handler
    async def handle_user_idle(processor, retry_count):
        """
        Handle user idle/silence during call
        - First timeout (retry_count=1): Prompt user "Are you still there?"
        - Second timeout (retry_count=2): End call gracefully with closing line
        """
        try:
            logger.info(f"User idle detected - retry count: {retry_count}")
            
            if retry_count == 1:
                # First timeout - prompt user
                logger.info("First idle timeout - prompting user")
                # Push LLM response frames to simulate assistant speaking
                await processor.push_frame(LLMFullResponseStartFrame())
                await processor.push_frame(TextFrame("Are you still there?"))
                await processor.push_frame(LLMFullResponseEndFrame())
                return True  # Continue monitoring
            else:
                # Second timeout - end call with closing line (triggers EndCallDetector)
                logger.info("Second idle timeout - ending call")
                # Push LLM response frames to simulate assistant speaking
                await processor.push_frame(LLMFullResponseStartFrame())
                await processor.push_frame(TextFrame("Thank you for your time. Have a great day."))
                await processor.push_frame(LLMFullResponseEndFrame())
                return False  # Stop monitoring
                
        except Exception as e:
            logger.error(f"Error in handle_user_idle: {e}")
            return False

    # Initialize UserIdleProcessor to detect silent/inactive users
    user_idle = UserIdleProcessor(
        callback=handle_user_idle,
        timeout=10.0  # 10 seconds of silence before prompting
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            transcript.user(),
            user_idle,  # Add user idle detection after user speech
            context_aggregator.user(),
            llm,
            ParallelPipeline(
                [FunctionFilter(tamil_filter), tamil_tts],
                [FunctionFilter(english_filter), english_tts],
                [FunctionFilter(hindi_filter), hindi_tts],
                [FunctionFilter(telugu_filter), telugu_tts],
                [FunctionFilter(malayalam_filter), malayalam_tts],
                [FunctionFilter(kannada_filter), kannada_tts],
            ),
            transport.output(),
            transcript.assistant(),
            EndCallDetector(call_id=call_id),  # Detect end-of-call keywords and trigger hang-up
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        """Handle client connection - create transcript file with header"""
        logger.info("Starting multilingual call conversation")
        logger.info("Supported languages: Tamil, English, Hindi, Telugu, Malayalam, Kannada")
        if custom_data:
            logger.info(f"Call initiated with custom data (customer info redacted for security)")
        if call_uuid:
            logger.info(f"Call UUID: {call_uuid}")
        
        try:
            # Create transcript file with header
            with open(current_transcript_file, "w", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write("=== MULTILINGUAL CALL TRANSCRIPT ===\n")
                f.write("=" * 70 + "\n\n")
                
                # Write call metadata
                f.write(f"Call UUID: {call_uuid or 'N/A'}\n")
                if custom_data:
                    f.write(f"Customer Name: {custom_data.get('customer_name', 'N/A')}\n")
                    f.write(f"Invoice Number: {custom_data.get('invoice_number', 'N/A')}\n")
                    f.write(f"Invoice Date: {custom_data.get('invoice_date', 'N/A')}\n")
                    f.write(f"Total Amount: {custom_data.get('total_amount', 'N/A')}\n")
                    f.write(f"Outstanding Balance: {custom_data.get('outstanding_balance', 'N/A')}\n")
                f.write(f"Started: {datetime.now().isoformat()}\n")
                
                f.write("\n" + "=" * 70 + "\n")
                f.write("CONVERSATION:\n")
                f.write("=" * 70 + "\n\n")
            
            logger.info("Transcript file created successfully")
        except Exception as e:
            logger.error(f"Error creating transcript file: {e}")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        """Handle client disconnection - finalize transcript and generate summary"""
        logger.info("Call ended")
        if call_uuid:
            logger.info(f"Call {call_uuid} disconnected - transcript saved")
        
        try:
            # Write footer to transcript file
            with open(current_transcript_file, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 70 + "\n")
                f.write(f"Ended: {datetime.now().isoformat()}\n")
                f.write(f"Status: Completed\n")
                f.write("=" * 70 + "\n")
            
            logger.info(f"Transcript finalized: {current_transcript_file}")
            
            # Generate summary using OpenAI
            await generate_call_summary(current_transcript_file)
            
        except Exception as e:
            logger.error(f"Error finalizing transcript: {e}")
        
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)

    await runner.run(task)


async def bot(runner_args):
    """Main bot entry point compatible with Pipecat Cloud."""

    # Extract custom data and call UUID from websocket state
    custom_data = getattr(runner_args.websocket.state, 'custom_data', {})
    call_uuid = getattr(runner_args.websocket.state, 'call_uuid', None)
    
    # Log what we received
    print(f"Bot received custom_data (customer info redacted for security)")
    print(f"Bot received call_uuid: {call_uuid}")
    logger.info(f"Bot received custom_data (customer info redacted for security)")
    logger.info(f"Bot received call_uuid: {call_uuid}")
    
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(f"Auto-detected transport: {transport_type}")

    serializer = PlivoFrameSerializer(
        stream_id=call_data["stream_id"],
        call_id=call_data["call_id"],
        auth_id=os.getenv("PLIVO_AUTH_ID", ""),
        auth_token=os.getenv("PLIVO_AUTH_TOKEN", ""),
        params=PlivoFrameSerializer.InputParams(auto_hang_up=True)
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=serializer,
        ),
    )

    handle_sigint = runner_args.handle_sigint

    # Pass custom data, call UUID, and call_data to run_bot
    await run_bot(transport, handle_sigint, custom_data=custom_data, call_uuid=call_uuid, call_data=call_data)
