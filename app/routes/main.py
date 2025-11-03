import json
import os
from urllib.parse import unquote
from datetime import datetime
from flask import Blueprint, render_template, flash, request, redirect, url_for, jsonify, send_from_directory, session
from app.extensions import db, redis
from flask_login import current_user, login_required
from app.models import UserSubscriptions, Subscriptions, Alerts
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


@bp.route('/')
@verified_required
def index():
  surebets = get_latest_data('surebets')
  total_surebet_items = len(surebets)
  
  active_subscription = False if not current_user.is_authenticated else has_active_subscription(current_user)
  return render_template('homepage.html', has_active_subscription=active_subscription, total_surebet_items=total_surebet_items)

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
  fav_leagues = set(current_user.favorite_leagues or [])

  for s in sports:
    s.is_favorite = s.league in fav_leagues
  return render_template('sports.html', sports=sports)

@bp.route('/bookmakers')
def bookmakers():
  return render_template('bookmakers.html')

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
    <div data-type="surebet" id="opportunity" data-profit-margin="{arb['profit_margin']}" data-total-implied-prob="{total_implied_prob}">
      <h1 class="font-bold m-0" style="font-size: 18px;">{arb['event']}</h1>
      <h2 class="text-emerald-800 font-extrabold m-0">{arb['sport_title']}</h2>
      <p>Profit Margin: <span class="font-extrabold">{arb['profit_margin']:.2f}%</span></p>
      <p class="m-0">Time: {format_date(arb['commence_time'])}</p>
      <p>Market: {arb.get('market', 'N/A').upper()}</p>
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
          <div class="bg-blue-100 p-2">
            <h3>{label}</h3>
            <p>Odds: {odd:.2f}</p>
            <p>Bookmaker: {bookmaker}</p>
            <p>Bet Amount: $<span class="bet-amount" data-implied-prob="{implied_prob}">0.00</span></p>
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
          data-away-line="{away_line}">
          
      <h1 class="font-bold text-lg">{middle.get('event')}</h1>
      <h2 class="text-emerald-800 font-extrabold">{middle.get('sport_title')}</h2>
      <p>Market: <strong>{middle.get('market', 'N/A').upper()}</strong></p>
      <p>Bookmakers: <span class="font-semibold text-blue-700">{b1}</span> & vs. <span class="font-semibold text-blue-700">{b2}</span></p>
      <p>Middle Range: <span class="font-semibold">{home_line} / {away_line}</span></p>
      
      <div class="grid grid-cols-2 gap-3 mt-3">
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h3 class="text-blue-800 font-semibold">{b1}</h3>
          <p>Line: {home_line}</p>
          <label class="text-sm text-gray-600 block">Odds:</label>
          <input type="number" step="0.01" class="input input-sm w-full odd-input" id="odd1" value="{middle['odds']['home_price']}" />
        </div>

        <div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h3 class="text-blue-800 font-semibold">{b2}</h3>
          <p>Line: {away_line}</p>
          <label class="text-sm text-gray-600 block">Odds:</label>
          <input type="number" step="0.01" class="input input-sm w-full odd-input" id="odd2" value="{middle['odds']['away_price']}" />
        </div>
      </div>
    </div>
    """
    return html_template.format(opportunity=opportunities_html)
  return "Invalid Request", 400


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