import re
from flask_mail import Message
from app.extensions import mail

def validate_email_address(email:str):
  pattern = re.compile(r"\"?([-a-zA-Z0-9.`?{}]+@\w+\.\w+)\"?")
  return re.match(pattern, email)

def send_otp_mail(user):
  msg = Message("Your Verification Code", sender="noreply@surebets.com", recipients=[user.email])
  msg.body = f"Your OTP code is: {user.otp_code}. It expires in 10 minutes."
  mail.send(msg)
  
def send_email(to:str, subject:str, body:str):
  msg = Message(subject=subject, sender="noreply@surebets.com", recipients=[to])
  msg.body = body
  mail.send(msg)