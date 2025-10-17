from flask import Blueprint, request, jsonify
from app.extensions import redis
from app.utils.helpers import sort_surebet_data

bp = Blueprint('api', __name__)

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