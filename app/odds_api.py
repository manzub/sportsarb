import requests
import os
from redis import Redis
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

class OddsAPI:
  def __init__(self, config):
    load_dotenv()
    self.api_key = config.api_key or os.getenv('ODDS_API_KEY')
    self.base_url = 'https://api.the-odds-api.com/v4'
    self.config = config
    self.remaining_requests = None
    self.used_requests = None
    self.api_limit_reached = False
    
  def get_sports(self):
    url = f"{self.base_url}/sports"
    params = { 'api_key': self.api_key, 'all':'false' }
    
    try:
      response = requests.get(url, params=params)
      response.raise_for_status()
      sports_data = response.json()
      # TODO: save results to redis
      return sports_data
    except Exception as e:
      self.handle_api_error(e)
      return []
    
  def get_odds(self, sport):
    # TODO: optional offline
    if self.api_limit_reached:
      return []
    
    url = f"{self.base_url}/sports/{sport}/odds"
    params = {
      'api_key': self.api_key,
      'regions': self.config.region,
      # 'markets': self.config.market,  # Use the new market parameter
      'markets': 'h2h,totals,spreads',
      'oddsFormat': 'decimal',
      'dateFormat': 'iso',
    }
    
    try:
      response = requests.get(url, params=params)
      if response.status_code == 422:
        return []
      response.raise_for_status()
      
      self.remaining_requests = response.headers.get('x-requests-remaining')
      self.used_requests = response.headers.get('x-requests-used')
      
      odds_data = response.json()
      # TODO: save offline?
      return odds_data
    except Exception as e:
      self.handle_api_error(e)
      return []
    
  def handle_api_error(self, error):
    if isinstance(error, requests.exceptions.HTTPError):
      if error.response.status_code == 401:
        print("Error: Unauthorized. Please check your API key.")
        self.api_limit_reached = True
      elif error.response.status_code == 429:
        print("Error: API request limit reached. Please try again later or upgrade your plan.")
        self.api_limit_reached = True
      else:
        print(f"HTTP Error: {error}")
    else:
      print(f"Error fetching data: {error}")