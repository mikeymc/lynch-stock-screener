import os
import resend
import logging

logger = logging.getLogger(__name__)

def send_verification_email(to_email: str, code: str) -> bool:
    """
    Send a verification email with the OTP code using Resend.
    
    Args:
        to_email: The recipient's email address.
        code: The 6-digit OTP code.
        
    Returns:
        bool: True if sent successfully, False otherwise.
    """
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key:
        logger.error("RESEND_API_KEY not set. Cannot send email.")
        return False
        
    resend.api_key = api_key
    
    html_content = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Verify your email</h2>
        <p>Thank you for signing up for papertree.ai</p>
        <p>Your verification code is:</p>
        <div style="background-color: #f4f4f5; padding: 12px; border-radius: 6px; text-align: center; margin: 20px 0;">
            <span style="font-size: 24px; font-weight: bold; letter-spacing: 5px; color: #18181b;">{code}</span>
        </div>
        <p>This code will expire in 15 minutes.</p>
        <p>If you didn't request this code, you can safely ignore this email.</p>
    </div>
    """
    
    try:
        r = resend.Emails.send({
            "from": "Papertree AI <info@papertree.ai>",
            "to": to_email,
            "subject": "Your Verification Code",
            "html": html_content
        })
        logger.info(f"Verification email sent to {to_email}. ID: {r.get('id')}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")
        return False
