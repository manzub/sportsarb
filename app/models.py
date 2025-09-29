from datetime import datetime
from sqlalchemy.sql.sqltypes import DateTime
from app import db, login_manager
from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship, backref
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
  return User.query.get(user_id)


class User(db.Model, UserMixin):
  __tablename__ = "users"
  id = Column(Integer, primary_key=True)
  email = Column(Text, unique=True)
  password = Column(Text)
  active = Column(Boolean, default=True)
  favorite_leagues = []
  favorite_teams = []
  subscriptions = relationship('UserSubscriptions', backref='users', lazy=True, cascade="all, delete-orphan")
  alerts = relationship('Alerts', backref='users', lazy=True, cascade="all, delete-orphan")
  
  def __init__(self, email, password):
    self.email = email
    self.password = generate_password_hash(password)
    self.status = True
    self.is_active = self.status

  def check_password(self, password):
    return check_password_hash(self.password, password)

class Subscriptions(db.Model):
  __tablename__ = "plans"
  id = Column(Integer, primary_key=True)
  plan_name = Column(Text, unique=True)
  price = Column(Float)
  duration = Column(Integer, default=30)

class UserSubscriptions(db.Model):
  __tablename__ = "subscriptions"
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  active = Column(Boolean, default=False)
  plan_id = Column(Integer, ForeignKey('plans.id'))
  start_date = Column(DateTime)
  end_date = Column(DateTime)

class AppSettings(db.Model):
  __tablename__ = "app_settings"
  id = Column(Integer, primary_key=True)
  setting_name = Column(Text, unique=True)
  value = Column(Text)

class Alerts(db.Model):
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  email_notify = Column(Boolean, default=False)
  favorite_leagues = Column(Boolean, default=False)
  favorite_team = Column(Boolean, default=False)

class Transactions(db.Model):
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  transaction_type = Column(Text)
  details = Column(Text)
