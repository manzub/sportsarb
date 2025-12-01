import string
import random
import requests
import os
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from google_auth_oauthlib.flow import Flow
from app.forms import LoginForm, ResetPassword
from app.models import User, Alerts
from app.utils.email_helpers import validate_email_address, send_otp_mail, send_email
from werkzeug.security import generate_password_hash
from app.extensions import db

bp = Blueprint('auth', __name__)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # for local dev only
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')

flow = Flow.from_client_config(
  {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uris": ["http://localhost:5001/auth/google"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
  },
  scopes=["https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile", "openid"]
)

def generate_otp():
  return ''.join(random.choices(string.digits, k=6))

@bp.route("google/login")
def google_login():
  flow.redirect_uri = url_for("auth.google_auth", _external=True)
  authorization_url, state = flow.authorization_url(
      access_type="offline",
      include_granted_scopes="true"
  )
  session["state"] = state
  return redirect(authorization_url)

@bp.route('/google')
def google_auth():
  flow.redirect_uri = url_for("auth.google_auth", _external=True)
  
  flow.fetch_token(authorization_response=request.url)
  if not session.get("state") == request.args.get("state"):
    return "Invalid state parameter", 400
  
  try:
    credentials = flow.credentials
    request_session = requests.Session()
    token_request = grequests.Request(session=request_session)

    response = request_session.get(
      "https://www.googleapis.com/oauth2/v2/userinfo",
      headers={"Authorization": f"Bearer {credentials.token}"}
    )
    user_info = response.json()
    email = user_info["email"]

    user = User.query.filter_by(email=email).first()
    if not user:
      # Create new user (no password needed)
      user = User(email=email, password=None)
      user.is_verified = True
      user.auth_provider = 'google'
      db.session.add(user)
      
      alerts_conf = Alerts(user.id)
      db.session.add(alerts_conf)
      db.session.commit()

    session['user_email'] = user.email
    login_user(user, remember=True)
    
    flash("Login successfull", "warning")
    return redirect(url_for('main.index'))

  except ValueError:
    flash("Invalid Google token", "warning")
    return redirect(url_for('auth.login'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
  if current_user.is_authenticated:
    return redirect(url_for('main.account'))
      
  form = LoginForm()
  if request.method == 'POST':
    if form.validate_on_submit():
      user = User.query.filter_by(email=form.email.data.lower()).first()
      if user:
        if user.auth_provider == 'google':
          flash('Invalid login method, Please login using google', 'warning')
          return redirect(url_for('auth.login'))
        elif user.auth_provider == 'local' and user.check_password(form.password.data):
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
            flash("We sent you a verification code. Please check your email.", "warning")
            return redirect(url_for('auth.confirmation', user_id=new_user.id))
          else:
            flash('Invalid email address', 'warning')
        else:
          return redirect(url_for('auth.login'))
      else:
        flash('Password is incorrect', 'warning')
          
  return render_template('login.html', form=form, google_client_id=GOOGLE_CLIENT_ID)

@bp.route('/confirmation/<int:user_id>', methods=['GET', 'POST'])
def confirmation(user_id):
  user = User.query.get_or_404(user_id)
  if request.method == 'POST':
    code = request.form.get('otp_code')
    if user.verify_otp(code):
      flash("Email verified successfully! Welcome.", "success")
      login_user(user, remember=True)
      return redirect(url_for('main.index'))
    else:
      flash("Invalid or expired OTP code.", "warning")
  return render_template('confirmation.html', user=user)

@bp.route('/resend-otp/<int:user_id>')
def resend_otp(user_id):
  user = User.query.get_or_404(user_id)
  user.set_otp()
  send_otp_mail(user)
  flash("A new verification code has been sent to your email.", "warning")
  return redirect(url_for('auth.confirmation', user_id=user.id))

@bp.route('/reset_password', methods=['GET','POST'])
def reset_password():
  form = ResetPassword()
  if form.validate_on_submit():
    email = form.email.data
    user = User.query.filter_by(email=email).first()

    if not user:
      flash('If the email exists, an OTP has been sent.', 'warning')
      return redirect(url_for('auth.reset_password'))

    otp = generate_otp()
    user.reset_otp = otp
    user.reset_otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.session.commit()

    send_email(
      to=user.email,
      subject='Password Reset Code',
      body=f'Your OTP for password reset is: {otp}'
    )
    
    flash('An OTP has been sent to your email address.', 'success')
    return redirect(url_for('auth.new_password'))
  return render_template('reset_password.html', form=form)

@bp.route('/new-password', methods=['GET', 'POST'])
def new_password():
  if request.method == 'POST':
    email = request.form.get('email')
    otp = request.form.get('otp_code')
    new_password = request.form.get('new_password')
  
    user = User.query.filter_by(email=email).first()

    if not user or user.reset_otp != otp:
      flash('Invalid OTP or email', 'red')
      return redirect(url_for('auth.reset_password'))

    if user.reset_otp_expiry < datetime.now(timezone.utc):
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
@login_required
def logout():
  logout_user()
  return redirect(url_for('main.index'))