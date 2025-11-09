import requests, os, json
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OFFLINE_FILE = os.path.join(BASE_DIR, '../static', 'arbitrage_results.json')

class OddsService:
  def __init__(self):
    load_dotenv()
    self.api_key = os.getenv('ODDS_API_KEY')
    self.base_url = 'https://api.the-odds-api.com/v4'
    self.markets = 'h2h,spreads,totals'
    self.remaining_requests = None
    self.used_requests = None
    self.api_limit_reached = False
    self.save_offline = False
    self.use_offline = True
    self.file_path = OFFLINE_FILE

  def get_sports(self):
    url = f"{self.base_url}/sports"
    params = {'api_key': self.api_key, 'all': 'false'}
    try:
      resp = requests.get(url, params=params)
      resp.raise_for_status()
      sports_data = resp.json()
      return sports_data
    except Exception as e:
      self.handle_api_error(e)
      return []

  def get_odds(self, sport, regions):
    if self.use_offline:
      return self.load_offline_data()['odds'].get(sport, [])
    
    if self.api_limit_reached:
      return []
    
    now = datetime.now(timezone.utc)
    from_date = now + timedelta(days=2)
    to_date = now + timedelta(days=7)

    commence_time_from = from_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    commence_time_to = to_date.strftime('%Y-%m-%dT%H:%M:%SZ')
  
    url = f"{self.base_url}/sports/{sport}/odds"
    params = {
      'api_key': self.api_key,
      'includeLinks': 'true',
      'oddsFormat': 'decimal',
      'dateFormat': 'iso',
      'regions': regions,
      'markets': self.markets,
      'commenceTimeFrom': commence_time_from,
      'commenceTimeTo': commence_time_to
      }
    try:
      resp = requests.get(url, params=params)
      if resp.status_code == 422:
        return []
      resp.raise_for_status()
      self.remaining_requests = resp.headers.get('x-requests-remaining')
      self.used_requests = resp.headers.get('x-requests-used')
      
      odds_data = resp.json()
      if self.save_offline:
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
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    # Write data to file (formatted)
    with open(self.file_path, 'w', encoding='utf-8') as f:
      json.dump(data, f, indent=2)

  def save_data_for_sport(self, sport, odds_data):
    # Load existing file if available
    if os.path.exists(self.file_path):
      with open(self.file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    else:
      data = {'sports': [], 'odds': {}}

    # Add or update data for the given sport
    data['odds'][sport] = odds_data

    if sport not in data['sports']:
      data['sports'].append(sport)

    self.save_data(data)
      
  def load_offline_data(self):
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    offline_file = os.path.join(BASE_DIR, '../static', 'arbitrage_results.json')
    with open(offline_file, 'r') as f:
      return json.load(f)
