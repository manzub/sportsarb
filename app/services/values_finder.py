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

	# -------------------------------------------------------
	#                    PUBLIC ENTRYPOINT
	# -------------------------------------------------------
	def find_arbitrage(self, sports, markets):
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

			all_valuebets.sort(key=lambda x: x['expected_value'], reverse=True)
			save_json('valuebets', all_valuebets)

	# -------------------------------------------------------
	#               EVENT → MARKET → VALUEBET LOOP
	# -------------------------------------------------------
	def _calculate_valuebets(self, odds, sport_group):
			results = []
			for event in odds:
					for market_type in self.markets:
							try:
									results.extend(self._find_valuebets(event, market_type, sport_group))
							except Exception as e:
									logger.error(f"Error calculating valuebets for {event.get('id')}: {str(e)}")
			return results

	# -------------------------------------------------------
	#                  CORE VALUEBET LOGIC
	# -------------------------------------------------------
	def _find_valuebets(self, event, market_type, sport_group):
			bookmakers = event.get('bookmakers', [])
			if not bookmakers:
					return []

			market_data = self._extract_market_data(bookmakers, market_type, event)

			# 1) Find sharp or market-average reference odds
			sharp_ref_raw = self._find_sharp_reference(market_data)
			using_market_avg = False
			if not sharp_ref_raw:
					sharp_ref_raw = self._market_average_reference(market_data)
					using_market_avg = True
			if not sharp_ref_raw:
					return []

			# 2) Remove vig from reference odds → fair reference probabilities
			ref_implied_raw = {k: self._implied_prob(v) for k, v in sharp_ref_raw.items() if v > 1}
			fair_ref_probs = self._remove_vig(ref_implied_raw)

			# 3) Compute volatility map for confidence scoring
			vol_map = self._build_volatility_map(market_data)

			valuebets = []

			# 4) Convert each bookmaker’s odds into fair (vig-free) probabilities
			for book_name, outcomes in market_data.items():

					# Skip sharp books for betting
					if any(sharp in book_name.lower() for sharp in self.sharp_books):
							continue

					# Convert this bookmaker’s market to fair probabilities
					book_raw_probs = {k: self._implied_prob(v) for k, v in outcomes.items() if v > 1}
					fair_book_probs = self._remove_vig(book_raw_probs)

					for outcome_key, fair_prob in fair_book_probs.items():
							if outcome_key not in fair_ref_probs:
									continue

							book_odds = outcomes.get(outcome_key)
							if not book_odds or book_odds <= 1 or book_odds > 20:
									continue

							true_prob = fair_ref_probs[outcome_key]
							ev = (book_odds * true_prob) - 1

							# Drop extreme fake EV (stale odds or misalignment)
							if ev > 0.50:
									continue

							# Dynamic thresholds
							volatility_score = vol_map.get(outcome_key, 1.0)
							threshold = self._dynamic_threshold(using_market_avg, volatility_score, sport_group)

							if ev < threshold:
									continue

							# Outlier control vs reference odds
							ref_odds = sharp_ref_raw.get(outcome_key)
							if ref_odds and book_odds > ref_odds * 1.25:
									continue

							confidence = self._confidence_score(ev, using_market_avg, volatility_score, sport_group)

							record = self._create_valuebet_record(
									event, sport_group, book_name, market_type,
									outcome_key, book_odds, ref_odds, ev, confidence
							)
							if record:
									valuebets.append(record)

			valuebets.sort(key=lambda x: x['expected_value'], reverse=True)
			return valuebets

	# -------------------------------------------------------
	#              MARKET (ODDS) EXTRACTION
	# -------------------------------------------------------
	def _extract_market_data(self, bookmakers, market_type, event):
			"""Build aligned outcome keys per bookmaker."""
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

									point = outcome.get('point')
									nm = name.lower()

									# Create canonical outcome key
									if market_type == 'h2h':
											key = name

									elif market_type == 'spreads':
											key = f"{name}@{point}"

									elif market_type == 'totals':
											key = f"{name}@{point}"

									else:
											key = name

									prev = data[book_name].get(key)
									if not prev or price > prev:
											data[book_name][key] = price

			return data

	# -------------------------------------------------------
	#                SHARP / MARKET AVERAGE REF
	# -------------------------------------------------------
	def _find_sharp_reference(self, market_data):
			for sharp in self.sharp_books:
					for book, outcomes in market_data.items():
							if sharp in book.lower():
									return outcomes
			return None

	def _market_average_reference(self, market_data):
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

	# -------------------------------------------------------
	#                 MATHEMATICAL HELPERS
	# -------------------------------------------------------
	def _implied_prob(self, odds):
			return 1 / odds if odds and odds > 1 else None

	def _remove_vig(self, implied_probs):
			"""Normalize implied probabilities so they sum to 1.0."""
			total = sum(implied_probs.values())
			if total == 0:
					return implied_probs
			return {k: v / total for k, v in implied_probs.items()}

	# -------------------------------------------------------
	#                VOLATILITY & THRESHOLDS
	# -------------------------------------------------------
	def _build_volatility_map(self, market_data):
			by_key = defaultdict(list)
			for outcomes in market_data.values():
					for key, price in outcomes.items():
							if price and price > 1:
									by_key[key].append(price)

			vol_map = {}
			for key, prices in by_key.items():
					if len(prices) < 3:
							vol_map[key] = 0.7
							continue

					avg = mean(prices)
					sd = pstdev(prices) if len(prices) > 1 else 0
					cv = sd / avg if avg else 0

					score = 1 / (1 + cv)
					vol_map[key] = max(0.3, min(score, 1.0))

			return vol_map

	def _dynamic_threshold(self, using_market_avg, volatility_score, sport_group):
			base = 0.06 if using_market_avg else 0.03

			if volatility_score < 0.75:
					base += 0.02

			sg = (sport_group or '').lower()
			if any(tag in sg for tag in ['lower', 'reserve', 'u21', 'friendly']):
					base += 0.02

			return max(0.02, min(base, 0.12))

	def _confidence_score(self, ev, using_market_avg, volatility_score, sport_group):
			ev_score = min(max(ev, 0.0), 0.25) / 0.25
			source_factor = 0.7 if using_market_avg else 1.0
			vol_factor = volatility_score
			sg = (sport_group or '').lower()
			tier_factor = 0.9 if any(tag in sg for tag in ['lower', 'reserve', 'u21', 'friendly']) else 1.0
			confidence = ev_score * source_factor * vol_factor * tier_factor
			return round(max(0.0, min(confidence, 1.0)), 2)

	# -------------------------------------------------------
	#                      OUTPUT
	# -------------------------------------------------------
	def _create_valuebet_record(self, event, sport_group, bookmaker, market_type,
															outcome_key, odds, ref_odds, ev, confidence):

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
					'team_or_outcome': outcome_key,
					'odds': round(float(odds), 3),
					'reference_odds': round(float(ref_odds), 3) if ref_odds else None,
					'expected_value': round(float(ev) * 100, 2),
					'confidence': confidence,
					'bookmaker_link': get_bookmaker_links(event, [bookmaker], market_type),
					'commence_time': event.get('commence_time'),
					'sport_title': event.get('sport_title'),
					'unique_id': str(uuid.uuid4())
			}