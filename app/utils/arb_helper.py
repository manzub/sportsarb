import json
from app.extensions import redis
from datetime import datetime
from collections import defaultdict, Counter

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

def sort_valuebets_data(data):
  """Transforms raw valuebets JSON into frontend-friendly display list."""
  results = []
  
  for vb in json.loads(data):
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