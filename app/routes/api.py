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
    __data = redis.get(latest)
    data = sort_surebet_data(__data)
  
  page = int(request.args.get("page", 1))
  limit = int(request.args.get("limit", 10))
  start = (page - 1) * limit
  end = start + limit
  total_pages = (len(data) + limit - 1) // limit

  return jsonify({ "data": data[start:end], "page": page, "total_pages": total_pages })