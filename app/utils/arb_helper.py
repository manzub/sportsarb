import json
from app.extensions import redis
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

def get_latest_data(key):
  raw = redis.get(f"arb:{key}")
  if not raw:
    return []
  try:
    data = json.loads(raw)
    if isinstance(data, list):
      return data
    elif isinstance(data, dict):
      return list(data.values())
  except Exception as e:
    print(f"Error decoding data for {key}: {e}")
  return []

# Profit/Bookmaker/Event/Odds
def sort_surebet_data(raw_data, cutoff = None):
  
  try:
    parsed = json.loads(raw_data)
  except Exception as e:
    print("Error decoding surebets:", e)
    return []
  
  if isinstance(parsed, dict):
    items = list(parsed.values())
  elif isinstance(parsed, list):
    items = parsed
  else:
    return []
  
  results = []
  for arb in items:
    # if cutoff, skip items
    if cutoff is not None and float(arb['profit_margin']) > cutoff:
      continue
    
    # Format date/time
    event_time = arb.get('commence_time')
    if event_time:
      try:
        event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
        date_str = event_time.strftime("%d/%m")
        time_str = event_time.strftime("%H:%M")
      except Exception:
        date_str, time_str = "N/A", "N/A"
    else:
      date_str, time_str = "N/A", "N/A"
      
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
        "date": date_str,
        "time": time_str,
        "commence_time": arb['commence_time'],
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

def sort_middle_data(raw_data):
  try:
    parsed = json.loads(raw_data)
  except Exception as e:
    print("Error decoding middles:", e)
    return []
  
  if isinstance(parsed, dict):
    items = list(parsed.values())
  elif isinstance(parsed, list):
    items = parsed
  else:
    return []
  
  results = []
  for middle in items:
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
        "sport_name": middle.get('sport_group', ''),
        "confidence": float(middle.get('confidence', 0.0)) * 100,
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

def sort_valuebets_data(raw_data):
  
  try:
    parsed = json.loads(raw_data)
  except Exception as e:
    print("Error decoding middles:", e)
    return []
  
  if isinstance(parsed, dict):
    items = list(parsed.values())
  elif isinstance(parsed, list):
    items = parsed
  else:
    return []
  
  results = []
  for vb in items:
    # --- Parse event time ---
    event_time = vb.get('commence_time')
    if event_time:
      try:
        dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
        date_str, time_str = dt.strftime("%d/%m"), dt.strftime("%H:%M")
      except Exception:
        date_str, time_str = "N/A", "N/A"
    else:
      date_str, time_str = "N/A", "N/A"
    
    # --- bet info ---
    bookmaker = vb.get('bookmaker')
    bookmaker_link = vb.get('bookmaker_link', '')
    team_or_outcome = vb.get('team_or_outcome')
    odds = vb.get('odds')
    ev = round(vb.get('expected_value', 0), 2)
    point = vb.get('point')

    # --- label ---
    event = vb.get('event', '')
    sport = vb.get('sport_title', '')
    market = vb.get('market', '')

    bet_label = f"{team_or_outcome} @ {odds}" if team_or_outcome else f"{market} @ {odds}"
    recommendation = f"Bet on {bet_label} with {bookmaker}"

    # --- Format record for frontend ---
    results.append({
      "valuebet_id": vb.get('unique_id'),
      "event": event,
      "sport": sport,
      "market": market,
      "bookmaker": bookmaker,
      "bookmaker_link": bookmaker_link,
      "date": date_str,
      "time": time_str,
      "start_time": vb.get('commence_time', ''),
      "odds": odds,
      "bet_recommendation": recommendation,
      "expected_value": ev,
      "confidence": vb.get('confidence', ''),
      "point": point,
      "type": "valuebet"
    })
  
  return results

def apply_filters(data, args):
  from app.utils.helpers import parse_datetime
  sort = args.get("sort")
  market = args.get("market", "")
  outcome_types = args.get("outcome_type", "")
  outcome_types = [x for x in outcome_types.split(",") if x]
  commence_time_filter = args.get("commence_time")

  # Time filtering
  if commence_time_filter:
    now = datetime.now(timezone.utc)
    time_map = {
      "4h": timedelta(hours=4),
      "8h": timedelta(hours=8),
      "12h": timedelta(hours=12),
      "2d": timedelta(days=2),
      "1w": timedelta(weeks=1)
    }
    if commence_time_filter in time_map:
      limit_time = now + time_map[commence_time_filter]
      data = [
        d for d in data
        if d.get("commence_time") 
        and parse_datetime(d["commence_time"]) <= limit_time
      ]

  # Market
  if market:
    data = [d for d in data if d.get("market_type") == market]

  # Sort
  if sort == "profit":
    data.sort(key=lambda x: x.get("profit", 0), reverse=True)
  elif sort == "time":
    data.sort(key=lambda x: x.get("commence_time", ""))

  # Outcome filter
  if outcome_types:
    filtered = []
    ids = {d["surebet_id"] for d in data}
    for sid in ids:
      count = count_bookmakers_by_surebet_id(data, sid)
      if ("2way" in outcome_types and count == 2) or \
        ("3way" in outcome_types and count == 3):
        filtered.extend([d for d in data if d["surebet_id"] == sid])
    data = filtered

  return data

def get_bookmaker_links(event, selected_bookmakers, market_key):
  links = {}
  for bookmaker in event.get("bookmakers", []):
    if bookmaker["title"] in selected_bookmakers:
      # Find matching market
      for market in bookmaker.get("markets", []):
        if market["key"] == market_key:
          links[bookmaker["title"]] = bookmaker.get("link", "")
  return links

def count_bookmakers_by_surebet_id(data, surebet_id):
  """Count how many bookmakers belong to a specific surebet_id."""
  return sum(1 for d in data if d.get("surebet_id") == surebet_id)