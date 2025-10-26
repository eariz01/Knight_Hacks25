# MessageSender.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

PRODUCT_PATH = "product.json"

def main():
    # Load case data
    with open(PRODUCT_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Pull fields (with safe defaults)
    litigation_phase = str(data.get("litigation_phase", "")).strip()
    phase_norm = litigation_phase.casefold()
    client_name = data.get("client_name", "Client")
    receiver_email = data.get("client_email", "thegeeemanfl@gmail.com")  # fallback if missing

    # Determine event type based on original conditions
    event_type = None
    if phase_norm == "discovery":
        event_type = "Deposition"
    elif phase_norm == "settlement discussion":
        event_type = "Mediation"

    if not event_type:
        print(f"ℹ️ No email sent: litigation_phase='{litigation_phase}' does not meet conditions.")
        return

    # Email config — replace with your Gmail + App Password
    sender_email = "earistizabal102006@gmail.com"
    password = "dzst mdtm kmxv vvik"  # <- Paste your Gmail App Password (not your login)

    subject = f"{event_type} Request"
    body = (
        f"Hello {client_name},\n\n"
        f"We are reaching out to schedule your {event_type}. "
        f"Please let us know your availability.\n\n"
        f"Best regards,\nDonna"
    )

    # Create message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    # Send (SSL 465). If blocked, switch to STARTTLS 587 (see comment below).
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(sender_email, password)
            server.send_message(message)
        print(f"✅ Email sent to {receiver_email} ({event_type})")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

    # STARTTLS alternative:
    # with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
    #     server.ehlo()
    #     server.starttls()
    #     server.login(sender_email, password)
    #     server.send_message(message)

if __name__ == "__main__":
    main()
