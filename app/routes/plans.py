import json
from datetime import datetime, timedelta
from flask import Blueprint, request, flash, redirect, url_for, render_template
from flask_login import current_user
from app.forms import SelectPlan
from app.models import Subscriptions, UserSubscriptions, AppSettings
from app.extensions import db

bp = Blueprint('plans', __name__)

@bp.route('/overview', methods=['GET', 'POST'])
def overview():
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
          end_date = datetime.utcnow() + timedelta(days=30)
          new_plan = UserSubscriptions(user_id=current_user.id, active=False, plan_id=form.plan_id.data, start_date=datetime.utcnow(), end_date=end_date)
          db.session.add(new_plan)
          db.session.commit()
          flash(f"New Plan {valid_plan.plan_name} Started", 'emerald')
          return redirect(url_for('main.account'))
      else:
        flash("Must be signed in to start a new plan", 'yellow')
        return redirect(url_for('auth.logout'))
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