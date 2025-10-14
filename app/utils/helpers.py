import json
import re
from datetime import datetime
from functools import wraps
from app.models import UserSubscriptions
from flask_login import current_user
from flask import flash, session

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.utcnow() and (sub.end_date is None or sub.end_date >= datetime.utcnow()))

def validate_email_address(email:str):
  pattern = re.compile(r"\"?([-a-zA-Z0-9.`?{}]+@\w+\.\w+)\"?")
  return re.match(pattern, email)

def check_active_plan(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    pending_plan_id = None

    if current_user.is_authenticated:
      user_plan = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
      if user_plan and not user_plan.active and user_plan.status == 'pending':
        flash('pending', 'yellow')
        pending_plan_id = user_plan.id
      session['has_active_plan'] = user_plan.active

    # Render the route function result
    response = fn(*args, **kwargs)

    # If response is a rendered template, inject the variable
    if isinstance(response, dict):
      response['pending_plan_id'] = pending_plan_id
      return response
    return response
  return wrapper

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
        "odds": arb['best_odds'][item]
      }
      arb_item.append(x_item)
    results.extend(arb_item)
  return results