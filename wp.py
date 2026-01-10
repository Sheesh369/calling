import requests
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Replace with your actual values
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERSION = os.getenv("WHATSAPP_VERSION", "v24.0")


def send_whatsapp_message(recipient: str, text: str):
    """Send WhatsApp text message to specific recipient
    
    Args:
        recipient: Phone number with country code (e.g., '919677343703')
        text: Message text to send
        
    Returns:
        Response object if successful
    """
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
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
        logger.info(f"Message sent successfully to {recipient}")
        logger.info(f"Response: {response.json()}")
        return response
    except requests.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise
    except requests.Timeout as e:
        logger.error(f"Timeout error: {e}")
        raise
    except requests.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        logger.error(f"Response: {response.text}")
        raise
    except requests.RequestException as e:
        logger.error(f"Request error: {e}")
        raise


def send_template_message(recipient: str, template_name: str = "hello_world"):
    """Send WhatsApp template message
    
    Args:
        recipient: Phone number with country code
        template_name: Name of approved template
    """
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en_US"}
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Template message sent to {recipient}")
        logger.info(f"Response: {response.json()}")
        return response
    except requests.RequestException as e:
        logger.error(f"Error sending template: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        raise


if __name__ == "__main__":
    # Example usage
    recipient_number = "919677343703"  # Replace with recipient's number
    
    # Send a text message (only works if you have a conversation open)
    try:
        send_whatsapp_message(recipient_number, "Hello! This is a test message from Python.")
    except Exception as e:
        print(f"Failed to send text message: {e}")
    
    # Send a template message (works to initiate conversation)
    try:
        send_template_message(recipient_number, "hello_world")
    except Exception as e:
        print(f"Failed to send template: {e}")