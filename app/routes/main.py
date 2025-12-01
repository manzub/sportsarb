import json
import os
from urllib.parse import unquote
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, flash, request, redirect, url_for, jsonify, send_from_directory, session
from app.extensions import db, redis
from flask_login import current_user, login_required
from app.forms import SelectPlan
from app.models import UserSubscriptions, Subscriptions, Alerts, AppSettings
from app.utils.helpers import has_active_subscription, verified_required
from app.utils.arb_helper import get_latest_data

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


@bp.route('/', methods=['GET','POST'])
@verified_required
def index():
  form = SelectPlan()
  if request.method == 'POST':
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
          end_date = datetime.now(timezone.utc) + timedelta(days=30)
          new_plan = UserSubscriptions(user_id=current_user.id, active=False, plan_id=form.plan_id.data, start_date=datetime.utcnow(), end_date=end_date)
          db.session.add(new_plan)
          db.session.commit()
          flash(f"New Plan {valid_plan.plan_name} Started", 'success')
          return redirect(url_for('main.account'))
      else:
        flash("Must be signed in to start a new plan", 'warning')
        return redirect(url_for('auth.logout'))
  plans = Subscriptions.query.all()
  plans_with_benefits = []
  if plans and len(plans) > 0:
    for x in plans:
      settings_key = f"{x.plan_name.lower()}_plan_benefit"
      benefits = AppSettings.query.filter_by(setting_name=settings_key).first()
      data = x.to_dict()
      data['benefits'] = json.loads(benefits.value) if benefits and benefits.value else []
      plans_with_benefits.append(data)
  else:
    return redirect(url_for('main.index'))
  
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('homepage.html', has_active_subscription=active_subscription, plans=plans_with_benefits, form=form)

@bp.route('/faq')
def frequently_asked():
  return render_template('faq.html')

@bp.route('/service-worker.js')
def service_worker():
  return send_from_directory('static', 'service-worker.js', mimetype="application/javascript")

@bp.route('/sports')
def sports():
  from app.models import Sports
  
  sports = Sports.query.order_by(Sports.sport.asc(), Sports.league.asc()).all()
  fav_leagues = set(current_user.favorite_leagues or []) if current_user.is_authenticated else set([])

  for s in sports:
    s.is_favorite = s.league in fav_leagues
  return render_template('sports.html', sports=sports)

@bp.route('/bookmakers')
def bookmakers():
  return render_template('bookmakers.html')

@bp.route('/surebets')
def surebets():
  surebets = get_latest_data('surebets')
  total_surebet_items = len(surebets)
  
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('surebets.html', has_active_subscription=active_subscription, total_surebet_items=total_surebet_items)

# TODO: middles and values on if has active plan
@bp.route('/middles')
def middles():
  middles = get_latest_data('middles')
  total_middle_items = len(middles)
  total_items_with_positive_ev = sum( 1 for item in middles if (item.get('expected_value') or 0) > 0)
    
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('middles.html', has_active_subscription=active_subscription, total_middle_items=total_middle_items, total_items_with_positive_ev=total_items_with_positive_ev)

@bp.route('/valuebets')
def valuebets():
  values = get_latest_data('valuebets')
  total_value_items = len(values)
  
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('valuebets.html', has_active_subscription=active_subscription, total_value_items=total_value_items)

@bp.route('/change_currency', methods=['POST'])
def change_currency():
  currency = request.form.get('currency')
  if currency:
    if current_user and current_user.is_authenticated:
      current_user.preferred_currency = currency
      db.session.commit()
      flash(f"Preferred currency changed to {currency}", 'emerald')
    session['preferred_currency'] = currency
    return redirect(request.referrer or url_for('main.index'))

@bp.route('/surebet/calculator')
def bet_calculator():
  html_template = """{opportunity}"""
  opportunities_html = ""
  
  arb_filter = unquote(request.args.get('arb_item'))
  if arb_filter:
    # get redis arb items
    latest_keys = redis.keys("surebets:*")
    if not latest_keys:
      return "No Surebets available", 404
    
    latest = max(latest_keys)
    data = redis.get(latest)
    if not data:
      return "No data found", 404
    
    results = [x for x in json.loads(data) if x['unique_id'] == arb_filter]
    if not results:
      return "Arb item not found or expired", 404
    
    arb = results[0]
    total_implied_prob = sum(1/odd for odd in list(arb['best_odds'].values()))
    
    opportunities_html += f"""
    <div id="opportunity"
        data-type="surebet"
        data-profit-margin="{arb['profit_margin']}"
        data-total-implied-prob="{total_implied_prob}"
        class="w-full">

      <h1 class="text-2xl font-bold text-gray-900">{arb['event']}</h1>
      <h2 class="text-emerald-700 text-lg font-semibold">{arb['sport_title']}</h2>

      <div class="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
        <p><span class="font-semibold">Profit Margin:</span> {arb['profit_margin']:.2f}%</p>
        <p><span class="font-semibold">Time:</span> {format_date(arb['commence_time'])}</p>
        <p><span class="font-semibold">Market:</span> {arb.get('market', 'N/A').upper()}</p>
        {"<p><span class='font-semibold'>Points:</span> " + str(arb.get('points')) + "</p>" if arb.get('market') in ['spreads','totals'] else ""}
      </div>

      <div class="odds grid grid-cols-1 gap-4 mt-5">
    """
    
    if arb.get('market') == 'spreads':
      opportunities_html += f"<p>Points Spread: {arb.get('points', 'N/A')}</p>"
    elif arb.get('market') == 'totals':
      opportunities_html += f"<p>Total Points: {arb.get('points', 'N/A')}</p>"
      
    opportunities_html += '<div class="odds grid grid-cols-2 gap-2">'
    
    for outcome, odd in arb['best_odds'].items():
      if outcome != 'spread':  # Skip the spread key when displaying odds
        bookmaker = arb['bookmakers'][outcome]
        implied_prob = 1 / odd
        
        if arb.get('market') == 'spreads':
          spread = f"+{arb['points']}" if outcome == 'Underdog' else f"-{arb['points']}"
          label = f"{outcome} ({spread})"
        else:
          label = outcome
          
        opportunities_html += f"""
          <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <h3 class="font-semibold text-gray-800">{label}</h3>
            <p class="text-sm text-gray-700">Odds: <span class="font-medium">{odd:.2f}</span></p>
            <p class="text-sm text-gray-700">Bookmaker: {bookmaker}</p>
            <p class="text-sm mt-1">Bet Amount: $<span class="bet-amount font-bold" data-implied-prob="{implied_prob}">0.00</span></p>
          </div>
        """
    
    opportunities_html += '</div>'
    return html_template.format(opportunity=opportunities_html)
  return "Invalid request", 400

@bp.route('/middle/calculator')
def middle_calculator():
  html_template = """{opportunity}"""
  opportunities_html = ""

  middle_filter = unquote(request.args.get('middle_item'))
  if middle_filter:
    latest_keys = redis.keys("middles:*")
    if not latest_keys:
      return "No middles available", 404
    
    latest = max(latest_keys)
    data = redis.get(latest)
    if not data:
      return "No data found", 404
    
    results = [x for x in json.loads(data) if x['unique_id'] == middle_filter]

    if not results:
      return "Middle item not found or expired", 404
    middle = results[0]
    b1, b2 = middle['bookmakers']['bookmaker1'], middle['bookmakers']['bookmaker2']
    home_line, away_line = middle['lines']['home_line'], middle['lines']['away_line']

    opportunities_html += f"""
    <div id="opportunity"
        data-type="middle"
        data-bookmaker1="{b1}"
        data-bookmaker2="{b2}"
        data-home-line="{home_line}"
        data-away-line="{away_line}"
        class="bg-gray-800 border border-gray-700 rounded-xl p-5 mb-6 shadow-md">

      <h1 class="font-bold text-xl text-white">{middle.get('event')}</h1>
      <h2 class="text-emerald-400 font-semibold mt-1">{middle.get('sport_title')}</h2>

      <div class="mt-3 text-gray-300 space-y-1">
        <p>Market: <strong class="text-white">{middle.get('market', 'N/A').upper()}</strong></p>
        <p>Bookmakers:
          <span class="font-semibold text-emerald-400">{b1}</span> vs.
          <span class="font-semibold text-emerald-400">{b2}</span>
        </p>
        <p>Middle Range:
          <span class="font-semibold text-white">{home_line} / {away_line}</span>
        </p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-5">
        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <h3 class="text-emerald-300 font-semibold">{b1}</h3>
          <p class="text-gray-400">Line: {home_line}</p>

          <label class="text-sm text-gray-500 block mt-2">Odds:</label>
          <input type="number"
                step="0.01"
                class="w-full bg-gray-800 border border-gray-600 text-white rounded-md px-3 py-2 mt-1 odd-input focus:ring-emerald-500 focus:border-emerald-500"
                id="odd1"
                value="{middle['odds']['home_price']}" />
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <h3 class="text-emerald-300 font-semibold">{b2}</h3>
          <p class="text-gray-400">Line: {away_line}</p>

          <label class="text-sm text-gray-500 block mt-2">Odds:</label>
          <input type="number"
                step="0.01"
                class="w-full bg-gray-800 border border-gray-600 text-white rounded-md px-3 py-2 mt-1 odd-input focus:ring-emerald-500 focus:border-emerald-500"
                id="odd2"
                value="{middle['odds']['away_price']}" />
        </div>
      </div>
    </div>
    """

    return html_template.format(opportunity=opportunities_html)
  return "Invalid Request", 400

@bp.route('/valuebet/calculator')
def valuebet_calculator():
  html_template = """{opportunity}"""
  opportunities_html = ""

  value_id = unquote(request.args.get('value_item'))
  if not value_id:
    return "Invalid Request", 400

  # Pull Redis key
  latest_keys = redis.keys("valuebets:*")
  if not latest_keys:
    return "No Valuebets available", 404
  
  latest = max(latest_keys)
  data = redis.get(latest)
  if not data:
    return "No data found", 404
  
  results = [x for x in json.loads(data) if x['unique_id'] == value_id]
  if not results:
    return "Valuebet item not found or expired", 404
  
  vb = results[0]

  # Variables
  odds = vb['odds']
  ev_percent = vb['expected_value']  # stored as %
  confidence = vb.get('confidence', None)

  opportunities_html += f"""
  <div id="opportunity"
    data-type="valuebet"
    data-odds="{odds}"
    data-ev="{ev_percent}"
    data-confidence="{confidence}">
        
    <h1 class="font-bold text-lg">{vb['event']}</h1>
    <h2 class="text-emerald-800 font-extrabold">{vb['sport_title']}</h2>

    <p><strong>Market:</strong> {vb['market'].upper()}</p>
    <p><strong>Outcome:</strong> {vb['team_or_outcome']}</p>
    <p><strong>Bookmaker:</strong> {vb['bookmaker']}</p>
    <p><strong>Odds:</strong> {odds:.2f}</p>
    <p><strong>EV:</strong> {ev_percent:.2f}%</p>
    <p><strong>Confidence:</strong> {confidence:.2f}</p>
    <p class="m-0">Time: {format_date(vb['commence_time'])}</p>
  </div>
  """

  return html_template.format(opportunity=opportunities_html)
  

@bp.route('/account')
@login_required
@verified_required
def account():
  plan, user_subscription = None, None
  user_subscription = UserSubscriptions.query.filter_by(user_id=current_user.id).first()
  if user_subscription:
    plan = Subscriptions.query.filter_by(id=user_subscription.plan_id).first()
    
  # Ensure alert settings exist
  alerts = current_user.alert_settings
  if not alerts:
    alerts = Alerts(user_id=current_user.id)
    db.session.add(alerts)
    db.session.commit()
    
  return render_template('account.html', plan=plan, subscription=user_subscription, alerts=alerts, VAPID_PUBLIC_KEY=os.getenv('VAPID_PUBLIC_KEY'))

@bp.route('/account/notifications/email', methods=['POST'])
@login_required
def update_email_notification():
  data = request.get_json()
  enabled = bool(data.get("enabled"))
  alerts = current_user.alert_settings
  alerts.email_notify = enabled
  db.session.commit()
  return jsonify({"status": "ok", "email_notify": enabled})