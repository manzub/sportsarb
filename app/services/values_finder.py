import uuid
from collections import defaultdict
from statistics import mean, pstdev
from app.utils.redis_helper import save_json, get_cached_odds
from app.utils.helpers import update_sport_db_count
from app.utils.arb_helper import get_bookmaker_links
from app.utils.logger import setup_logging

logger = setup_logging()

class ValueBetsFinder:
  def __init__(self):
    self.markets = ['h2h', 'spreads', 'totals']
    self.seen_valuebets = set()
    self.sharp_books = ['betfair', 'pinnacle', 'sbobet', 'matchbook', 'betcris']

  # ------------------ Public entrypoint ------------------

  def find_arbitrage(self, sports, markets):
    """Fetch odds for each sport and identify value bets."""
    if not sports:
      logger.error("Failed to fetch sports data")
      return

    all_valuebets = []
    self.markets = markets.split(',') if markets else self.markets

    for sport in sports:
      try:
        odds = get_cached_odds(sport=sport['key'])
        if not odds:
          continue
        valuebets = self._calculate_valuebets(odds, sport['group'])
        all_valuebets.extend(valuebets)
        update_sport_db_count(key=sport['key'], valuebets=len(all_valuebets))
      except Exception as e:
        logger.error(f"ValueBet - Error processing sport {sport['key']}: {str(e)}")
        continue

    # Sort globally by EV desc and save
    all_valuebets.sort(key=lambda x: x['expected_value'], reverse=True)
    save_json('valuebets', all_valuebets)

  # ------------------ Orchestration ------------------

  def _calculate_valuebets(self, odds, sport_group):
    """Loop through all events for a sport and detect value opportunities."""
    results = []
    for event in odds:
      for market_type in self.markets:
        try:
          results.extend(self._find_valuebets(event, market_type, sport_group))
        except Exception as e:
          logger.error(f"Error calculating valuebets for {event.get('id')}: {str(e)}")
    return results

  # ------------------ Core finder ------------------

  def _find_valuebets(self, event, market_type, sport_group):
    """
    Detect value bets for one event + market.
    Uses sharp book if present; otherwise falls back to market average.
    EV = (book_odds * true_prob_no_vig) - 1
    """
    bookmakers = event.get('bookmakers', [])
    if not bookmakers:
      return []

    # 1) Extract market data (keyed so spreads/totals align by point)
    market_data = self._extract_market_data(bookmakers, market_type, event)

    # 2) Reference set: sharp preferred, else market average
    sharp_ref = self._find_sharp_reference(market_data)
    using_market_avg = False
    if not sharp_ref:
      sharp_ref = self._market_average_reference(market_data)
      using_market_avg = True
    if not sharp_ref:
      return []

    # 3) Build fair (no-vig) probabilities from the reference
    # sharp_ref is dict outcome_key -> decimal odds
    sharp_implied = {k: self._implied_prob(v) for k, v in sharp_ref.items() if v and v > 1}
    if not sharp_implied:
      return []
    fair_probs = self._remove_vig(sharp_implied)  # sums to 1.0

    # 4) Pre-compute market volatility per outcome_key for confidence/threshold
    #    (how much different books disagree on the decimal odds for this outcome_key)
    vol_map = self._build_volatility_map(market_data)

    valuebets = []
    for book_name, outcomes in market_data.items():
      if not outcomes or book_name is None:
        continue
      # Skip using the sharp book itself as a candidate (we compare other books to sharp)
      if any(sharp in book_name.lower() for sharp in self.sharp_books):
        continue

      for outcome_key, book_odds in outcomes.items():
        # outcome_key is aligned (e.g., "Home Team@-6.0" or "Over@210.5" or "Team Name")
        if outcome_key not in fair_probs:
          continue
        if not book_odds or book_odds <= 1:
          continue
        
        if book_odds > 20:
          continue
        
        # ---- Spread/Totals Point alignment check ----
        if market_type in ['spreads', 'totals'] and outcome_key not in sharp_ref:
          continue

        true_prob = fair_probs[outcome_key]  # fair probability (no vig)
        ev = (book_odds * true_prob) - 1
        
        if ev > 0.50:
          continue

        # Dynamic threshold based on source + volatility + sport group
        volatility_score = vol_map.get(outcome_key, 1.0)  # 0..1 where 1 means tight/agreeing market
        threshold = self._dynamic_threshold(using_market_avg, volatility_score, sport_group)

        # Basic sanity: discard low EV
        if ev < threshold:
          continue

        # Outlier control: if way higher than sharp, likely stale/error
        ref_odds = sharp_ref.get(outcome_key)
        if ref_odds and book_odds > ref_odds * 1.25:
          continue

        # Confidence blends EV strength, source reliability, and volatility
        confidence = self._confidence_score(ev, using_market_avg, volatility_score, sport_group)

        record = self._create_valuebet_record(
          event=event,
          sport_group=sport_group,
          bookmaker=book_name,
          market_type=market_type,
          outcome_key=outcome_key,
          odds=book_odds,
          ref_odds=ref_odds if ref_odds else None,
          ev=ev,
          confidence=confidence
        )
        if record:
          valuebets.append(record)

    # Return ALL valid bets above threshold (Option A), sorted by EV desc
    valuebets.sort(key=lambda x: x['expected_value'], reverse=True)
    return valuebets

  # ------------------ Data extraction ------------------

  def _extract_market_data(self, bookmakers, market_type, event):
      """
      Returns dict:
        { 'Bookmaker Name': { outcome_key: decimal_odds, ... }, ... }

      outcome_key aligns by market:
        - h2h: team name
        - spreads: "TeamName@POINT" (e.g., "Lakers@-6.5")
        - totals: "Over@POINT" / "Under@POINT" (e.g., "Over@210.5")
      """
      data = defaultdict(dict)
      home = (event.get('home_team') or '').lower()
      away = (event.get('away_team') or '').lower()

      for bookmaker in bookmakers:
          book_name = bookmaker.get('title')
          if not book_name:
              continue

          for market in bookmaker.get('markets', []):
              if market.get('key') != market_type:
                  continue

              for outcome in market.get('outcomes', []):
                  name = outcome.get('name')
                  price = outcome.get('price')
                  if not name or not price:
                      continue

                  # Build aligned outcome key
                  point = outcome.get('point')
                  key = None
                  if market_type == 'h2h':
                      key = name  # as given by feed
                  elif market_type == 'spreads':
                      # normalize by matching to home/away labels via team names
                      nm = name.lower()
                      # Prefer the original casing in key for readability
                      if nm == home or nm == away:
                          key = f"{name}@{point}" if point is not None else name
                      else:
                          # unknown name; still keep but include point to avoid clashes
                          key = f"{name}@{point}" if point is not None else name
                  elif market_type == 'totals':
                      nm = name.lower()
                      if 'over' in nm or 'under' in nm:
                          key = f"{name}@{point}" if point is not None else name
                      else:
                          # totals outcome without clear Over/Under label — keep raw
                          key = f"{name}@{point}" if point is not None else name
                  else:
                      key = name

                  # Keep best (highest) odds per bookmaker/outcome_key
                  prev = data[book_name].get(key)
                  if (not prev) or (price > prev):
                      data[book_name][key] = price

      return data

  # ------------------ Reference builders ------------------

  def _find_sharp_reference(self, market_data):
      """Return odds dict from the first sharp book present, else None."""
      for sharp in self.sharp_books:
          for book, outcomes in market_data.items():
              if sharp in book.lower():
                  return outcomes
      return None

  def _market_average_reference(self, market_data):
      """Average decimal odds per outcome_key across books (min 3 books)."""
      stacks = defaultdict(list)
      for outcomes in market_data.values():
          for key, price in outcomes.items():
              if price and price > 1:
                  stacks[key].append(price)

      avg_ref = {}
      for key, prices in stacks.items():
          if len(prices) < 3:
              continue
          avg_ref[key] = sum(prices) / len(prices)
      return avg_ref if avg_ref else None

  # ------------------ Math helpers ------------------

  def _implied_prob(self, odds):
      return 1 / odds if odds and odds > 1 else None

  def _remove_vig(self, implied_probs):
      """
      Normalize raw implied probabilities (sum > 1) to fair (sum = 1).
      implied_probs: dict outcome_key -> raw implied prob
      """
      total = sum(p for p in implied_probs.values() if p)
      if not total:
          return implied_probs
      return {k: (v / total) for k, v in implied_probs.items()}

  def _build_volatility_map(self, market_data):
      """
      For each outcome_key, compute a 0..1 'agreement score':
        1.0 = tight agreement (low dispersion), ~0.5 or less = high dispersion.
      We use normalized dispersion via coefficient of variation-like transform.
      """
      by_key = defaultdict(list)
      for outcomes in market_data.values():
          for key, price in outcomes.items():
              if price and price > 1:
                  by_key[key].append(price)

      vol_map = {}
      for key, prices in by_key.items():
          if len(prices) < 3:
              # with too few books, treat as lower confidence
              vol_map[key] = 0.7
              continue
          avg = mean(prices)
          if avg <= 0:
              vol_map[key] = 0.6
              continue
          sd = pstdev(prices) if len(prices) > 1 else 0.0
          cv = (sd / avg) if avg else 0.0  # coefficient of variation
          # Map CV to 0..1 where higher cv -> lower score
          score = 1 / (1 + cv)  # cv=0 => 1.0 ; cv=1 => 0.5 ; cv=2 => 0.333...
          # Clamp
          vol_map[key] = max(0.3, min(score, 1.0))
      return vol_map

  def _dynamic_threshold(self, using_market_avg, volatility_score, sport_group):
      """
      Base thresholds:
        - sharp: 3%
        - market average: 6%
      Add +2% for volatile/low tiers or weak agreement.
      """
      base = 0.06 if using_market_avg else 0.03

      # Penalize volatility / disagreement
      if volatility_score < 0.75:
          base += 0.02

      # Light sport-group heuristic (optional, non-invasive)
      sg = (sport_group or '').lower()
      if any(tag in sg for tag in ['lower', 'reserve', 'u21', 'friendly']):
          base += 0.02

      # Clamp sane bounds
      return max(0.02, min(base, 0.12))

  def _confidence_score(self, ev, using_market_avg, volatility_score, sport_group):
      """
      Confidence blends:
        - EV strength (capped at 25%)
        - Source quality (sharp > market avg)
        - Market agreement (volatility score)
        - Light sport-group penalty for low tiers
      Returns 0..1
      """
      # EV contribution
      ev_score = min(max(ev, 0.0), 0.25) / 0.25  # 0..1

      # Source factor
      source_factor = 0.7 if using_market_avg else 1.0

      # Volatility factor already 0.3..1.0 from _build_volatility_map
      vol_factor = volatility_score

      # Sport group small penalty for low tiers
      sg = (sport_group or '').lower()
      tier_factor = 0.9 if any(tag in sg for tag in ['lower', 'reserve', 'u21', 'friendly']) else 1.0

      confidence = ev_score * source_factor * vol_factor * tier_factor
      return round(max(0.0, min(confidence, 1.0)), 2)

  # ------------------ Output builder ------------------

  def _create_valuebet_record(self, event, sport_group, bookmaker, market_type,
                              outcome_key, odds, ref_odds, ev, confidence):
      """
      Build and deduplicate a valuebet entry.
      Output fields intentionally minimal (no internal fields like true_prob/vol/source).
      """
      key = f"{event.get('home_team')}_{event.get('away_team')}_{bookmaker}_{outcome_key}_{market_type}"
      if key in self.seen_valuebets:
          return None
      self.seen_valuebets.add(key)

      return {
          'type': 'valuebet',
          'event': f"{event.get('home_team')} vs {event.get('away_team')}",
          'sport_group': sport_group,
          'market': market_type,
          'bookmaker': bookmaker,
          'team_or_outcome': outcome_key,     # includes point for spreads/totals (e.g., "Over@210.5", "Lakers@-6.5")
          'odds': round(float(odds), 3),
          'reference_odds': round(float(ref_odds), 3) if ref_odds else None,
          'expected_value': round(float(ev) * 100, 2),  # %
          'confidence': confidence,
          'bookmaker_link': get_bookmaker_links(event, [bookmaker], market_type),
          'commence_time': event.get('commence_time'),
          'sport_title': event.get('sport_title'),
          'unique_id': str(uuid.uuid4())
      }