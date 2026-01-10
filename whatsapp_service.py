import os
import requests
from loguru import logger
from dotenv import load_dotenv

load_dotenv(override=True)

# WhatsApp Configuration from environment
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERSION = os.getenv("WHATSAPP_VERSION", "v24.0")


def send_whatsapp_message(recipient: str, text: str) -> dict:
    """
    Send WhatsApp text message to specific recipient
    
    Args:
        recipient: Phone number with country code (e.g., '919677343703')
        text: Message text to send
        
    Returns:
        dict: Response data with success status and message ID
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise ValueError("WhatsApp credentials not configured in .env file")
    
    url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": text},
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"WhatsApp message sent successfully to {recipient}")
        logger.info(f"Response: {result}")
        
        return {
            "success": True,
            "message_id": result.get("messages", [{}])[0].get("id"),
            "recipient": recipient,
            "response": result
        }
        
    except requests.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return {"success": False, "error": f"Connection error: {str(e)}"}
    
    except requests.Timeout as e:
        logger.error(f"Timeout error: {e}")
        return {"success": False, "error": f"Timeout error: {str(e)}"}
    
    except requests.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        logger.error(f"Response: {response.text}")
        return {"success": False, "error": f"HTTP error: {response.text}"}
    
    except requests.RequestException as e:
        logger.error(f"Request error: {e}")
        return {"success": False, "error": f"Request error: {str(e)}"}


def send_template_message(recipient: str, template_name: str, language_code: str = "en") -> dict:
    """
    Send WhatsApp template message
    
    Args:
        recipient: Phone number with country code
        template_name: Name of the approved template
        language_code: Language code (default: 'en')
        
    Returns:
        dict: Response data with success status
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise ValueError("WhatsApp credentials not configured in .env file")
    
    url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code}
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"WhatsApp template sent successfully to {recipient}")
        
        return {
            "success": True,
            "message_id": result.get("messages", [{}])[0].get("id"),
            "recipient": recipient,
            "template": template_name,
            "response": result
        }
        
    except Exception as e:
        logger.error(f"Error sending template: {e}")
        return {"success": False, "error": str(e)}


def format_payment_reminder_message(customer_data: dict) -> str:
    """
    Format a payment reminder message from customer data
    
    Args:
        customer_data: Dictionary with customer and invoice details
        
    Returns:
        str: Formatted message text
    """
    message = f"""Hello {customer_data.get('customer_name', 'Customer')}!

This is a friendly reminder from Hummingbird regarding your pending payment.

Invoice Details:
• Invoice Number: {customer_data.get('invoice_number', 'N/A')}
• Invoice Date: {customer_data.get('invoice_date', 'N/A')}
• Total Amount: {customer_data.get('total_amount', 'N/A')}
• Outstanding Balance: {customer_data.get('outstanding_balance', 'N/A')}

Please arrange for the payment at your earliest convenience. If you have any questions or concerns, feel free to reach out to us.

Thank you for your prompt attention to this matter!

Best regards,
Hummingbird Team"""
    
    return message