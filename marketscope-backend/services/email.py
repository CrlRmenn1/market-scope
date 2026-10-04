"""Password-reset codes and the SMTP email that delivers them."""
import random
import smtplib
from email.message import EmailMessage

from core.config import (
    RESET_CODE_TTL_MINUTES,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


def generate_reset_code():
    return ''.join(random.choice('0123456789') for _ in range(6))


def is_smtp_configured():
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def send_password_reset_email(target_email: str, reset_code: str):
    if not is_smtp_configured():
        print(f"Password reset code for {target_email}: {reset_code}")
        return

    msg = EmailMessage()
    msg["Subject"] = f"{SMTP_FROM_NAME} Password Reset Code"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = target_email
    msg.set_content(
        f"Your MarketScope password reset code is: {reset_code}\n\n"
        f"This code expires in {RESET_CODE_TTL_MINUTES} minutes."
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(msg)
