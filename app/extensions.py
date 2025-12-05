import os
from redis import Redis, from_url
from dotenv import load_dotenv
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
import stripe

load_dotenv()
run_mode = os.getenv("RUN_MODE", "docker")
is_local = run_mode == "local"

if is_local:
  redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)
else:
  redis = from_url(os.getenv("REDIS_URL"))
    
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()
stripe.api_key = os.getenv('STRIPE_SECRET')