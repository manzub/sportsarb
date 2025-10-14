# tasks to save to redis here and run in celery
from app import create_app
from datetime import timedelta, datetime
from app.services.odds_service import OddsService
from app.services.arbitrage_service import calculate_arbitrage
from app.utils.redis_helper import save_json
from app.utils.logger import setup_logging

app = create_app()
celery = app.celery
logger = setup_logging()

@celery.task
def find_arbitrage():
  odds_api = OddsService()
  team_name_cache = {}
  all_arbs = []
  total_events, total_arbs = 0, 0
  
  sports = odds_api.get_sports()
  logger.info(f"Analyzing {len(sports)} sports...")
  
  for sport in sports:
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
  
celery.conf.beat_schedule = {
  'fetch-odds-every-5-minutes': {
    'task': 'app.tasks.find_arbitrage', # task here
    'schedule': timedelta(minutes=1),  # 5 minutes
  },
}