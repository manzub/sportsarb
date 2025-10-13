# tasks to save to redis here and run in celery
import os
import json
import logging
from app.odds_api import OddsAPI
from app.utils.arbitrage_finder import find_surebets
from redis import Redis
from datetime import timedelta, datetime
from app import create_app

app = create_app()
celery = app.celery
redis = Redis(host="localhost", port=6379,db=0, decode_responses=True)

def save_results(key_prefix, data, expire_hours=1):
  timestamp = datetime.now().strftime("%Y%m%d%H%M")
  key = f"{key_prefix}:{timestamp}"
  json_data = json.dumps(data)
  redis.set(key, json_data, ex=timedelta(hours=expire_hours))
  print(f"[+] Saved {key} to Redis ({len(json_data)} bytes)")
  return key

@celery.task
def find_arbitrage():
  setup_logging()
  odds_api = OddsAPI()
  team_name_cache = {}
  
  try:
    sports = odds_api.get_sports()
    if not sports:
      logging.error("Failed to fetch sports data")
      # return?
      return
    logging.info(f"Analysing {len(sports)} in-season sports...")
    
    total_events = 0
    total_arbs = 0
    all_arbs = []
    
    for sport in sports:
      try:
        odds = odds_api.get_odds(sport['key'])
        if odds_api.api_limit_reached:
          logging.warning("API limit reached. Stopping analysis.")
          break
        if odds:
          total_events += len(odds)
          arbs = calculate_arbitrage(markets=odds_api.markets, odds=odds) #calculate middles, surebets, values
          total_arbs += len(arbs)
          all_arbs.extend(arbs)
      except Exception as e:
        logging.error(f"Error processing sport {sport['key']}: {str(e)}")
        continue
    # save to redis
    save_results('summary', {
      "total_events": total_events,
      "total_arbitrage_opportunities": total_arbs,
      # "arbitrage_opportunities": all_arbs,
      "api_usage": {
          "remaining_requests": odds_api.remaining_requests,
          "used_requests": odds_api.used_requests
      }
    })
  except Exception as e:
    logging.error(f"Fatal error in find_arbitrage: {str(e)}")
    return #return empty list?

# TODO: calculate middles, values, surebets
def calculate_arbitrage(markets, odds):
  results = []
  all_surebets = []
  all_middles = []
  all_valuebets = []
  for event in odds:
    # extend and save surbets
    surebets = find_surebets(markets, event)
    if surebets:
      all_surebets.extend(surebets)
    
    # TODO: middles more
  save_results("surebets", all_surebets)
  
  results.extend(all_surebets)
  results.extend(all_middles)
  results.extend(all_valuebets)
  return results

def setup_logging():
  BASE_DIR = os.path.abspath(os.path.dirname(__file__))
  filename = os.path.join(BASE_DIR, '..', 'arbitrage_finder.log')
  logging.basicConfig(filename=filename, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

celery.conf.beat_schedule = {
  'fetch-odds-every-5-minutes': {
    'task': 'app.tasks.find_arbitrage', # task here
    'schedule': timedelta(minutes=1),  # 5 minutes
  },
}