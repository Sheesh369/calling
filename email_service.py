import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger
from dotenv import load_dotenv

load_dotenv(override=True)

# Email Configuration from environment
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)
FROM_NAME = os.getenv("FROM_NAME", "Hummingbird")


def send_email(recipient: str, subject: str, body_html: str, body_text: str = None) -> dict:
    """
    Send email to recipient
    
    Args:
        recipient: Email address of recipient
        subject: Email subject
        body_html: HTML body of email
        body_text: Plain text body (optional, falls back to HTML)
        
    Returns:
        dict: Response with success status
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise ValueError("Email credentials not configured in .env file")
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        message["To"] = recipient
        
        # Add plain text part
        if body_text:
            part1 = MIMEText(body_text, "plain")
            message.attach(part1)
        
        # Add HTML part
        part2 = MIMEText(body_html, "html")
        message.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        
        logger.info(f"Email sent successfully to {recipient}")
        return {
            "success": True,
            "recipient": recipient,
            "subject": subject
        }
        
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def format_payment_reminder_email(customer_data: dict) -> tuple:
    """
    Format payment reminder email from customer data
    
    Args:
        customer_data: Dictionary with customer and invoice details
        
    Returns:
        tuple: (subject, html_body, text_body)
    """
    customer_name = customer_data.get('customer_name', 'Customer')
    invoice_number = customer_data.get('invoice_number', 'N/A')
    invoice_date = customer_data.get('invoice_date', 'N/A')
    total_amount = customer_data.get('total_amount', 'N/A')
    outstanding_balance = customer_data.get('outstanding_balance', 'N/A')
    
    subject = f"Payment Reminder - Invoice {invoice_number}"
    
    # Plain text version
    text_body = f"""Hello {customer_name},

This is a friendly reminder from Hummingbird regarding your pending payment.

Invoice Details:
• Invoice Number: {invoice_number}
• Invoice Date: {invoice_date}
• Total Amount: {total_amount}
• Outstanding Balance: {outstanding_balance}

Please arrange for the payment at your earliest convenience. If you have any questions or concerns, feel free to reach out to us.

Thank you for your prompt attention to this matter!

Best regards,
Hummingbird Team"""
    
    # HTML version
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #4CAF50;
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
            }}
            .invoice-details {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #4CAF50;
            }}
            .invoice-details p {{
                margin: 8px 0;
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                padding: 10px;
                color: #666;
                font-size: 0.9em;
            }}
            .highlight {{
                color: #4CAF50;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Payment Reminder</h2>
            </div>
            <div class="content">
                <p>Hello <strong>{customer_name}</strong>,</p>
                
                <p>This is a friendly reminder from <span class="highlight">Hummingbird</span> regarding your pending payment.</p>
                
                <div class="invoice-details">
                    <h3 style="margin-top: 0; color: #4CAF50;">Invoice Details</h3>
                    <p><strong>Invoice Number:</strong> {invoice_number}</p>
                    <p><strong>Invoice Date:</strong> {invoice_date}</p>
                    <p><strong>Total Amount:</strong> {total_amount}</p>
                    <p><strong>Outstanding Balance:</strong> <span style="color: #d32f2f; font-weight: bold;">{outstanding_balance}</span></p>
                </div>
                
                <p>Please arrange for the payment at your earliest convenience. If you have any questions or concerns, feel free to reach out to us.</p>
                
                <p>Thank you for your prompt attention to this matter!</p>
                
                <p>Best regards,<br>
                <strong>Hummingbird Team</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated payment reminder. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body, text_body