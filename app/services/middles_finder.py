import uuid
from collections import defaultdict
from app.utils.redis_helper import save_json
from app.utils.helpers import get_bookmaker_links
from app.services.odds_service import OddsService
from app.utils.logger import setup_logging

logger = setup_logging()

class MiddlesFinder:
  def __init__(self):
    self.odds_api = OddsService()
    self.markets = ['spreads', 'totals']
    self.seen_middles = set()

  def find_arbitrage(self, sports, config):
    try:
      if not sports:
        logger.error("Failed to fetch sports data")
        return

      all_middles = []
      self.markets = config.get('markets', 'spreads,totals').split(',')

      for sport in sports:
        try:
          odds = self.odds_api.get_odds(sport_key=sport['key'], config=config)
          if self.odds_api.api_limit_reached:
            logger.warning("API limit reached. Stopping analysis.")
            break

          if odds:
            middles = self.calculate_arbitrage(odds, sport['group'])
            all_middles.extend(middles)
        except Exception as e:
          logger.error(f"Error processing sport {sport['key']}: {str(e)}")
          continue

      save_json('middles', all_middles)
    except Exception as e:
      logger.error(f"Fatal error in find_arbitrage: {str(e)}")

  def calculate_arbitrage(self, odds, sport_group):
    all_middles = []
    for event in odds:
      for market_type in self.markets:
        try:
          middles = self._find_middles(event, market_type, sport_group)
          all_middles.extend(middles)
        except Exception as e:
          logger.error(f"Error calculating middles for {event.get('id')}: {str(e)}")
    return all_middles

  def _find_middles(self, event, market_type, sport_group):
    """Finds middles (spreads/totals) for one event."""
    bookmakers = event.get('bookmakers', [])
    if not bookmakers:
      return []

    market_data = self._extract_market_data(bookmakers, market_type, event)
    middles = []
    bookmaker_names = list(market_data.keys())

    # Pairwise comparison of all bookmakers
    for i in range(len(bookmaker_names)):
      for j in range(i + 1, len(bookmaker_names)):
        b1, b2 = bookmaker_names[i], bookmaker_names[j]
        m1, m2 = market_data[b1], market_data[b2]

        if market_type == 'spreads':
          pairs = [
            (b1, b2, m1['home'], m2['away'], m1['home_price'], m2['away_price']),
            (b2, b1, m2['home'], m1['away'], m2['home_price'], m1['away_price']),
          ]
        else:  # totals
          pairs = [
            (b1, b2, m1['over'], m2['under'], m1['over_price'], m2['under_price']),
            (b2, b1, m2['over'], m1['under'], m2['over_price'], m1['under_price']),
          ]

        for b_home, b_away, line1, line2, price1, price2 in pairs:
          if line1 is None or line2 is None:
            continue

          # ✅ skip symmetrical or opposite lines (e.g. -9.5 / +9.5)
          if abs(line1) == abs(line2):
            continue

          # ✅ ensure a valid middle window
          window = round(line2 - line1, 2)
          if not (0 < window <= self._max_window_for_sport(sport_group)):
            continue

          # ✅ confidence score (narrower window → higher confidence)
          confidence = max(0, 1 - (window / self._max_window_for_sport(sport_group)))

          # ✅ EV estimation
          ev = self._estimate_ev(price1, price2)
          if ev is None or ev < 0:
            continue

          # ✅ filter low-confidence middles
          if confidence < 0.5:
            continue

          record = self._create_middle_record(
            event, sport_group, b_home, b_away, market_type,
            line1, line2, price1, price2, ev, confidence, window
          )

          if record:
            middles.append(record)

    return middles

  def _extract_market_data(self, bookmakers, market_type, event):
    """Extracts spreads or totals data per bookmaker."""
    data = defaultdict(lambda: {
      'home': None, 'away': None, 'over': None, 'under': None,
      'home_price': None, 'away_price': None,
      'over_price': None, 'under_price': None
    })

    for bookmaker in bookmakers:
      book_name = bookmaker.get('title')
      if not book_name:
        continue

      for market in bookmaker.get('markets', []):
        if market.get('key') != market_type:
          continue

        for outcome in market.get('outcomes', []):
          point, price = outcome.get('point'), outcome.get('price')
          if point is None or price is None:
            continue

          name = outcome.get('name', '').lower()
          if market_type == 'spreads':
            if name == event['home_team'].lower():
              data[book_name]['home'] = point
              data[book_name]['home_price'] = price
            elif name == event['away_team'].lower():
              data[book_name]['away'] = point
              data[book_name]['away_price'] = price
          elif market_type == 'totals':
            if 'over' in name:
              data[book_name]['over'] = point
              data[book_name]['over_price'] = price
            elif 'under' in name:
              data[book_name]['under'] = point
              data[book_name]['under_price'] = price
    return data

  def _implied_prob(self, odds):
    """Convert American or decimal odds to implied probability."""
    if odds is None:
      return None
    if abs(odds) > 10:  # American odds
      if odds > 0:
        return 100 / (odds + 100)
      return abs(odds) / (abs(odds) + 100)
    return 1 / odds if odds > 1 else None  # Decimal odds

  def _estimate_ev(self, price1, price2):
    """Estimate Expected Value (EV%) based on implied probabilities."""
    p1, p2 = self._implied_prob(price1), self._implied_prob(price2)
    if not p1 or not p2:
      return None
    overlap_prob = max(0, 1 - (p1 + p2))
    return round(overlap_prob * 100, 2)

  def _max_window_for_sport(self, sport_group):
    """Set the max middle window threshold depending on sport."""
    sport_group = sport_group.lower()
    if 'basketball' in sport_group:
      return 2.0
    elif 'football' in sport_group or 'nfl' in sport_group:
      return 3.0
    elif 'soccer' in sport_group:
      return 1.0
    return 2.5  # default

  def _create_middle_record(self, event, sport_group, b1, b2, market_type,
                            line1, line2, price1, price2, ev, confidence, window):
    """Create middle object, avoid duplicates."""
    key = f"{event['home_team']}_{event['away_team']}_{market_type}_{line1}_{line2}"
    if key in self.seen_middles:
      return None
    self.seen_middles.add(key)

    return {
      'type': 'middle',
      'event': f"{event['home_team']} vs {event['away_team']}",
      'sport_group': sport_group,
      'market': market_type,
      'bookmakers': {'bookmaker1': b1, 'bookmaker2': b2},
      'links': get_bookmaker_links(event, [b1, b2], market_type),
      'lines': {'home_line': line1, 'away_line': line2},
      'odds': {'home_price': price1, 'away_price': price2},
      'middle_range': window,
      'expected_value': ev,
      'confidence': round(confidence, 2),
      'commence_time': event.get('commence_time'),
      'sport_title': event.get('sport_title'),
      'unique_id': str(uuid.uuid4()),
    }