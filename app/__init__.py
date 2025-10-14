from flask import Flask
from flask_wtf import CSRFProtect
from celery import Celery
from .extensions import db, login_manager, migrate
from .routes import main, auth, api, plans

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
  login_manager.login_view = 'auth.login'

  migrate.init_app(app, db)

  from app import models, tasks
  app.register_blueprint(main.bp)
  app.register_blueprint(auth.bp, url_prefix='/auth')
  app.register_blueprint(api.bp, url_prefix='/api')
  app.register_blueprint(plans.bp, url_prefix='/plans')
  
  app.celery = make_celery(app)
  CSRFProtect(app)
  
  return app