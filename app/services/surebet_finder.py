import uuid
from collections import defaultdict
from difflib import get_close_matches
from app.utils.redis_helper import save_json, get_cached_odds
from app.utils.arb_helper import get_bookmaker_links
from app.utils.helpers import update_sport_db_count
from app.utils.logger import setup_logging

logger = setup_logging()

# find arbitrage function takes sports, get odds using specific parameters
# find best_odds
class SurebetFinder:
  def __init__(self):
    self.cutoff = 1
    self.team_name_cache = {}
    self.markets = None
    
  def find_arbitrage(self, sports, markets):
    try:
      if not sports:
        logger.error("Failed to fetch sports data")
        return
      logger.info(f"Analyzing {len(sports)} in-season sports...")
      
      all_arbs = []
      self.markets = markets.split(',') if markets else ['h2h']
      for sport in sports:
        try:
          odds = get_cached_odds(sport['key'])
          if odds:
            arbs = self.calculate_arbitrage(odds, sport['group']) # calculate arbs
            all_arbs.extend(arbs)
            update_sport_db_count(key=sport['key'], surebets=len(all_arbs)) #update db counts
        except Exception as e:
          logger.error(f"Surebet - Error processing sport {sport['key']}: {str(e)}")
          continue
      save_json('surebets', all_arbs) # save to redis here
    except Exception as e:
      logger.error(f"Fatal error in find_arbitrage: {str(e)}")
      
  def calculate_arbitrage(self, odds, sport_group):
    arbs = []
    for market in self.markets:
      for event in odds:
        best_odds, bookmakers, points = self.get_best_odds(event, market)
        if best_odds:
          try:
            if market == 'h2h':
              implied_prob = sum(1 / odd for odd in best_odds.values())
            elif market == 'spreads':
              # Filter out the 'spread' key and verify bookmakers are different
              odds_without_spread = {k: v for k, v in best_odds.items() if k != 'spread'}
              teams = list(odds_without_spread.keys())
              if len(teams) == 2 and bookmakers[teams[0]] != bookmakers[teams[1]]:
                implied_prob = sum(1 / odd for odd in odds_without_spread.values())
              else:
                logger.warning("Invalid spread bet setup - skipping")
                continue
            elif market == 'totals':
              implied_prob = 1/best_odds['Over'] + 1/best_odds['Under']
            else:
              logger.warning(f"Unsupported market: {market}")
              continue
            
            logger.info(f"Event: {event['home_team']} vs {event['away_team']}, Implied Prob: {implied_prob}")
            
            if implied_prob < 1:
              profit_margin = (1 / implied_prob - 1) * 100
              logger.info(f"Potential arbitrage found! Profit Margin: {profit_margin}%")
              
              if profit_margin >= self.cutoff:
                arb = {
                  'type': 'surebet',
                  'event': f"{event['home_team']} vs {event['away_team']}",
                  'profit_margin': profit_margin,
                  'best_odds': best_odds,
                  'bookmakers': bookmakers,
                  'links': get_bookmaker_links(event, bookmakers.values(), market),
                  'commence_time': event.get('commence_time'),
                  'sport_name': sport_group,
                  'market': market,
                  'unique_id': str(uuid.uuid4()),
                  'sport_title': event.get('sport_title')
                }
                if points is not None:
                  arb['points'] = points
                arbs.append(arb)
                logger.info(f"Added arbitrage opportunity with {profit_margin:.2f}% profit margin")
              else:
                logger.info(f"Profit margin {profit_margin}% below cutoff {self.cutoff}%")
            else:
              logger.info("No arbitrage opportunity")
          except Exception as e:
            logger.error(f"Error calculating arbitrage for event: {str(e)}")
            continue
        else:
          logger.info(f"No valid odds for {event['home_team']} vs {event['away_team']}")
      # end market for
    return arbs
    
  
  def get_best_odds(self, event, market_key):
    if market_key == 'h2h':
      return self.get_best_odds_h2h(event)
    elif market_key == 'totals':
      return self.get_best_odds_totals(event)
    elif market_key == 'spreads':
      return self.get_best_odds_spreads(event)
    else:
      logger.warning(f"Unsupported market: {market_key}")
      return None, None, None
  
  def get_best_odds_h2h(self, event):
    best_odds = {}
    bookmakers = {}
    if 'bookmakers' in event and isinstance(event['bookmakers'], list):
      for bookmaker in event['bookmakers']:
        if 'markets' in bookmaker and isinstance(bookmaker['markets'], list):
          for market in bookmaker['markets']:
            if market['key'] == 'h2h':
              for outcome in market['outcomes']:
                if outcome['name'] not in best_odds or outcome['price'] > best_odds[outcome['name']]:
                  best_odds[outcome['name']] = outcome['price']
                  bookmakers[outcome['name']] = bookmaker['title']
    return (best_odds, bookmakers, None) if len(best_odds) > 1 else (None, None, None)
  
  def get_best_odds_totals(self, event):
    odds_by_points = defaultdict(lambda: {'Over': 0, 'Under': 0})
    bookmakers_by_points = defaultdict(lambda: {'Over': '', 'Under': ''})
    
    if 'bookmakers' in event and isinstance(event['bookmakers'], list):
      for bookmaker in event['bookmakers']:
        if 'markets' in bookmaker and isinstance(bookmaker['markets'], list):
          for market in bookmaker['markets']:
            if market['key'] == 'totals':
              for outcome in market['outcomes']:
                total_points = outcome.get('point')
                if total_points is not None:
                  if outcome['name'] == 'Over' and outcome['price'] > odds_by_points[total_points]['Over']:
                    odds_by_points[total_points]['Over'] = outcome['price']
                    bookmakers_by_points[total_points]['Over'] = bookmaker['title']
                  elif outcome['name'] == 'Under' and outcome['price'] > odds_by_points[total_points]['Under']:
                    odds_by_points[total_points]['Under'] = outcome['price']
                    bookmakers_by_points[total_points]['Under'] = bookmaker['title']
    
    best_odds = None
    best_bookmakers = None
    best_total_points = None
    best_implied_prob = float('inf')

    for total_points, odds in odds_by_points.items():
      if odds['Over'] > 0 and odds['Under'] > 0:
        implied_prob = 1/odds['Over'] + 1/odds['Under']
        if implied_prob < best_implied_prob:
          best_implied_prob = implied_prob
          best_odds = odds.copy()  # Create a copy to avoid modifying the original
          best_bookmakers = bookmakers_by_points[total_points]
          best_total_points = total_points

    if best_odds:
      return best_odds, best_bookmakers, best_total_points
    else:
      return None, None, None
  
  def standardize_team_name(self, team_name, event_teams):
    """
    Standardize team names using fuzzy matching.
    Cache results to improve performance.
    """
    if not team_name:
      return None
        
    cache_key = (team_name.lower(), tuple(sorted(event_teams)))
    if cache_key in self.team_name_cache:
      return self.team_name_cache[cache_key]

    matches = get_close_matches(team_name.lower(), [t.lower() for t in event_teams], n=1, cutoff=0.6)
    if matches:
      standardized = next(t for t in event_teams if t.lower() == matches[0])
      self.team_name_cache[cache_key] = standardized
      return standardized
    
    logger.warning(f"No match found for team name: {team_name}")
    return None
  
  def get_best_odds_spreads(self, event):
    event_teams = [event['home_team'], event['away_team']]
    odds_by_points = defaultdict(lambda: {
      'Home': {'odds': 0, 'team': None, 'bookmaker': None, 'point': None},
      'Away': {'odds': 0, 'team': None, 'bookmaker': None, 'point': None}
    })
    
    if 'bookmakers' in event and isinstance(event['bookmakers'], list):
      for bookmaker in event['bookmakers']:
        if 'markets' in bookmaker and isinstance(bookmaker['markets'], list):
          for market in bookmaker['markets']:
            if market['key'] == 'spreads':
              for outcome in market['outcomes']:
                point = outcome.get('point')
                if point is not None:
                  try:
                    point = float(point)
                  except (ValueError, TypeError):
                    continue

                  # Standardize team name
                  team_name = self.standardize_team_name(outcome['name'], event_teams)
                  if not team_name:
                    continue

                  # Determine if team is home or away
                  side = 'Home' if team_name == event['home_team'] else 'Away'

                  # Store odds if better than existing
                  if outcome['price'] > odds_by_points[point][side]['odds']:
                    odds_by_points[point][side] = {
                      'odds': outcome['price'],
                      'team': team_name,
                      'bookmaker': bookmaker['title'],
                      'point': point
                    }

    # Find the best arbitrage opportunity across all point spreads
    best_odds = None
    best_bookmakers = None
    best_points = None
    best_implied_prob = float('inf')

    for point, sides in odds_by_points.items():
      # Verify both sides exist and are from different bookmakers
      if (sides['Home']['odds'] > 0 and sides['Away']['odds'] > 0 and
          sides['Home']['bookmaker'] != sides['Away']['bookmaker']):

          home_point = sides['Home']['point']
          away_point = sides['Away']['point']

          # ✅ Ensure one side is negative and the other positive (opposite spreads)
          # or allow small ±0.5 tolerance for discrepancies like -6.0 vs +6.5
          if (home_point * away_point >= 0) and abs(home_point + away_point) > 0.5:
            continue

          home_prob = 1 / sides['Home']['odds']
          away_prob = 1 / sides['Away']['odds']
          implied_prob = home_prob + away_prob

          logger.info(f"Checking spread {point}:")
          logger.info(f"  Home: {sides['Home']['team']} ({home_point}) @ {sides['Home']['odds']} ({sides['Home']['bookmaker']}) - Implied prob: {home_prob:.4f}")
          logger.info(f"  Away: {sides['Away']['team']} ({away_point}) @ {sides['Away']['odds']} ({sides['Away']['bookmaker']}) - Implied prob: {away_prob:.4f}")
          logger.info(f"  Total implied prob: {implied_prob:.4f}")

          if implied_prob < 1:
            best_implied_prob = implied_prob
            best_odds = {
              sides['Home']['team']: sides['Home']['odds'],
              sides['Away']['team']: sides['Away']['odds']
            }
            best_bookmakers = {
              sides['Home']['team']: sides['Home']['bookmaker'],
              sides['Away']['team']: sides['Away']['bookmaker']
            }
            best_points = (home_point, away_point)

            logger.info(f"Found valid arbitrage opportunity:")
            logger.info(f"  Home: {sides['Home']['team']} {home_point} @ {sides['Home']['odds']} ({sides['Home']['bookmaker']})")
            logger.info(f"  Away: {sides['Away']['team']} {away_point} @ {sides['Away']['odds']} ({sides['Away']['bookmaker']})")
            logger.info(f"  Implied Probability: {implied_prob:.4f}")

    if best_odds:
      best_odds['spread'] = best_points
      return best_odds, best_bookmakers, best_points
    else:
      return None, None, None