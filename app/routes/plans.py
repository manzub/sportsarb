import json
from datetime import datetime, timedelta
from flask import Blueprint, request, flash, redirect, url_for, render_template, jsonify, session, current_app
from flask_login import current_user, login_required
from app.forms import SelectPlan
from app.models import Subscriptions, UserSubscriptions, AppSettings
from app.extensions import db, stripe

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
          end_date = datetime.now() + timedelta(days=30)
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

@bp.route('/checkout/<int:plan_id>', methods=['GET'])
def checkout(plan_id):
  return render_template('select-plan.html', plan_id=plan_id)

@bp.route('/return', methods=['GET'])
def payment_return():
  return render_template('return.html')

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
        subscription.start_date = datetime.now()
        subscription.end_date = datetime.now() + timedelta(days=30)
        db.session.commit()

  return jsonify(status=stripe_session.status, customer_email=stripe_session.customer_details.email)
