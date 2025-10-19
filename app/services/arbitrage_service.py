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
          spreads[bookmaker['title']]['home_price'] = price
          spreads[bookmaker['title']]['bookmaker_home'] = bookmaker['title']
        elif outcome['name'] == event['away_team']:
          spreads[bookmaker['title']]['away'] = point
          spreads[bookmaker['title']]['away_price'] = price
          spreads[bookmaker['title']]['bookmaker_away'] = bookmaker['title']

  # --- Compare spreads across bookmakers ---
  bookmaker_names = list(spreads.keys())
  for i in range(len(bookmaker_names)):
    for j in range(i + 1, len(bookmaker_names)):
      b1, b2 = bookmaker_names[i], bookmaker_names[j]
      s1, s2 = spreads[b1], spreads[b2]

      # Middle when one book's home line < another book's away line
      if s1['home'] is not None and s2['away'] is not None:
        if s1['home'] < s2['away']:
          middles.append({
            'type': 'middle',
            'event': f"{event['home_team']} vs {event['away_team']}",
            'bookmakers': {'bookmaker1': b1, 'bookmaker2': b2},
            'links': get_bookmaker_links(event, [b1, b2], 'spreads'),
            'lines': {
              'home_line': s1['home'],
              'away_line': s2['away']
            },
            'odds': {
              'home_price': s1['home_price'],
              'away_price': s2['away_price']
            },
            'commence_time': event.get('commence_time'),
            'unique_id': str(uuid.uuid4()),
            'sport_title': event.get('sport_title'),
            'market': 'spreads'
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

  all_market_types = ['h2h', 'spreads', 'totals']

  for market_type in all_market_types:
    # Collect odds across all bookmakers for this market type
    outcome_prices = defaultdict(list)
    outcome_meta = defaultdict(dict)

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

          key = name if market_type == 'h2h' else f"{name}_{point}"
          outcome_prices[key].append(price)
          outcome_meta[key] = {'point': point}

    # Average odds (market consensus)
    avg_odds = {k: sum(v) / len(v) for k, v in outcome_prices.items() if v}

    # Define threshold per market type (tolerance)
    thresholds = {'h2h': 0.03, 'spreads': 0.05, 'totals': 0.04}

    # Evaluate bookmakers vs average
    for bookmaker in event['bookmakers']:
      for market in bookmaker.get('markets', []):
        if market.get('key') != market_type:
          continue

        for outcome in market.get('outcomes', []):
          name = outcome.get('name')
          price = outcome.get('price')
          point = outcome.get('point')

          key = name if market_type == 'h2h' else f"{name}_{point}"
          avg_price = avg_odds.get(key)
          if not avg_price:
            continue

          threshold = thresholds.get(market_type, 0.03)

          if price > avg_price * (1 + threshold):
            implied_prob = round(1 / price * 100, 2)
            market_prob = round(1 / avg_price * 100, 2)
            overvalue = round(((price / avg_price) - 1) * 100, 2)

            value_item = {
              'type': 'valuebet',
              'event': f"{event['home_team']} vs {event['away_team']}",
              'sport_title': event.get('sport_title'),
              'commence_time': event.get('commence_time'),
              'bookmaker': bookmaker['title'],
              'market': market_type,
              'team_or_outcome': name,
              'odds': round(price, 3),
              'avg_market_odds': round(avg_price, 3),
              'implied_probability': implied_prob,
              'market_probability': market_prob,
              'overvalue_percent': overvalue,
              'point': point if point is not None else None,
              'bookmaker_link': bookmaker.get('link', ''),
              'unique_id': str(uuid.uuid4())
            }
            
            # Add point if it's spreads or totals
            if point is not None:
              value_item['point'] = point

            valuebets.append(value_item)
            logger.info(f"[VALUEBET] {value_item['event']} | {name} @{price} ({market_type}) "
                          f"avg={avg_price:.2f}, edge={value_item['avg_market_odds']}%")

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
