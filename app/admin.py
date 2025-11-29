from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, expose
from flask_login import current_user, login_required
from flask import redirect, url_for, request, flash
from datetime import datetime, timezone
from app.extensions import redis, db
from app.models import Sports, User, AppSettings
from app.utils.helpers import to_bool, get_config_by_name
import platform, psutil


class SecureAdminIndexView(AdminIndexView):
  @expose('/')
  def index(self):
    # Restrict access
    if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
      return redirect(url_for('auth.login', next=request.url))

    # --- Basic stats ---
    total_users = User.query.count()
    total_sports = Sports.query.count()

    # Arbitrage counts per sport
    sport_stats = []
    sports = Sports.query.all()
    for s in sports:
      sport_stats.append({
        'name': s.league,
        'surebets': s.surebets or 0,
        'middles': s.middles or 0,
        'values_count': getattr(s, 'values', 0) or 0
      })

    # --- System info (server stats) ---
    sys_info = {
      "uptime": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "cpu_usage": psutil.cpu_percent(interval=0.5),
      "mem_usage": psutil.virtual_memory().percent,
      "python_version": platform.python_version(),
      "hostname": platform.node()
    }

    # --- Redis cache stats ---
    try:
      redis_info = redis.info()
      redis_status = f"Connected ({redis_info.get('connected_clients', 0)} clients)"
    except Exception:
      redis_status = "Unavailable"
      
    # --- use oddsapi state ---
    use_online_setting = get_config_by_name('finder_use_offline')

    return self.render(
      'admin/dashboard.html',
      total_users=total_users,
      total_sports=total_sports,
      sport_stats=sport_stats,
      sys_info=sys_info,
      redis_status=redis_status,
      use_online_setting=not to_bool(use_online_setting if use_online_setting else None)
    )

  @expose('/toggle-oddsapi')
  @login_required
  def toggle_oddsapi(self):
    # Restrict access
    if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
      return redirect(url_for('auth.login', next=request.url))
    
    # db toggle use_offline/save_offline
    finder_use_offline = AppSettings.query.filter_by(setting_name='finder_use_offline').first()
    finder_save_offline = AppSettings.query.filter_by(setting_name='finder_save_offline').first()
    if finder_use_offline and finder_save_offline:
      current_true_state = to_bool(finder_use_offline.value if finder_use_offline else None)
      finder_use_offline.value = not current_true_state
      finder_save_offline.value = current_true_state
      db.session.commit()
      
    flash('Toggled Use OddsAPI', 'success')
    return redirect(url_for('.index'))

  """Protects the main /admin dashboard route"""
  def is_accessible(self):
    return current_user.is_authenticated and getattr(current_user, "is_admin", False)

  def inaccessible_callback(self, name, **kwargs):
    # Redirect to login page if not authenticated or not admin
    return redirect(url_for('auth.login', next=request.url))

class AdminView(ModelView):
  def is_accessible(self):
    return current_user.is_authenticated and getattr(current_user, "is_admin", False)

  def inaccessible_callback(self, name, **kwargs):
    return redirect(url_for('auth.login', next=request.url))
  
class SportView(ModelView):
  can_delete = False
  can_create = False
