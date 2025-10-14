import json
from urllib.parse import unquote
from datetime import datetime
from flask import Blueprint, render_template, flash, request, redirect, url_for
from app.extensions import db, redis
from flask_login import current_user, login_required
from app.models import UserSubscriptions, Subscriptions
from app.utils.helpers import has_active_subscription, check_active_plan

bp = Blueprint('main', __name__)

@bp.app_template_filter('format_date')
def format_date(date_string):
  date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
  return date.strftime('%Y-%m-%d %I:%M %p %Z')

@bp.app_template_filter("days_to_months")
def days_filter(days):
  import math
  if days == 30:
    return "Month"
  months = math.ceil(days / 30)
  return f"{months} Month{'s' if months > 1 else ''}"

@bp.route('/')
def index():
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('homepage.html', has_active_subscription=active_subscription)

@bp.route('/change_currency', methods=['POST'])
@login_required
def change_currency():
  currency = request.form.get('currency')
  if currency:
    current_user.preferred_currency = currency
    db.session.commit()
    flash(f"Preferred currency changed to {currency}", 'emerald')
  return redirect(url_for('main.index'))

@bp.route('/calculator')
def bet_calculator():
  redis_key = request.args.get('page')
  arb_filter = unquote(request.args.get('arb_item'))
  if arb_filter and redis_key:
    # get redis arb items
    latest = max(redis.keys(f"{redis_key}:*"))
    data = redis.get(latest)
    arb_item = [x for x in json.loads(data) if x['unique_id'] == arb_filter]
    if arb_item:
      total_implied_prob = sum(1/odd for odd in list(arb_item[0]['best_odds'].values()))
      return render_template('calculator.html', total_implied_prob=total_implied_prob, arb_item=arb_item[0]) # continue logic
    flash(f"Could not find {str(redis_key).capitalize()} Item", 'red')
  flash("Page Not Found", 'red')
  return render_template('404.html')

@bp.route('/account')
@login_required
@check_active_plan
def account():
  user_subscription = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
  plan = Subscriptions.query.filter_by(id=user_subscription.plan_id).first()
  return render_template('account.html', plan=plan, user_subscription=user_subscription)
