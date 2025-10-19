from flask import Blueprint, request, jsonify
from app.extensions import redis
from app.utils.helpers import sort_surebet_data, sort_middle_data, sort_valuebets_data
from app.services.odds_service import OddsService
import json

bp = Blueprint('api', __name__)

@bp.route('/sports', methods=['GET'])
def sports():
  results = []
  odds_service = OddsService()
  sports_data = odds_service.load_offline_data()['sports']
  for item in sports_data:
    if isinstance(item, dict) and 'description' in item:
      results.append(item['description'])
    
  return jsonify({"sports":results, "total_sports": len(results)})

@bp.route('/summary', methods=['GET'])
def summary():
  key = request.args.get('key')
  if key:
    redis_key = sorted(redis.keys(f"{key}:*"))[-1] if redis.keys(f"{key}:*") else None
    if redis_key:
      data = json.loads(redis.get(redis_key))
      if data:
        return jsonify({ f"total_{key}": len(data) })
  return jsonify({})

@bp.route('/surebets')
def get_surebets():
  data = []
  keys = redis.keys('surebets:*')
  if keys:
    latest = max(keys)
    raw_data = redis.get(latest)
    data = sort_surebet_data(raw_data)
  
  # Get filters
  sort = request.args.get("sort")
  market = request.args.get("market")
  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 10))
  
  if market:
    data = [d for d in data if d.get('market_type', 'h2h') == market]
  
  if sort == "profit":
    data.sort(key=lambda x: x.get("profit", 0), reverse=True)
  elif sort == "time":
    data.sort(key=lambda x: x.get("start_time", ""), reverse=False)
  
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit

  return jsonify({ "data": data[start:end], "page": page, "total_pages": total_pages })

@bp.route('/middles')
def middles():
  data = []
  keys = redis.keys('middles:*')
  if keys:
    latest = max(keys)
    raw_data = redis.get(latest)
    data = sort_middle_data(raw_data)
  
  # Filters
  sort = request.args.get("sort")
  market = request.args.get("market")
  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 10))
  
  # Filter by market type
  if market:
    data = [d for d in data if d.get('market', 'spreads') == market]

  # Sorting logic
  if sort == "profit":
    data.sort(key=lambda x: x.get("profit", 0), reverse=True)
  elif sort == "time":
    data.sort(key=lambda x: x.get("start_time", ""), reverse=False)

  # Pagination
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit
  
  # Count positive expected value items
  total_positive_expected = len([d for d in data if d.get("expected_value", 0) > 0])

  return jsonify({ "data": data[start:end], "page": page, "total_pages": total_pages, "total_positive_expected": total_positive_expected })

@bp.route('/values')
def values():
  data = []
  keys = redis.keys('valuebets:*')
  if keys:
    latest = max(keys)
    raw_data = redis.get(latest)
    data = sort_valuebets_data(raw_data)
    
  # Filters
  sort = request.args.get("sort")
  market = request.args.get("market")
  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 10))
  
  # Filter by market type
  if market:
    data = [d for d in data if d.get('market_type', 'spread') == market]

  # Sorting logic
  if sort == "profit":
    data.sort(key=lambda x: x.get("profit", 0), reverse=True)
  elif sort == "time":
    data.sort(key=lambda x: x.get("start_time", ""), reverse=False)

  # Pagination
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit
  
  return jsonify({ "data": data[start:end], "page": page, "total_pages": total_pages })
