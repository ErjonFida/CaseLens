import os
import smtplib
import logging
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger("email_service")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

def render_email_template(template_name: str, **context) -> str:
    
    template = jinja_env.get_template(template_name)
    return template.render(**context)

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = os.environ.get("SMTP_PORT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SENDER = os.environ.get("SMTP_SENDER")

def send_email(to_email: str, subject: str, html_content: str) -> bool:

    is_configured = all([SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_SENDER])
    is_placeholder = (
        SMTP_USERNAME == "email" or 
        SMTP_SENDER == "email@gmail.com" or 
        SMTP_PASSWORD == "password"
    )

    if not is_configured or is_placeholder:
        logger.warning("SMTP is not configured or uses placeholders. Logging email to console and local log file.")
        logger.info("--------------------------------------------------")
        logger.info(f"TO: {to_email}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"CONTENT:\n{html_content}")
        logger.info("--------------------------------------------------")
        
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

    subject = "Welcome to CaseLens"
    html_content = render_email_template("email/registration.html", email=to_email)
    return send_email(to_email, subject, html_content)

def send_unknown_device_login_email(to_email: str, ip: str, user_agent: str) -> bool:

    subject = "Security Alert: Login from Unknown Device"
    html_content = render_email_template(
        "email/unknown_device_login.html",
        ip=ip,
        user_agent=user_agent,
    )
    return send_email(to_email, subject, html_content)
