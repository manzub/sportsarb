import os
from datetime import datetime
from flask import Flask, send_from_directory, abort, session, flash
from flask_login import current_user
from flask_admin import Admin
from flask_admin.theme import Bootstrap4Theme
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_wtf import CSRFProtect
from celery import Celery
from .extensions import db, login_manager, migrate, mail
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
  
  broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
  app.config.update(
    broker_url=broker,
    result_backend=broker
  )

  db.init_app(app)
  login_manager.init_app(app)
  login_manager.login_view = 'auth.login'

  migrate.init_app(app, db)
  mail.init_app(app)

  from app import models, tasks
  from app.models import UserSubscriptions, User, AppSettings, Sports
  from app.utils.helpers import get_exchange_rates
  from app.admin import AdminView, SecureAdminIndexView, SportView
  
  app.register_blueprint(main.bp)
  app.register_blueprint(auth.bp, url_prefix='/auth')
  app.register_blueprint(api.bp, url_prefix='/api')
  app.register_blueprint(plans.bp, url_prefix='/plans')
  
  @app.context_processor
  def get_app_name():
    app_name = AppSettings.query.filter_by(setting_name='app_name').first()
    return dict(app_name=app_name.value if app_name else 'NoName')
  
  @app.context_processor
  def check_active_plan():
    pending_plan_id = None
    if current_user and current_user.is_authenticated:
      user_plan = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
      if user_plan and not user_plan.active and user_plan.status == 'pending':
        flash('pending', 'yellow')
        pending_plan_id = user_plan.id
    return {'pending_plan_id': pending_plan_id}

  @app.context_processor
  def inject_currency_data():
    exchange_rates = get_exchange_rates() or {}
    if not isinstance(exchange_rates, dict):
      exchange_rates = {}
    else:
      exchange_rates = {k: float(v) for k, v in exchange_rates.items() if isinstance(v, (int, float))}

    return dict(
      exchange_rates=exchange_rates,
      preferred_currency=(
        current_user.preferred_currency if current_user.is_authenticated
        else session.get('preferred_currency', 'USD')
      )
    )
  
  with app.app_context():
    admin = Admin(app=app, name='Surebet Admin', index_view=SecureAdminIndexView(url='/admin', endpoint='admin'), theme=Bootstrap4Theme(swatch='flatly'))
    admin.add_view(AdminView(User, db.session, name='Users'))
    admin.add_view(AdminView(AppSettings, db.session, category='Settings', name='App Settings'))
    admin.add_view(SportView(Sports, db.session, category='Settings', name='Sports'))
    admin.add_link(MenuLink(name="Webpage", url="/"))
    admin.add_link(MenuLink(name="Logout", category="Account", url="/auth/logout"))
  
  @app.route('/<path:filename>')
  def serve_from_static(filename):
    static_path = os.path.join(app.static_folder, filename)
    if os.path.exists(static_path):
      return send_from_directory(app.static_folder, filename)
    abort(404)
  
  app.celery = make_celery(app)
  CSRFProtect(app)
  
  return app