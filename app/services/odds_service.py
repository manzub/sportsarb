import requests, os, json
from dotenv import load_dotenv

class OddsService:
  def __init__(self):
    load_dotenv()
    self.api_key = os.getenv('ODDS_API_KEY')
    self.base_url = 'https://api.the-odds-api.com/v4'
    self.markets = 'h2h,spreads,totals'
    self.remaining_requests = None
    self.used_requests = None
    self.api_limit_reached = False

  def get_sports(self):
    return self.load_offline_data()['sports']
    
    url = f"{self.base_url}/sports"
    params = {'api_key': self.api_key, 'all': 'false'}
    try:
      resp = requests.get(url, params=params)
      resp.raise_for_status()
      return resp.json()
    except Exception as e:
      self.handle_api_error(e)
      return []

  def get_odds(self, sport_key):
    return self.load_offline_data()['odds'].get(sport_key, [])
  
    url = f"{self.base_url}/sports/{sport_key}/odds"
    params = {
        'api_key': self.api_key,
        'markets': self.markets,
        'regions': 'uk,eu,us',
        'includeLinks': 'true',
        'oddsFormat': 'decimal',
        'dateFormat': 'iso',
    }
    try:
      resp = requests.get(url, params=params)
      if resp.status_code == 422:
        return []
      resp.raise_for_status()
      self.remaining_requests = resp.headers.get('x-requests-remaining')
      self.used_requests = resp.headers.get('x-requests-used')
      return resp.json()
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
      
  def load_offline_data(self):
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    offline_file = os.path.join(BASE_DIR, '../static', 'response_data.json')
    with open(offline_file, 'r') as f:
      return json.load(f)
