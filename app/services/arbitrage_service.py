import uuid
from datetime import datetime
from collections import defaultdict
from app.utils.redis_helper import save_json
from app.utils.helpers import get_bookmaker_links
from app.utils.logger import setup_logging

logger = setup_logging()

def find_surebets(markets, event, team_cache):
  """Find risk-free arbitrage opportunities for h2h markets."""
  surebets = []

  if not event.get('bookmakers'):
    return surebets

  best_odds = {}
  best_bookmakers = {}

  # For each outcome, find best odds
  for bookmaker in event['bookmakers']:
    for market in bookmaker.get('markets', []):
      if market['key'] not in ['h2h', 'spreads', 'totals']:
        continue

      for outcome in market.get('outcomes', []):
        name = outcome['name']
        price = outcome['price']

        if name not in best_odds or price > best_odds[name]:
          best_odds[name] = price
          best_bookmakers[name] = bookmaker['title']

  # If we have 2+ outcomes, check for arbitrage
  if len(best_odds) >= 2:
    implied_prob = sum(1 / odd for odd in best_odds.values())

    if implied_prob < 1:
      profit_margin = round((1 - implied_prob) * 100, 2)
      bookmakers = {k: best_bookmakers[k] for k in best_odds}

      surebets.append({
        'type': 'surebet',
        'event': f"{event['home_team']} vs {event['away_team']}",
        'profit_margin': profit_margin,
        'best_odds': best_odds,
        'bookmakers': bookmakers,
        'links': get_bookmaker_links(event, bookmakers.values(), 'h2h'),
        'commence_time': event.get('commence_time'),
        'market': 'h2h',
        'unique_id': str(uuid.uuid4()),
        'sport_title': event.get('sport_title')
      })

  return surebets

def find_middles(markets, event):
  """
  Finds 'middles' in spread or totals markets. when one book offers +X and another offers -Y with X < Y.
  """
  middles = []

  if not event.get('bookmakers'):
    return middles

  # --- Collect spreads ---
  spreads = defaultdict(lambda: {'home': None, 'away': None, 'bookmaker_home': '', 'bookmaker_away': ''})

  for bookmaker in event['bookmakers']:
    for market in bookmaker.get('markets', []):
      if market['key'] not in ['spreads', 'totals']:
        continue

      for outcome in market.get('outcomes', []):
        point = outcome.get('point')
        price = outcome.get('price')

        if point is None or price is None:
          continue

        if outcome['name'] == event['home_team']:
          spreads[bookmaker['title']]['home'] = point
          spreads[bookmaker['title']]['bookmaker_home'] = bookmaker['title']
        elif outcome['name'] == event['away_team']:
          spreads[bookmaker['title']]['away'] = point
          spreads[bookmaker['title']]['bookmaker_away'] = bookmaker['title']

  # --- Compare spreads across bookmakers ---
  bookmaker_names = list(spreads.keys())
  for i in range(len(bookmaker_names)):
    for j in range(i + 1, len(bookmaker_names)):
      b1, b2 = bookmaker_names[i], bookmaker_names[j]
      home1, away1 = spreads[b1]['home'], spreads[b1]['away']
      home2, away2 = spreads[b2]['home'], spreads[b2]['away']

      if home1 is not None and away2 is not None:
        # Middle exists if line overlap gives possible double win
        if home1 < away2:
          middles.append({
            'type': 'middle',
            'event': f"{event['home_team']} vs {event['away_team']}",
            'bookmakers': { 'bookmaker1': b1, 'bookmaker2': b2 },
            'links': get_bookmaker_links(event, [b1, b2], 'spreads'),
            'lines': { 'home_line': home1, 'away_line': away2 },
            'commence_time': event.get('commence_time'),
            'unique_id': str(uuid.uuid4()),
            'sport_title': event.get('sport_title'),
            'market': market['key'],
          })

  return middles

def find_valuebets(markets, event):
  """
  Valuebet occurs when bookmaker's odds imply a lower probability than the average market concensus
  very risky
  """  
  valuebets = []
  if not event.get('bookmakers'):
    return valuebets
  
  bookmaker_links = {}
  all_markets = ['h2h', 'spreads', 'totals']
  
  for market_type in all_markets:
    # --- Collect all odds for each outcome ---
    outcome_prices = defaultdict(list)  # e.g. {'Buffalo Sabres': [2.45, 2.40, 2.30]}
    outcome_metadata = defaultdict(dict)
    
    for bookmaker in event['bookmakers']:
      for market in bookmaker.get('markets', []):
        if market.get('key') != market_type:
          continue

        for outcome in market.get('outcomes', []):
          name = outcome.get('name')
          price = outcome.get('price')
          point = outcome.get('point')

          if not name or not price:
            continue

          outcome_key = name
          if market_type in ['spreads', 'totals'] and point is not None:
            outcome_key = f"{name}_{point}"  # distinguish Over_2.5, Under_3.5, etc.
            outcome_metadata[outcome_key]['point'] = point

          outcome_prices[outcome_key].append(price)
          bookmaker_links[bookmaker['title']] = bookmaker.get('link', 'N/A')
          
    # --- Compute average odds for each outcome ---
    market_avg = {}
    for outcome_key, prices in outcome_prices.items():
      if prices:
        market_avg[outcome_key] = sum(prices) / len(prices)
        
    # --- Detect value bets (odds > avg * (1 + threshold)) ---
    for bookmaker in event['bookmakers']:
      for market in bookmaker.get('markets', []):
        if market.get('key') != market_type:
          continue

        for outcome in market.get('outcomes', []):
          name = outcome.get('name')
          price = outcome.get('price')
          point = outcome.get('point')

          outcome_key = name
          if market_type in ['spreads', 'totals'] and point is not None:
            outcome_key = f"{name}_{point}"

          avg_price = market_avg.get(outcome_key)
          if not avg_price:
            continue
          
          # dynamic common thresholds
          thresholds = {'h2h': 0.03, 'spreads': 0.05, 'totals': 0.04}
          threshold = thresholds.get(market_type, 0.03)

          if price > avg_price * (1 + threshold):
            value_item = {
              'type': 'valuebet',
              'event': f"{event['home_team']} vs {event['away_team']}",
              'market': market_type,
              'team_or_outcome': name,
              'bookmaker': bookmaker['title'],
              'odds': price,
              'avg_market_odds': round(avg_price, 3),
              'advantage_percent': round((price / avg_price - 1) * 100, 2),
              'expected_value': round(((price * (1 / avg_price)) - 1) * 100, 2),
              'link': bookmaker.get('link', 'N/A'),
              'commence_time': event.get('commence_time'),
              'sport_title': event.get('sport_title'),
              'unique_id': str(uuid.uuid4())
            }

            # Add point if it's spreads or totals
            if point is not None:
              value_item['point'] = point

            valuebets.append(value_item)
            logger.info(f"[VALUEBET] {value_item['event']} | {name} @{price} ({market_type}) "
                          f"avg={avg_price:.2f}, edge={value_item['advantage_percent']}%")
            
  return valuebets


  
  

def calculate_arbitrage(markets, odds, team_cache):
  all_surebets, all_middles, all_valuebets = [], [], []

  for event in odds:
    surebets = find_surebets(markets, event, team_cache)
    if surebets:
      all_surebets.extend(surebets)

    middles = find_middles(markets, event)
    if middles:
      all_middles.extend(middles)
      
    valuebets = find_valuebets(markets, event)
    if middles:
      all_valuebets.extend(valuebets)

  # Save all results to Redis
  if all_surebets:
    save_json("surebets", all_surebets)
  if all_middles:
    save_json("middles", all_middles)
  if all_middles:
    save_json("valuebets", all_valuebets)

  logger.info(f"Calculated {len(all_surebets)} surebets and {len(all_middles)} middles and {len(all_valuebets)} valuebets.")
  return all_surebets + all_middles + all_valuebets
