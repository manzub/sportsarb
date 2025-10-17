import json
import re
from datetime import datetime
from functools import wraps
from app.models import UserSubscriptions
from flask_login import current_user
from flask_mail import Message
from flask import flash, session, redirect, url_for
from app import mail

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.now() and (sub.end_date is None or sub.end_date >= datetime.now()))

def validate_email_address(email:str):
  pattern = re.compile(r"\"?([-a-zA-Z0-9.`?{}]+@\w+\.\w+)\"?")
  return re.match(pattern, email)

def verified_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if not current_user.is_verified:
      flash("Please verify your email before accessing this page.", "yellow")
      return redirect(url_for('main.verify_email', user_id=current_user.id))
    return f(*args, **kwargs)
  return decorated_function

def sort_surebet_data(data):
  results = []
  for arb in json.loads(data):
    arb_item = []
    team_names = str(arb['event']).split(' vs ')
    event = f"{team_names[0]} to Win"
    bookmakers = list(arb['bookmakers'].keys())
    for idx, item in enumerate(bookmakers):
      if idx > 0 and len(bookmakers) == 2:
        event = f"{team_names[1]} to Win"
      elif len(bookmakers) == 3:
        event = "Both teams to draw"
      x_item = {
        "surebet_id": arb['unique_id'],
        "profit": round(arb['profit_margin'], 2),
        "bookmaker": arb['bookmakers'][item],
        "start_time": arb['commence_time'],
        "event": event,
        "tournament": arb['sport_title'],
        "market": item,
        "market_type": arb['market'],
        "odds": arb['best_odds'][item]
      }
      arb_item.append(x_item)
    results.extend(arb_item)
  return results

def get_bookmaker_links(event, selected_bookmakers, market_key):
  links = {}
  for bookmaker in event.get("bookmakers", []):
    if bookmaker["title"] in selected_bookmakers:
      # Find matching market
      for market in bookmaker.get("markets", []):
        if market["key"] == market_key:
          links[bookmaker["title"]] = bookmaker.get("link", "")
  return links

def send_otp_mail(user):
  msg = Message("Your Verification Code", sender="noreply@surebets.com", recipients=[user.email])
  msg.body = f"Your OTP code is: {user.otp_code}. It expires in 10 minutes."
  mail.send(msg)
  
def send_email(to:str, subject:str, body:str):
  msg = Message(subject=subject, sender="noreply@surebets.com", recipients=[to])
  msg.body = body
  mail.send(msg)
  