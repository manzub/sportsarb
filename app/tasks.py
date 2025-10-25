# tasks to save to redis here and run in celery
from sqlalchemy import func
from app import create_app
from datetime import timedelta, datetime
from app.services.odds_service import OddsService
from app.services.arbitrage_service import calculate_arbitrage
from app.utils.redis_helper import save_json
from app.utils.logger import setup_logging

app = create_app()
celery = app.celery
logger = setup_logging()

@celery.task(name='app.tasks.find_arbitrage')
def find_arbitrage():
  odds_api = OddsService()
  team_name_cache = {}
  all_arbs = []
  total_events, total_arbs = 0, 0
  
  sports = odds_api.get_sports()
  logger.info(f"Analyzing {len(sports)} sports...")
  
  for sport in sports:
    if isinstance(sport, dict) and 'key' in sport:
      odds = odds_api.get_odds(sport['key'])
      if odds_api.api_limit_reached:
        logger.warning("API limit reached, stopping.")
        break
      total_events += len(odds)
      arbs = calculate_arbitrage(odds_api.markets, odds, team_name_cache)
      total_arbs += len(arbs)
      all_arbs.extend(arbs)
  
  save_json('summary', {
    "total_events": total_events,
    "total_arbitrage_opportunities": total_arbs,
    "api_usage": {
      "remaining_requests": odds_api.remaining_requests,
      "used_requests": odds_api.used_requests,
    },
  })
  
@celery.task(name='app.tasks.notify_users')
def notify_users():
  """Checks all users and sends notifications when their favorite sports/leagues get updated."""
  from app.models import User, Sports  # import inside to avoid circulars
  from app.utils.helpers import check_valid_sports_leagues, send_email
  from app.utils.webpush_helper import send_webpush
  
  
  all_users = User.query.all()
  if not all_users:
    return "No users found"
  
  for user in all_users:
    alerts = user.alert_settings
    if not alerts:
      continue

    # Ensure proper attributes exist
    fav_sports = user.favorite_sports or []
    fav_leagues = user.favorite_leagues or []
    if not fav_sports and not fav_leagues:
        continue

    # Filter valid sports/leagues (you already have this function)
    valid_sports = check_valid_sports_leagues(user)
    if not valid_sports:
        continue
    
    results = []
    for sport in valid_sports:
      updates = {
        "sport": sport.sport,
        "league": sport.league,
        "surebets": sport.surebets if sport.surebets > int(sport.last_count["surebets"]) else 0,
        "middles": sport.middles if sport.middles > int(sport.last_count["middles"]) else 0,
        "values": sport.values if sport.values > int(sport.last_count["values"]) else 0
      }
      if updates["surebets"] + updates["middles"] + updates["values"] > 0:
        results.append(updates)
    
    if not results:
      continue
    
    # Prepare message
    msg = "\n".join([
      f"Sport: {r['sport']} | League: {r['league']} "
      f"→ Surebets: {r['surebets']} | Middles: {r['middles']} | Values: {r['values']}"
      for r in results
    ])
    
    if alerts.email_notify:
      send_email(user.email, "Found Arbitrage Opportunities", msg)
      
    # === WEB PUSH NOTIFICATION ===
    if alerts.webpush_info:
      try:
        send_webpush(
          subscription_info=alerts.webpush_info,
          title="🎯 Arbitrage Alert",
          body=f"{len(results)} new updates found. Check dashboard for details."
        )
      except Exception as e:
        print(f"WebPush failed for {user.email}: {e}")
  return "Done"
  
celery.conf.beat_schedule = {
  'fetch-odds-every-5-minutes': {
    'task': 'app.tasks.find_arbitrage', # task here
    'schedule': timedelta(minutes=5),  # 5 minutes
  },
  'notify_users': {
    'task': 'app.tasks.notify_users',
    'schedule': timedelta(hours=1)
  }
}