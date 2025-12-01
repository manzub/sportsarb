from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import redis
from app.utils.arb_helper import sort_surebet_data, sort_middle_data, sort_valuebets_data, apply_filters
from app.utils.helpers import get_config_by_name, has_active_subscription
from app.extensions import db
import json
import os

bp = Blueprint('api', __name__)

def paginate(data, page, limit):
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit
  return data[start:end], total_pages


@bp.route('/webpush/subscribe', methods=['POST'])
@login_required
def webpush_subscribe():
  from app.models import Alerts
  
  try:
    subscription_info = request.get_json()
    if not subscription_info:
      return jsonify({"error": "Missing subscription info"}), 400
    if not current_user.alert_settings:
      # Create new alert settings if not existing
      alerts = Alerts(user_id=current_user.id)
      alerts.webpush_info = subscription_info
      db.session.add(alerts)
    else:
      current_user.alert_settings.webpush_info = subscription_info
    db.session.commit()
    return jsonify({"status": "subscribed"}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"error": str(e)}), 500
  
@bp.route('/webpush/unsubscribe', methods=['POST'])
@login_required
def webpush_unsubscribe():
  if current_user.alert_settings.webpush_info:
    current_user.alert_settings.webpush_info = None
    db.session.commit()
  return jsonify({'status': 'unsubscribed'}), 200

@bp.route('/sports', methods=['GET'])
def sports():
  from app.models import Sports
  
  results = {}
  sports = Sports.query.all()
  for row in sports:
    key = row.sport
    if key not in results:
      results[key] = []
    
    results[key].append({
      "id": row.id,
      "league": row.league,
      "surebets": row.surebets,
      "middles": row.middles,
      "values": row.values,
      "last_count": row.last_count
    })
    
  return jsonify({"sports":results, "total_sports": len(results)})

@bp.route('/summary', methods=['GET'])
def summary():
  key = request.args.get('key')
  if not key:
    return jsonify({}), 400

  redis_key = f"arb:{key}"
  raw = redis.get(redis_key)
  if not raw:
    return jsonify({f"total_{key}": 0})

  try:
    data = json.loads(raw)
    if isinstance(data, dict):
      count = len(data)
    elif isinstance(data, list): 
      count = len(data)
    else:
      count = 0

    return jsonify({f"total_{key}": count})

  except Exception as e:
      print("Error parsing Redis data:", e)
      return jsonify({f"total_{key}": 0})

@bp.route('/surebets')
def get_surebets():
  data = []
  raw_data = redis.get("arb:surebets")
  if raw_data:
    # if free user show only cutoff, get config
    profit_margin_cutoff = float(get_config_by_name('free_plan_cutoff'))
    if current_user.is_authenticated and current_user.current_plan:
      profit_margin_cutoff = None
    data = sort_surebet_data(raw_data, cutoff=profit_margin_cutoff)
    
  data = apply_filters(data, request.args)

  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 51))
  data_page, total_pages = paginate(data, page, limit)

  return jsonify({
    "data": data_page,
    "page": page,
    "total_pages": total_pages
  })

@bp.route('/middles')
@login_required
def get_middles():
  data = []
  if current_user.is_authenticated and has_active_subscription(current_user):
    raw_data = redis.get("arb:middles")
    if raw_data:
      data = sort_middle_data(raw_data)
      
    data = apply_filters(data, request.args)
    
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    data_page, total_pages = paginate(data, page, limit)

  return jsonify({
    "data": data_page,
    "page": page,
    "total_pages": total_pages
  })

@bp.route('/values')
@login_required
def get_values():
  data = []
  if current_user.is_authenticated and has_active_subscription(current_user):
    raw_data = redis.get("arb:valuebets")
    if raw_data:
      data = sort_valuebets_data(raw_data)
      
    data = apply_filters(data, request.args)
    
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    data_page, total_pages = paginate(data, page, limit)

  return jsonify({
    "data": data_page,
    "page": page,
    "total_pages": total_pages
  })

@bp.route('/webpush/test', methods=['GET'])
@login_required
def webpush_test():
  from pywebpush import webpush, WebPushException
  subscription_info = current_user.alert_settings.webpush_info
  if not subscription_info:
    return jsonify({"error": "User not subscribed"}), 400

  vapid_private_key = os.getenv("VAPID_PRIVATE_KEY")

  payload = json.dumps({
    "title": "Test Notification",
    "body": "This is a test push from your Flask backend!"
  })

  try:
    webpush(
      subscription_info=subscription_info,
      data=payload,
      vapid_private_key=vapid_private_key,
      vapid_claims={"sub": "mailto:admin@yourapp.com"}
    )
    return jsonify({"status": "Notification sent!", "info": subscription_info}), 200
  except WebPushException as ex:
    print("WebPush error:", repr(ex))
    return jsonify({"error": "Push failed", "details": str(ex)}), 500
  
@bp.route('/sports/toggle-favorite', methods=['POST'])
@login_required
def toggle_favorite():
  data = request.get_json()
  league = data.get('league')
  favorite = data.get('favorite')
  user = current_user
  
  if not league:
    return jsonify({'error': 'Missing league'}), 400
  
  # ensure list exists
  if user.favorite_leagues is None:
    user.favorite_leagues = []

  # toggle logic
  if league in user.favorite_leagues:
    user.favorite_leagues.remove(league)
    action = 'removed'
  else:
    user.favorite_leagues.append(league)
    action = 'added'

  db.session.commit()
  return jsonify({'success': True, 'action': action, 'favorites': user.favorite_leagues})