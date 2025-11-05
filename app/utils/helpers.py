from datetime import datetime, timezone
from functools import wraps
from flask_login import current_user
from flask import flash, redirect, url_for, has_app_context, current_app
from app.extensions import db

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.now(timezone.utc) and (sub.end_date is None or sub.end_date >= datetime.now(timezone.utc)))

def check_valid_sports_leagues(user):
  from app.models import Sports
  
  fav_sports = user.favorite_sports or []
  fav_leagues = user.favorite_leagues or []
  if not fav_sports or not fav_leagues:
    return []
  
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

def update_sport_db_count(key: str, **counts):
  from app.models import Sports
  from app.utils.logger import setup_logging
  
  logger = setup_logging()
  
  def _update():
    sport = Sports.query.filter_by(league=key).first()
    if not sport:
      logger.warning(f"No sport found with league '{key}'")
      return False

    sport.last_count = {
      'surebets': sport.surebets,
      'middles': sport.middles,
      'values': sport.values
    }

    for field in ['surebets', 'middles', 'values']:
      if field in counts and counts[field] is not None:
        setattr(sport, field, counts[field])

    db.session.commit()
    return True

  if has_app_context():
    return _update()
  else:
    app = current_app._get_current_object()
    with app.app_context():
      return _update()

def verified_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if current_user.is_authenticated and not getattr(current_user, "is_verified", False):
      flash("Please verify your email before accessing this page.", "yellow")
      return redirect(url_for("main.verify_email", user_id=current_user.id))
    return f(*args, **kwargs)
  return decorated_function

def convert_amount(amount_usd, target_currency):
  exchange_rates = get_exchange_rates()
  rate = exchange_rates.get(target_currency, 1)
  return round(amount_usd * rate, 2)

def db_get_bookmaker_regions():
  from app.models import AppSettings
  app_settings = AppSettings.query.filter_by(setting_name='bookmaker_regions').first()
  if app_settings:
    bookmaker_regions = app_settings.value or 'uk'
    return bookmaker_regions
  return 'uk'

def get_exchange_rates():
  from app.models import AppSettings
  import json
  try:
    currency_settings = AppSettings.query.filter_by(setting_name='exchange_rates').first()
    if currency_settings:
      exchange_rates = json.loads(currency_settings.value)
      return exchange_rates
  except Exception as e:
    print("Error fetching exchange rates:", e)
    return {} 

def parse_datetime(date_str):
  """
  Converts ISO, timestamp, or common datetime formats safely to a datetime object.
  """
  try:
    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
  except Exception:
    try:
      return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
      return datetime.utcnow()  # fallback
  