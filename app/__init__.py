import os
from dotenv import load_dotenv
from flask import Flask
from datetime import datetime
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import stripe

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
stripe.api_key = os.getenv('STRIPE_SECRET')


def create_app():
  app = Flask(__name__)
  app.config.from_object('app.config.AppConfigs')

  db.init_app(app)
  login_manager.init_app(app)
  login_manager.login_view = 'main.signin'

  migrate.init_app(app, db)

  # import routes AFTER app + db are set up
  from app import models
  from app.routes import bp as main_bp
  app.register_blueprint(main_bp)
  csrf = CSRFProtect(app)

  return app

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.utcnow() and (sub.end_date is None or sub.end_date >= datetime.utcnow()))