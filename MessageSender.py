import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

# Load the JSON file
with open("product.json", "r") as file:
    cases = json.load(file)

litigation_phase = case["litigation_phase"]
type = None
name = case["client_name"]

if litigation_phase == "Discovery":
    type = "Deposition"
elif litigation_phase == "Settlement Discussion":
    type = "Mediation"
else:
    type = None


if type is not None:
    # Email details
    sender_email = "sender@mail.com" # Use your own gmail
    receiver_email = "reciever@mail.com" # add recipients by product later VERY IMPORTANT NEXT STEP
    password = "APP PASSWORD"  # Add your own APP Password 
    subject = f"{type} Request"
    body = f"Hello {name}, I hope this message finds you well. We are reaching out to schedule the {type} please let us know your availability so we can schedule this soon. Best regards, Donna"

    # Create email
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    # Send email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, password)
        server.send_message(message)
