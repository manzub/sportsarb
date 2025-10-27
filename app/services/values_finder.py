import uuid
from collections import defaultdict
from app.utils.redis_helper import save_json
from app.utils.helpers import get_bookmaker_links
from app.services.odds_service import OddsService
from app.utils.logger import setup_logging

logger = setup_logging()

# find valuebets, use a sharpbook/market average to find valuebets
# if sharpbook exists use sharp book odds as true odds to filter/find valuebets
# else use market average
# implemented confidence scoring
class ValueBetsFinder:
  def __init__(self):
    self.odds_api = OddsService()
    self.markets = ['h2h', 'spreads', 'totals']
    self.seen_valuebets = set()
    self.value_threshold = 0.03  # 3% edge minimum
    self.sharp_books = ['betfair', 'pinnacle', 'sbobet', 'matchbook', 'betcris']

  def find_arbitrage(self, sports, config):
    """Fetch odds for each sport and identify value bets."""
    try:
      if not sports:
        logger.error("Failed to fetch sports data")
        return

      all_valuebets = []
      self.markets = config.get('markets', 'h2h,spreads,totals').split(',')

      for sport in sports:
        try:
          odds = self.odds_api.get_odds(sport_key=sport['key'], config=config)
          if self.odds_api.api_limit_reached:
            logger.warning("API limit reached. Stopping analysis.")
            break

          if odds:
            valuebets = self._calculate_valuebets(odds, sport['group'])
            all_valuebets.extend(valuebets)
        except Exception as e:
          logger.error(f"Error processing sport {sport['key']}: {str(e)}")
          continue

      save_json('valuebets', all_valuebets)
    except Exception as e:
      logger.error(f"Fatal error in find_valuebets: {str(e)}")

  def _calculate_valuebets(self, odds, sport_group):
    """Loop through all events for a sport and detect value opportunities."""
    all_valuebets = []
    for event in odds:
      for market_type in self.markets:
        try:
          bets = self._find_valuebets(event, market_type, sport_group)
          all_valuebets.extend(bets)
        except Exception as e:
          logger.error(f"Error calculating valuebets for {event.get('id')}: {str(e)}")
    return all_valuebets

  def _find_valuebets(self, event, market_type, sport_group):
    bookmakers = event.get('bookmakers', [])
    if not bookmakers:
      return []

    market_data = self._extract_market_data(bookmakers, market_type)
    sharp_ref = self._find_sharp_reference(market_data)
    if not sharp_ref:
      sharp_ref = self._market_average_reference(market_data)

    if not sharp_ref:
      return []

    valuebets = []
    for book_name, outcomes in market_data.items():
      if book_name.lower() in self.sharp_books:
        continue

      for outcome_name, price in outcomes.items():
        if not price or outcome_name not in sharp_ref:
          continue

        sharp_prob = self._implied_prob(sharp_ref[outcome_name])
        book_prob = self._implied_prob(price)
        if not sharp_prob or not book_prob:
          continue

        ev = self._expected_value(price, sharp_prob)
        if ev < self.value_threshold:
          continue

        confidence = self._confidence_score(ev)
        record = self._create_valuebet_record(
          event, sport_group, book_name, market_type,
          outcome_name, price, sharp_ref[outcome_name], ev, confidence
        )
        if record:
          valuebets.append(record)
    return valuebets
  
  def _extract_market_data(self, bookmakers, market_type):
    """Extracts outcome data for a given market from all bookmakers."""
    data = defaultdict(dict)
    for bookmaker in bookmakers:
      book_name = bookmaker.get('title')
      if not book_name:
        continue

      for market in bookmaker.get('markets', []):
        if market.get('key') != market_type:
          continue

        for outcome in market.get('outcomes', []):
          name, price = outcome.get('name'), outcome.get('price')
          if not name or not price:
            continue
          data[book_name][name] = price
    return data

  def _find_sharp_reference(self, market_data):
    """Find Betfair or other sharp bookmaker as reference."""
    for sharp in self.sharp_books:
      for book, outcomes in market_data.items():
        if sharp in book.lower():
          return outcomes
    return None

  def _market_average_reference(self, market_data):
    """Fallback to average market odds as a pseudo-sharp reference."""
    avg_data = defaultdict(list)
    for outcomes in market_data.values():
      for name, price in outcomes.items():
        avg_data[name].append(price)

    avg_ref = {}
    for name, prices in avg_data.items():
      if not prices:
        continue
      avg_ref[name] = sum(prices) / len(prices)
    return avg_ref if avg_ref else None

  def _implied_prob(self, odds):
    """Convert decimal odds to implied probability."""
    return 1 / odds if odds and odds > 1 else None

  def _expected_value(self, odds, sharp_prob):
    """Expected value = (odds * sharp_prob) - 1"""
    if not odds or not sharp_prob:
      return 0
    return (odds * sharp_prob) - 1

  def _confidence_score(self, ev):
    """Assign confidence level based on Expected Value size."""
    if ev >= 0.10:
      return 'High'
    elif ev >= 0.05:
      return 'Medium'
    else:
      return 'Low'
    
  def _create_valuebet_record(self, event, sport_group, bookmaker, market_type,
                              outcome, odds, ref_odds, ev, confidence):
    """Build and deduplicate a valuebet entry."""
    key = f"{event['home_team']}_{event['away_team']}_{bookmaker}_{outcome}_{market_type}"
    if key in self.seen_valuebets:
      return None
    self.seen_valuebets.add(key)

    return {
      'type': 'valuebet',
      'event': f"{event['home_team']} vs {event['away_team']}",
      'sport_group': sport_group,
      'market': market_type,
      'bookmaker': bookmaker,
      'team_or_outcome': outcome,
      'odds': round(odds, 3),
      'reference_odds': round(ref_odds, 3),
      'expected_value': round(ev * 100, 2),
      'confidence': confidence,
      'bookmaker_link': get_bookmaker_links(event, [bookmaker], market_type),
      'commence_time': event.get('commence_time'),
      'sport_title': event.get('sport_title'),
      'unique_id': str(uuid.uuid4())
    }
