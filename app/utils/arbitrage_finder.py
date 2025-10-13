import logging
from collections import defaultdict
import uuid
from difflib import get_close_matches
from datetime import datetime, timedelta, timezone

def find_surebets(markets: str, event):
  surebets_arbs = []
  # x -> market [h2h,totals,spreads]
  indv_market = markets.split(',')
  for x in indv_market:
    best_odds, bookmakers, bookmaker_links, points, market = get_best_odds(x, event)
    if best_odds:
      try:
        if x == 'h2h': # if h2h market
          implied_prob = sum(1 / odd for odd in best_odds.values())
        elif x == 'spreads':
          # Filter out the 'spread' key and verify bookmakers are different
          odds_without_spread = {k: v for k, v in best_odds.items() if k != 'spread'}
          teams = list(odds_without_spread.keys())
          if len(teams) == 2 and bookmakers[teams[0]] != bookmakers[teams[1]]:
              implied_prob = sum(1 / odd for odd in odds_without_spread.values())
          else:
              logging.warning("Invalid spread bet setup - skipping")
              continue
        elif x == 'totals':
          implied_prob = 1/best_odds['Over'] + 1/best_odds['Under']
        else:
          logging.warning(f"Unsupported market: {x}")
          continue
        
        logging.info(f"Event: {event['home_team']} vs {event['away_team']}, Implied Prob: {implied_prob}")
        
        if implied_prob < 1:
          profit_margin = (1 / implied_prob - 1) * 100
          logging.info(f"Potential arbitrage found! Profit Margin: {profit_margin}%")
          if profit_margin >= 0: #cutoff = minimum profit margin
            surebet_item = {
              'type': 'surebet',
              'event': event['home_team'] + ' vs ' + event['away_team'],
              'profit_margin': profit_margin,
              'best_odds': best_odds,
              'bookmakers': bookmakers,
              'links': bookmaker_links,
              'commence_time': event['commence_time'],
              'market': market,
              'unique_id': f"{uuid.uuid4()}",
              'sport_title': event['sport_title']
            }
            if points is not None:
              surebet_item['points'] = points
            surebets_arbs.append(surebet_item)
            logging.info(f"Added arbitrage opportunity with {profit_margin:.2f}% profit margin")
          else:
            logging.info(f"Profit margin {profit_margin}% below cutoff 0%")
        else:
          logging.info("No arbitrage opportunity")
      except Exception as e:
        logging.error(f"Error calculating arbitrage for event: {str(e)}")
        continue
    else:
      logging.info(f"No valid odds for {event['home_team']} vs {event['away_team']}")
  return surebets_arbs

def get_best_odds(market, event):
  if market == 'h2h':
    return get_best_odds_h2h(event)
  elif market == 'totals':
    return get_best_odds_totals(event)
  elif market == 'spreads':
    return get_best_odds_spreads(event)
  else:
    logging.warning(f"Unsupported market: {market}")
    return None, None, None, None
  
def get_best_odds_h2h(event):
  best_odds = {}
  bookmakers = {}
  links = {}
  if 'bookmakers' in event and isinstance(event['bookmakers'], list):
    for bookmaker in event['bookmakers']:
      if 'markets' in bookmaker and isinstance(bookmaker['markets'], list):
        for market in bookmaker['markets']:
          if market['key'] == 'h2h':
            for outcome in market['outcomes']:
              if outcome['name'] not in best_odds or outcome['price'] > best_odds[outcome['name']]:
                best_odds[outcome['name']] = outcome['price']
                bookmakers[outcome['name']] = bookmaker['title']
                links[bookmaker['title']] = bookmaker['link']
  return (best_odds, bookmakers, links, None, 'h2h') if len(best_odds) > 1 else (None, None, None, None)

def get_best_odds_totals(event):
  return (None, None, None, None, None)

def get_best_odds_spreads(event):
  return (None, None, None, None, None)