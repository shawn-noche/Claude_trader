"""alerts/email_alert.py — Send briefings via SMTP email.

Uses Python's built-in smtplib. Works with Gmail (App Passwords) and
most SMTP providers. Gracefully degrades if credentials are not set.

Setup for Gmail:
  1. Enable 2FA on your Google account
  2. Go to Google Account -> Security -> App Passwords
  3. Create an app password and add it to .env as EMAIL_PASSWORD
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional

from config import (
    EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
    EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_RECIPIENT,
)

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(EMAIL_USERNAME and EMAIL_PASSWORD and EMAIL_RECIPIENT)


def send_email(subject: str, plain_text: str, html_body: Optional[str] = None) -> bool:
    if not _is_configured():
        logger.info("Email not configured - skipping email send.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USERNAME
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(plain_text, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USERNAME, EMAIL_RECIPIENT, msg.as_string())
        logger.info("Email sent to %s: %s", EMAIL_RECIPIENT, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Email authentication failed. Check EMAIL_USERNAME and EMAIL_PASSWORD in .env")
        return False
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False


def send_morning_briefing(plain_text: str) -> bool:
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    subject = f"Turtle Trader Briefing - {date_str}"
    html_body = _plain_to_html(plain_text)
    return send_email(subject, plain_text, html_body)


def send_urgent_alert(ticker: str, alert_type: str, message: str) -> bool:
    subjects = {
        "stop_loss": f"STOP-LOSS HIT - {ticker}",
        "system2_entry": f"System 2 Signal - {ticker}",
        "time_exit": f"Time Exit Warning - {ticker}",
    }
    subject = subjects.get(alert_type, f"Turtle Alert - {ticker}")
    html = f"<html><body><pre>{message}</pre></body></html>"
    return send_email(subject, message, html)


def _plain_to_html(text: str) -> str:
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        if line.startswith(("=", "-")):
            html_lines.append('<hr style="border: 1px solid #333;">')
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f'<p style="margin: 2px 0;">{line}</p>')
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #222; background: #f9f9f9; padding: 20px; }}
            .container {{ max-width: 700px; margin: auto; background: white;
                          padding: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            h2 {{ color: #1a1a2e; }}
            hr {{ margin: 12px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Turtle Trader - Daily Briefing</h2>
            {chr(10).join(html_lines)}
        </div>
    </body>
    </html>
    """
