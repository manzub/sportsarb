import json
from datetime import datetime, timedelta, timezone
from redis import Redis

redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)

def save_json(prefix, data, expire_hours=1):
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
  key = f"{prefix}:{timestamp}"
  redis.set(key, json.dumps(data), ex=timedelta(hours=expire_hours))
  print(f"[+] Saved {key} to Redis")
  return key

def save_odds_data(data, expire_hours=1):
  redis.set("odds:data", json.dumps(data), ex=timedelta(hours=expire_hours))
  redis.set("odds:latest", datetime.now(timezone.utc).isoformat())
  return "Done"

def get_cached_odds(sport):
  data = redis.get("odds:data")
  odds = json.loads(data) if data else {}
  return odds.get(sport)

def get_keys_by_prefix(prefix):
  return redis.keys(f"{prefix}:*")

def load_json(key):
  val = redis.get(key)
  return json.loads(val) if val else None