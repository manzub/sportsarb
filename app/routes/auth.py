import string
import random
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.forms import LoginForm
from app.models import User, Alerts
from app.utils.email_helpers import validate_email_address, send_otp_mail, send_email
from werkzeug.security import generate_password_hash
from app.extensions import db

bp = Blueprint('auth', __name__)

def generate_otp():
  return ''.join(random.choices(string.digits, k=6))

@bp.route('/login', methods=['GET', 'POST'])
def login():
  form = LoginForm()
  if request.method == 'POST':
    if form.validate_on_submit():
      user = User.query.filter_by(email=form.email.data.lower()).first()
      if user and user.check_password(form.password.data):
        login_user(user=user, remember=form.remember_me.data)
        session['user_email'] = user.email
        next = request.args.get('next')
        if not next or not next[0] == '/':
          next = url_for('main.index')
        return redirect(next)
      elif form.create_account.data:
        email_exists = User.query.filter_by(email=form.email.data.lower()).first()
        if not email_exists:
          if validate_email_address(email=form.email.data.lower()):
            new_user = User(email=form.email.data, password=form.password.data)
            db.session.add(new_user)
            # populate alerts
            alerts_conf = Alerts(new_user.id)
            db.session.add(alerts_conf)
            db.session.commit()
            
            # otp code
            new_user.set_otp()
            send_otp_mail(new_user)
            
            session['user_email'] = new_user.email
            flash("We sent you a verification code. Please check your email.", "yellow")
            return redirect(url_for('auth.confirmation', user_id=new_user.id))
          else:
            flash('Invalid email address', 'red')
        else:
          return redirect(url_for('auth.login'))
      else:
        flash('Password is incorrect', 'red')
          
  return render_template('login.html', form=form)

@bp.route('/confirmation/<int:user_id>', methods=['GET', 'POST'])
def confirmation(user_id):
  user = User.query.get_or_404(user_id)
  if request.method == 'POST':
    code = request.form.get('otp_code')
    if user.verify_otp(code):
      flash("Email verified successfully! Welcome.", "emerald")
      login_user(user, remember=True)
      return redirect(url_for('main.index'))
    else:
      flash("Invalid or expired OTP code.", "red")
  return render_template('confirmation.html', user=user)

@bp.route('/resend-otp/<int:user_id>')
def resend_otp(user_id):
  user = User.query.get_or_404(user_id)
  user.set_otp()
  send_otp_mail(user)
  flash("A new verification code has been sent to your email.", "yellow")
  return redirect(url_for('auth.confirmation', user_id=user.id))

@bp.route('/request-password-reset', methods=['GET'])
@login_required
def request_password_reset():
  user = User.query.filter_by(email=current_user.email).first()

  if not user:
    flash('No account found with that email', 'red')
    return redirect(url_for('main.account'))

  otp = generate_otp()
  user.reset_otp = otp
  user.reset_otp_expiry = datetime.now() + timedelta(minutes=10)
  db.session.commit()

  send_email(
    to=current_user.email,
    subject='Password Reset Code',
    body=f'Your OTP for password reset is: {otp}'
  )
  
  flash('An OTP has been sent to your email address.', 'success')
  return redirect(url_for('auth.reset_password'))

@bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
  if request.method == 'POST':
    email = request.form.get('email')
    otp = request.form.get('otp_code')
    new_password = request.form.get('new_password')
  
    user = User.query.filter_by(email=email).first()

    if not user or user.reset_otp != otp:
      flash('Invalid OTP or email', 'red')
      return redirect(url_for('auth.reset_password'))

    if user.reset_otp_expiry < datetime.now():
      flash('OTP expired, please request again.', 'warning')
      return redirect(url_for('auth.reset_password'))

    user.password = generate_password_hash(new_password)
    user.reset_otp = None
    user.reset_otp_expiry = None
    db.session.commit()
    
    flash('Password reset successfully! You can now log in.', 'emerald')
    return redirect(url_for('auth.login'))

  return render_template('reset_password.html')

@bp.route('/logout')
def logout():
  logout_user()
  return redirect(url_for('main.index'))