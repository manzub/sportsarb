import os
from redis import Redis
from dotenv import load_dotenv
from celery import Celery
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import stripe

load_dotenv()

db = SQLAlchemy()
redis = Redis(host="localhost", db=0, port=6379, decode_responses=True)
migrate = Migrate()
login_manager = LoginManager()
stripe.api_key = os.getenv('STRIPE_SECRET')