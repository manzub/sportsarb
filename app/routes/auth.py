from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user
from app.forms import LoginForm
from app.models import User, Alerts
from app.utils.helpers import validate_email_address
from app.extensions import db

bp = Blueprint('auth', __name__)

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
            # TODO: show otp code
            new_user = User(email=form.email.data, password=form.password.data)
            db.session.add(new_user)
            # populate alerts
            alerts_conf = Alerts(new_user.id)
            db.session.add(alerts_conf)
            db.session.commit()
            # login user
            login_user(user=user, remember=form.remember_me.data)
            session['user_email'] = user.email
            flash("Logged In Successfully!", 'red')
            return redirect(url_for('main.index'))
          else:
            flash('Invalid email address', 'red')
        else:
          return redirect(url_for('auth.login'))
          
  return render_template('login.html', form=form)

@bp.route('/logout')
def logout():
  logout_user()
  return redirect(url_for('main.index'))