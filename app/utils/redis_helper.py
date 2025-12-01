import json
from datetime import datetime, timedelta, timezone
from redis import Redis

redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)

def save_json(redis_key: str, new_items: list, expire_hours:int = 1):
  existing_raw = redis.get(redis_key)
  existing = json.loads(existing_raw) if existing_raw else {}

  for item in new_items:
    uid = item["unique_id"]
    existing[uid] = item

  redis.set(redis_key, json.dumps(existing), ex=timedelta(hours=expire_hours))
  print(f"[+] Updated {redis_key} ({len(new_items)} new items, total={len(existing)})")

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