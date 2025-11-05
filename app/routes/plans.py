import json
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, flash, redirect, url_for, render_template, jsonify, session, current_app
from flask_login import current_user, login_required
from app.forms import SelectPlan
from app.models import Subscriptions, UserSubscriptions, AppSettings, Transactions
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
          end_date = datetime.now(timezone.utc) + timedelta(days=30)
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
      data['benefits'] = json.loads(benefits.value) if benefits and benefits.value else []
      plans_with_benefits.append(data)
  else:
    return redirect(url_for('main.index'))
    
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
    plan_id = post_data.get('plan_id') or session.get('plan_id')
    if not plan_id:
      raise Exception("Missing plan_id")

    data = UserSubscriptions.query.filter_by(id=plan_id).first()
    if not data:
      raise Exception("Subscription not found")

    plan = Subscriptions.query.filter_by(id=data.plan_id).first()
    if not plan or not plan.stripe_price_id:
      raise Exception("Invalid plan or missing stripe price id")

    session['plan_id'] = plan_id

    stripe_session = stripe.checkout.Session.create(
      ui_mode='embedded',
      line_items=[{'price': plan.stripe_price_id, 'quantity': 1}],
      metadata={"plan_id": plan_id, "user_id": current_user.id},
      mode='subscription',
      return_url=current_app.config['SITE_URL'] + "/plans/return?session_id={CHECKOUT_SESSION_ID}",
      automatic_tax={'enabled': True}
    )

    return jsonify(clientSecret=stripe_session.client_secret)
  except Exception as e:
    print("Stripe error:", e)
    return jsonify(error=str(e)), 400

@bp.route('/session-status', methods=['GET'])
@login_required
def session_status():
  try:
    session_id = request.args.get('session_id')
    if not session_id:
      return jsonify(error="Missing session_id"), 400

    stripe_session = stripe.checkout.Session.retrieve(session_id)

    # Confirm payment really succeeded
    if stripe_session.payment_status == 'paid' and stripe_session.status == 'complete':
      plan_id = stripe_session.metadata.get('plan_id')
      user_id = int(stripe_session.metadata.get('user_id'))

      # Check if the user subscription exists
      subscription = UserSubscriptions.query.filter_by(id=plan_id, user_id=user_id).first()
      if subscription and not subscription.active:
          subscription.status = 'active'
          subscription.active = True
          subscription.start_date = datetime.now(timezone.utc)
          subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)
          db.session.add(subscription)

      # Log to Transactions table
      transaction = Transactions(
          user_id=user_id,
          transaction_type="subscription_payment",
          details=json.dumps({
              "session_id": stripe_session.id,
              "amount_total": stripe_session.amount_total,
              "currency": stripe_session.currency,
              "plan_id": plan_id,
              "status": stripe_session.payment_status,
              "customer_email": stripe_session.customer_details.email if stripe_session.customer_details else None
          })
      )
      db.session.add(transaction)
      db.session.commit()

      return jsonify(
          status="success",
          message="Payment confirmed and subscription activated",
          customer_email=stripe_session.customer_details.email
      )
    else:
      # Handle unpaid/incomplete states
      return jsonify(status=stripe_session.status, payment_status=stripe_session.payment_status)

  except Exception as e:
    print("Error confirming session:", e)
    return jsonify(error=str(e)), 500