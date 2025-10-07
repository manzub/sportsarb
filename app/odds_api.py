import requests
import os
import json
from dotenv import load_dotenv

class OddsAPI:
  def __init__(self):
    load_dotenv()
    self.api_key = os.getenv('ODDS_API_KEY')
    self.base_url = 'https://api.the-odds-api.com/v4'
    # self.config = config
    self.markets = 'h2h,spreads,totals'
    self.remaining_requests = None
    self.used_requests = None
    self.api_limit_reached = False
    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    self.offline_file = os.path.join(BASE_DIR, 'static', 'response_data.json')
    self.save_file = os.path.join(BASE_DIR, 'static', 'arbitrage_results.json')
    
  def get_sports(self):
    if self.offline_file:
      return self.load_offline_data()['sports']
    
    url = f"{self.base_url}/sports"
    params = { 'api_key': self.api_key, 'all':'false' }
    
    try:
      response = requests.get(url, params=params)
      response.raise_for_status()
      sports_data = response.json()
      # TODO: save results to redis
      if self.offline_file:
        self.save_data({'sports': sports_data, 'odds': {}})
      return sports_data
    except Exception as e:
      self.handle_api_error(e)
      return []
    
  def get_odds(self, sport):
    # TODO: optional offline
    if self.offline_file:
      return self.load_offline_data()['odds'].get(sport, [])
    if self.api_limit_reached:
      return []
    
    url = f"{self.base_url}/sports/{sport}/odds"
    params = {
      'api_key': self.api_key,
      # 'regions': self.config.region,
      # 'markets': self.config.market,  # Use the new market parameter
      'markets': self.markets,
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
      if self.offline_file:
        self.save_data_for_sport(sport, odds_data)
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
  
  def save_data(self, data):
    with open(self.save_file, 'w') as f:
      json.dump(data, f)

  def save_data_for_sport(self, sport, odds_data):
    if os.path.exists(self.save_file):
      with open(self.save_file, 'r') as f:
        data = json.load(f)
    else:
      data = {'sports': [], 'odds': {}}
    
    data['odds'][sport] = odds_data
    self.save_data(data)
    
  def load_offline_data(self):
    with open(self.offline_file, 'r') as f:
      return json.load(f)