import os
from redis import Redis
from dotenv import load_dotenv
from celery import Celery
from flask import Flask
from datetime import datetime
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import stripe

load_dotenv()

db = SQLAlchemy()
redis = Redis(host="localhost", db=0, port=6379, decode_responses=True)
migrate = Migrate()
login_manager = LoginManager()
stripe.api_key = os.getenv('STRIPE_SECRET')

def make_celery(app):
  celery = Celery(app.import_name, backend=app.config['result_backend'], broker=app.config['broker_url'])
  celery.conf.update(app.config)
  
  class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
      with app.app_context():
        return self.run(*args, **kwargs)
  celery.Task = ContextTask
  return celery


def create_app():
  app = Flask(__name__)
  app.config.from_object('app.config.AppConfigs')
  
  app.config.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0'
  )

  db.init_app(app)
  login_manager.init_app(app)
  login_manager.login_view = 'main.signin'

  migrate.init_app(app, db)

  # import routes AFTER app + db are set up
  from app import models, tasks
  from app.routes import bp as main_bp
  app.register_blueprint(main_bp)
  app.celery = make_celery(app)
  CSRFProtect(app)

  return app

def has_active_subscription(user):
  if not user.current_plan:
    return False
  
  sub = user.current_plan
  return (sub.active and sub.start_date <= datetime.utcnow() and (sub.end_date is None or sub.end_date >= datetime.utcnow()))