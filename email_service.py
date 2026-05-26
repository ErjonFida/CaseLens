import os
import smtplib
import html
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("email_service")

# SMTP credentials configuration
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SENDER = os.environ.get("SMTP_SENDER")

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Sends an email using configured SMTP settings.
    If credentials or server settings are not provided, it falls back
    to logging the email details locally and appending to db/emails.log.
    """
    # Check if SMTP details are configured and not placeholders
    is_configured = all([SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_SENDER])
    is_placeholder = (
        SMTP_USERNAME == "your_email@gmail.com" or 
        SMTP_SENDER == "your_email@gmail.com" or 
        SMTP_PASSWORD == "your_app_password"
    )

    if not is_configured or is_placeholder:
        # Fallback to local logs and database email log file
        logger.warning("SMTP is not configured or uses placeholders. Logging email to console and local log file.")
        logger.info("--------------------------------------------------")
        logger.info(f"TO: {to_email}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"CONTENT:\n{html_content}")
        logger.info("--------------------------------------------------")
        
        # Save to local file under db/emails.log for testing validation
        try:
            os.makedirs("./db", exist_ok=True)
            log_path = "./db/emails.log"
            # Rotate log if it exceeds 10MB
            if os.path.exists(log_path) and os.path.getsize(log_path) > 10 * 1024 * 1024:
                rotated = log_path + ".old"
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(log_path, rotated)
                logger.info("Rotated email log file (exceeded 10MB).")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"=== EMAIL ===\nTO: {to_email}\nSUBJECT: {subject}\nCONTENT:\n{html_content}\n=============\n\n")
        except Exception as e:
            logger.error(f"Failed to write mock email log: {e}")
        return True

    # Setup MIME email
    msg = MIMEMultipart()
    msg['From'] = SMTP_SENDER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        port = int(SMTP_PORT)
        if port == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, port)
        else:
            server = smtplib.SMTP(SMTP_HOST, port)
            server.starttls()
            
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_SENDER, to_email, msg.as_string())
        server.quit()
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_registration_email(to_email: str) -> bool:
    """Sends a welcoming email upon successful registration."""
    subject = "Welcome to Legal Assistant AI!"
    safe_email = html.escape(to_email)
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #0d0f12; color: #e2e8f0; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #60a5fa; margin-top: 0;">Account Registered</h2>
                <p>Welcome to your AI-powered Legal Assistant! Your account associated with <strong>{safe_email}</strong> has been successfully registered.</p>
                <p>You can now log in, upload legal files (bills, transcripts, contracts), and perform isolated semantic searches on them.</p>
                <br>
                <p style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 15px;">This is an automated system email.</p>
            </div>
        </body>
    </html>
    """
    return send_email(to_email, subject, html_content)

def send_unknown_device_login_email(to_email: str, ip: str, user_agent: str) -> bool:
    """Sends a security alert notification when login is detected from an unrecognized device."""
    subject = "Security Alert: Login from Unknown Device"
    safe_ip = html.escape(ip)
    safe_ua = html.escape(user_agent)
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #0d0f12; color: #e2e8f0; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #ef4444; margin-top: 0;">New Login Detected</h2>
                <p>We noticed a login to your Legal Assistant account from a device we don't recognize:</p>
                <table style="width: 100%; margin-top: 15px; margin-bottom: 15px; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; font-weight: bold; width: 120px; color: #94a3b8; border-bottom: 1px solid rgba(255,255,255,0.05);">IP Address:</td>
                        <td style="padding: 8px; color: #e2e8f0; border-bottom: 1px solid rgba(255,255,255,0.05);">{safe_ip}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; color: #94a3b8;">User Agent:</td>
                        <td style="padding: 8px; color: #e2e8f0; font-size: 13px;">{safe_ua}</td>
                    </tr>
                </table>
                <p>If this was you, you can safely ignore this email. If you did not log in, please secure your credentials immediately.</p>
                <br>
                <p style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 15px;">This is an automated system security email.</p>
            </div>
        </body>
    </html>
    """
    return send_email(to_email, subject, html_content)
