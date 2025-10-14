from sqlalchemy.sql.sqltypes import DateTime
from app import db, login_manager
from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship, backref
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
  return User.query.get(int(user_id))


class User(db.Model, UserMixin):
  __tablename__ = "users"
  id = Column(Integer, primary_key=True)
  email = Column(Text, unique=True)
  password = Column(Text)
  active = Column(Boolean, default=True)
  favorite_leagues = []
  favorite_teams = []
  preferred_currency = Column(String(3), default="USD")
  current_plan = relationship('UserSubscriptions', back_populates='user', uselist=False, cascade="all, delete-orphan")
  alert_settings = relationship('Alerts', backref='users', uselist=False, cascade="all, delete-orphan")
  
  def __init__(self, email, password):
    self.email = email
    self.password = generate_password_hash(password)

  @property
  def is_active(self):
    return self.active

  def check_password(self, password):
    return check_password_hash(self.password, password)

class Subscriptions(db.Model):
  __tablename__ = "plans"
  id = Column(Integer, primary_key=True)
  plan_name = Column(Text, unique=True)
  price = Column(Float)
  stripe_price_id = Column(Text)
  duration = Column(Integer, default=30)
  # add benefits

  def to_dict(self):
    return {
      "id": self.id,
      "plan_name": self.plan_name,
      "price": self.price,
      "stripe_price_id": self.stripe_price_id,
      "duration": self.duration
    }

class UserSubscriptions(db.Model):
  __tablename__ = "subscriptions"
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'), unique=True)
  active = Column(Boolean, default=False)
  status = Column(String(50), default='pending')
  plan_id = Column(Integer, ForeignKey('plans.id'))
  start_date = Column(DateTime)
  end_date = Column(DateTime)

  user = relationship("User", back_populates="current_plan")

  def __init__(self, user_id: int, active: bool, plan_id: int, start_date: DateTime, end_date: DateTime):
    self.user_id = user_id
    self.active = active
    self.plan_id = plan_id
    self.start_date = start_date
    self.end_date = end_date

class AppSettings(db.Model):
  __tablename__ = "app_settings"
  id = Column(Integer, primary_key=True)
  setting_name = Column(Text, unique=True)
  value = Column(Text)

  def __init__(self, setting_name, value):
    self.setting_name = setting_name
    self.value = value

class Alerts(db.Model):
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  email_notify = Column(Boolean, default=False)
  favorite_leagues = Column(Boolean, default=False)
  favorite_team = Column(Boolean, default=False)

  def __init__(self, user_id):
    self.user_id = user_id

class Transactions(db.Model):
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  transaction_type = Column(Text)
  details = Column(Text)

  def __init__(self, user_id, transaction_type, details):
    self.user_id = user_id
    self.transaction_type = transaction_type
    self.details = details
