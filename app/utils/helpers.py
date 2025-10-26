import json
import re
from datetime import datetime
from functools import wraps
from flask_login import current_user
from flask_mail import Message
from flask import flash, redirect, url_for
from app.extensions import redis, db
from app import mail

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.now() and (sub.end_date is None or sub.end_date >= datetime.now()))

def validate_email_address(email:str):
  pattern = re.compile(r"\"?([-a-zA-Z0-9.`?{}]+@\w+\.\w+)\"?")
  return re.match(pattern, email)

def check_valid_sports_leagues(user):
  from app.models import Sports
  
  valid_sports = [row for row in db.session.query(Sports.sport).filter(Sports.sport.in_(user.favorite_sports)).all()]
  valid_leagues = [row for row in db.session.query(Sports.league).filter(Sports.league.in_(user.favorite_leagues)).all()]
  if valid_leagues and valid_sports:
    result = list(set(valid_sports) & set(valid_leagues))
    return result
  return None

def save_sport_to_db(sport):
  from app.models import Sports
  
  existing = Sports.query.filter_by(league=sport['key']).first()
  if not existing:
    new_sport = Sports(sport=sport['group'], league=sport['key'])
    db.session.add(new_sport)
    db.session.commit()
    
  return sport

def verified_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if not current_user.is_verified:
      flash("Please verify your email before accessing this page.", "yellow")
      return redirect(url_for('main.verify_email', user_id=current_user.id))
    return f(*args, **kwargs)
  return decorated_function

def get_latest_data(key_prefix):
  keys = redis.keys(f"{key_prefix}:*")
  if not keys:
    return []
  latest_key = max(keys)
  raw_data = redis.get(latest_key)
  if not raw_data:
    return []
  try:
    data = json.loads(raw_data)
    if isinstance(data, list):
      return data
    elif isinstance(data, dict) and "items" in data:
      return data["items"]
  except Exception as e:
    print(f"Error decoding data for {key_prefix}: {e}")
  return []

# Profit/Bookmaker/Event/Odds
def sort_surebet_data(data):
  results = []
  for arb in json.loads(data):
    arb_item = []
    team_names = str(arb['event']).split(' vs ')
    bookmakers = list(arb['bookmakers'].keys())
    links = arb.get('links', {})
    
    for idx, bookmaker_key in enumerate(bookmakers):
      event_label = f"{team_names[0]} to Win"
      if idx == 1 or len(bookmakers) == 2:
        event_label = f"{team_names[1]} to Win"
      elif len(bookmakers) == 3 and idx == 2:
        event_label = "Both teams to Draw"
        
      bookmaker_name = arb['bookmakers'][bookmaker_key]
      bookmaker_link = links.get(bookmaker_name, "")
      
      x_item = {
        "surebet_id": arb['unique_id'],
        "profit": round(arb['profit_margin'], 2),
        "bookmaker": bookmaker_name,
        "bookmaker_link": bookmaker_link,
        "start_time": arb['commence_time'],
        "event": event_label,
        "tournament": arb['sport_title'],
        "sport_name": arb['sport_name'],
        "event_name": arb['event'],
        "market_type": arb['market'],
        "odds": arb['best_odds'][bookmaker_key],
        "type": "surebet"
      }
      arb_item.append(x_item)
    results.extend(arb_item)
  return results

def sort_middle_data(data):
  results = []
  for middle in json.loads(data):
    # Format date/time
    event_time = middle.get('commence_time')
    if event_time:
      try:
        event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
        date_str = event_time.strftime("%d/%m")
        time_str = event_time.strftime("%H:%M")
      except Exception:
        date_str, time_str = "N/A", "N/A"
    else:
      date_str, time_str = "N/A", "N/A"
    
    middle_item = []
    team_names = str(middle['event']).split(' vs ')
    bookmakers = list(middle['bookmakers'].values())
    links = middle.get('links', {})
    lines = middle.get('lines', {})  
    
    for idx, bookmaker_name in enumerate(bookmakers):
      # Default event label
      event_label = f"{team_names[0]} Line {lines.get('home_line', '')}"
      if idx == 1:
        event_label = f"{team_names[1]} Line {lines.get('away_line', '')}"

      bookmaker_link = links.get(bookmaker_name, "")
      x_item = {
        "middle_id": middle['unique_id'],
        "profit": round(middle.get('profit_margin', 0), 2),
        "bookmaker": bookmaker_name,
        "bookmaker_link": bookmaker_link,
        "event": event_label,
        "date": date_str,
        "time": time_str,
        "event_name": middle['event'],
        "tournament": middle.get('sport_title', ''),
        "market_type": middle.get('market', ''),
        "start_time": middle.get('commence_time', ''),
        "home_line": lines.get('home_line'),
        "away_line": lines.get('away_line'),
        "odds": middle.get('odds')['home_price'] if idx == 0 else middle.get('odds')['away_price'],
        "type": "middle"
      }

      middle_item.append(x_item)
    results.extend(middle_item)
  return results

def sort_valuebets_data(data):
  """Transforms valuebets JSON from Redis into frontend-ready list"""
  results = []
  for item in json.loads(data):
    # Format date/time
    event_time = item.get('commence_time')
    if event_time:
      try:
        event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
        date_str = event_time.strftime("%d/%m")
        time_str = event_time.strftime("%H:%M")
      except Exception:
        date_str, time_str = "N/A", "N/A"
    else:
      date_str, time_str = "N/A", "N/A"

    results.append({
      "valuebet_id": item.get('unique_id'),
      "bookmaker": item.get('bookmaker'),
      "bookmaker_link": item.get('bookmaker_link'),
      "event": item.get('event'),
      "sport": item.get('sport_title'),
      "date": date_str,
      "time": time_str,
      "market": item.get('market'),
      "team_or_outcome": item.get('team_or_outcome'),
      "odds": item.get('odds'),
      "probability": f"{item.get('implied_probability', 0)}%",
      "overvalue": f"+{item.get('overvalue_percent', 0)}%",
      "expected_value": item.get('overvalue_percent'),
      "point": item.get('point'),
      "type": "valuebet"
    })
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
  