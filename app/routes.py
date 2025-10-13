import json
from functools import wraps
from datetime import datetime, timedelta
from urllib.parse import unquote
from flask import Blueprint, render_template, session, flash, request, url_for, redirect, jsonify, current_app
from app.models import User, Alerts, Subscriptions, AppSettings, UserSubscriptions
from app.forms import LoginForm, SelectPlan

from app import has_active_subscription, db, stripe, redis
from flask_login import current_user, login_required, login_user, logout_user

bp = Blueprint('main', __name__)

def check_active_plan(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    pending_plan_id = None

    if current_user.is_authenticated:
      user_plan = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
      if user_plan and not user_plan.active and user_plan.status == 'pending':
        flash('pending', 'yellow')
        pending_plan_id = user_plan.id
      session['has_active_plan'] = user_plan.active

    # Render the route function result
    response = fn(*args, **kwargs)

    # If response is a rendered template, inject the variable
    if isinstance(response, dict):
      response['pending_plan_id'] = pending_plan_id
      return response
    return response
  return wrapper

def sort_surebet_data(data):
  results = []
  for arb in json.loads(data):
    arb_item = []
    surebet_id = str(arb['event']).replace(" ", "")[:11]
    team_names = str(arb['event']).split(' vs ')
    event = f"{team_names[0]} to Win"
    bookmakers = list(arb['bookmakers'].keys())
    for idx, item in enumerate(bookmakers):
      if idx > 0 and len(bookmakers) == 2:
        event = f"{team_names[1]} to Win"
      elif len(bookmakers) == 3:
        event = "Both teams to draw"
      x_item = {
        "surebet_id": arb['unique_id'],
        "profit": round(arb['profit_margin'], 2),
        "bookmaker": arb['bookmakers'][item],
        "start_time": arb['commence_time'],
        "event": event,
        "tournament": arb['sport_title'],
        "market": item,
        "odds": arb['best_odds'][item]
      }
      arb_item.append(x_item)
    results.extend(arb_item)
  return results

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


@bp.route('/api/surebets', methods=['GET'])
def get_surebets():
  data = []
  keys = redis.keys('surebets:*')
  if keys:
    latest = max(keys)
    __data = redis.get(latest)
    data = sort_surebet_data(__data)
  
  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 10))
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit

  return jsonify({ "data": data[start:end], "page": page, "total_pages": total_pages })
  
@bp.route('/calculator', methods=['GET'])
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
  

@bp.route('/')
def index():
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('homepage.html', has_active_subscription=active_subscription)

@bp.route('/plan/overview', methods=['GET', 'POST'])
def plans_overview():
  form = SelectPlan()
  if form.validate_on_submit():
    if current_user.is_authenticated:
      # check valid plan_id, create new plan or replace current, set to pending
      if form.plan_id.data:
        valid_plan = Subscriptions.query.filter_by(id=form.plan_id.data).first()
        if not valid_plan:
          flash("Invalid plan selected", 'yellow')
        
        # replace existing plan
        plan = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
        if plan:
          db.session.delete(plan)
          db.session.commit()
        # create new plan
        end_date = datetime.utcnow() + timedelta(days=30)
        new_plan = UserSubscriptions(user_id=current_user.id, active=False, plan_id=form.plan_id.data, start_date=datetime.utcnow(), end_date=end_date)
        db.session.add(new_plan)
        db.session.commit()
        flash(f"New Plan {valid_plan.plan_name} Started", 'emerald')
        return redirect(url_for('main.account'))
    else:
      flash("Must be signed in to start a new plan", 'yellow')
      return redirect(url_for('main.signin'))

  plans = Subscriptions.query.all()
  plans_with_benefits = []
  if plans and len(plans) > 0:
    for x in plans:
      settings_key = f"{x.plan_name.lower()}_plan_benefit"
      benefits = AppSettings.query.filter_by(setting_name=settings_key).first()
      data = x.to_dict()
      data['benefits'] = json.loads(benefits.value)
      plans_with_benefits.append(data)
  else:
    redirect(url_for('main.index'))
        
  return render_template('plans.html', plans=plans_with_benefits, form=form)

@bp.route('/plan/checkout/<int:plan_id>', methods=['GET'])
def checkout(plan_id):
  return render_template('select-plan.html', plan_id=plan_id)

@bp.route('/plans/return', methods=['GET'])
def payment_return():
  return render_template('return.html')

@bp.route('/account', methods=['GET'])
@login_required
@check_active_plan
def account():
  user_subscription = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
  plan = Subscriptions.query.filter_by(id=user_subscription.plan_id).first()
  return render_template('account.html', plan=plan, user_subscription=user_subscription)

@bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
  try:
    post_data = request.get_json()
    plan_id = session['plan_id'] if not post_data['plan_id'] else post_data['plan_id']
    data = UserSubscriptions.query.filter_by(id=plan_id).first()
    plan = Subscriptions.query.filter_by(id=data.plan_id).first()
    if plan:
      session['plan_id'] = plan_id
      stripe_session = stripe.checkout.Session.create(
        ui_mode='embedded',
        line_items=[
          {'price': plan.stripe_price_id, 'quantity': 1},
        ],
        metadata={"plan_id":plan_id},
        mode='subscription',
        return_url=current_app.config['SITE_URL']+"/plans/return?session_id={CHECKOUT_SESSION_ID}",
        automatic_tax={'enabled': True}
      )
    else:
      raise Exception('Invalid Plan Id')
  except Exception as e:
      print(e)
      return str(e)
  
  return jsonify(clientSecret=stripe_session.client_secret)

@bp.route('/session-status', methods=['GET'])
@login_required
def session_status():
  stripe_session = stripe.checkout.Session.retrieve(request.args.get('session_id'))
  if stripe_session.status == 'complete':
    # update to database and start subscription
    plan_id = stripe_session.metadata['plan_id']
    subscription = UserSubscriptions.query.filter_by(id=plan_id).first();
    if subscription:
      if not subscription.active:
        subscription.status = 'active'
        subscription.active = True
        subscription.start_date = datetime.utcnow()
        subscription.end_date = datetime.utcnow() + timedelta(days=30)
        db.session.commit()

  return jsonify(status=stripe_session.status, customer_email=stripe_session.customer_details.email)

@bp.route('/signin', methods=['GET', 'POST'])
def signin():
  form = LoginForm()
  if form.validate_on_submit():
    user = User.query.filter_by(email=form.email.data.lower()).first()
    if user and user.check_password(form.password.data):
      login_user(user=user, remember=form.remember_me.data)
      session['user_email'] = user.email
      next = request.args.get('next')
      if not next or not next[0] == '/':
        next = url_for('main.index')
      return redirect(next)
    else:
      if form.create_account.data:
        # TODO: validate email
        email_exists = User.query.filter_by(email=form.email.data.lower()).first()
        if not email_exists:
          # TODO: show otp code
          new_user = User(email=form.email.data, password=form.password.data)
          db.session.add(new_user)
          # populate alerts
          alerts_conf = Alerts(new_user.id)
          db.session.add(alerts_conf)
          db.session.commit()
          # login user
          login_user(user=user, remember=form.remember_me.data)
          session['user_email'] = user.email
          flash("Logged In Successfully!", 'red')
          return redirect(url_for('main.index'))
      else:
        flash("Invalid user details.", 'red')
  return render_template('signin.html', form=form)


@bp.route('/logout')
@login_required
def logout():
  logout_user()
  return redirect(url_for('main.index'))
