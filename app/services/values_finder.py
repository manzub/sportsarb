import uuid
from collections import defaultdict
from app.utils.redis_helper import save_json, get_cached_odds
from app.utils.helpers import update_sport_db_count
from app.utils.arb_helper import get_bookmaker_links
from app.utils.logger import setup_logging

logger = setup_logging()

# find valuebets, use a sharpbook/market average to find valuebets
# if sharpbook exists use sharp book odds as true odds to filter/find valuebets
# else use market average
# implemented confidence scoring
class ValueBetsFinder:
  def __init__(self):
    self.markets = ['h2h', 'spreads', 'totals']
    self.seen_valuebets = set()
    self.value_threshold = 0.03  # 3% edge minimum
    self.sharp_books = ['betfair', 'pinnacle', 'sbobet', 'matchbook', 'betcris']

  def find_arbitrage(self, sports, markets):
    """Fetch odds for each sport and identify value bets."""
    try:
      if not sports:
        logger.error("Failed to fetch sports data")
        return

      all_valuebets = []
      self.markets = markets.split(',') if markets else ['spreads', 'totals', 'h2h']

      for sport in sports:
        try:
          odds = get_cached_odds(sport=sport['key'])
          if odds:
            valuebets = self._calculate_valuebets(odds, sport['group'])
            all_valuebets.extend(valuebets)
            update_sport_db_count(key=sport['key'], valuebets=len(all_valuebets)) #update db counts
        except Exception as e:
          logger.error(f"ValueBet - Error processing sport {sport['key']}: {str(e)}")
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
    using_market_avg = False

    if not sharp_ref:
      sharp_ref = self._market_average_reference(market_data)
      using_market_avg = True

    if not sharp_ref:
      return []

    valuebets = []

    for book_name, outcomes in market_data.items():
      if not outcomes or book_name.lower() in self.sharp_books:
        continue  # skip sharp or empty

      for outcome_name, price in outcomes.items():
        if not price or outcome_name not in sharp_ref:
          continue

        sharp_odds = sharp_ref[outcome_name]
        if not sharp_odds or sharp_odds <= 1:
          continue

        sharp_prob = self._implied_prob(sharp_odds)
        book_prob = self._implied_prob(price)
        if not sharp_prob or not book_prob:
          continue

        # Expected Value (in decimal form)
        ev = (price * sharp_prob) - 1

        # Apply stronger filtering rules
        # skip tiny edges or improbable ones
        if ev < 0.05:  # require at least +5% EV
          continue

        # skip extremely inflated odds (likely data outlier)
        if price > sharp_odds * 1.25:
          continue

        # Skip low-confidence situations when using market average
        if using_market_avg and ev < 0.08:
          continue

        # Confidence now combines EV + reference quality
        confidence = self._confidence_score(ev, using_market_avg)

        record = self._create_valuebet_record(
          event, sport_group, book_name, market_type,
          outcome_name, price, sharp_odds, ev, confidence
        )

        if record:
          valuebets.append(record)

    # Sort by EV descending and limit per event to top few
    valuebets.sort(key=lambda x: x['expected_value'], reverse=True)
    return valuebets[:5]  # ✅ only keep top 5 strongest per event
  
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
    avg_data = defaultdict(list)
    for outcomes in market_data.values():
      for name, price in outcomes.items():
        if price and price > 1:
          avg_data[name].append(price)

    avg_ref = {}
    for name, prices in avg_data.items():
      if len(prices) < 3:
        continue  # skip unreliable averages
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

  def _confidence_score(self, ev, using_market_avg=False):
    """Assign numeric confidence (0–1) based on EV and data reliability."""
    base = min(max(ev, 0), 0.25) / 0.25  # scale EV up to 25%
    if using_market_avg:
      base *= 0.7  # penalize confidence if using avg market odds
    return round(base, 2)
    
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
