from wtforms import SubmitField, PasswordField, StringField, ValidationError, BooleanField, HiddenField, SelectField
from wtforms.validators import DataRequired, Email
from flask_wtf import FlaskForm
from app.models import User

class LoginForm(FlaskForm):
  email = StringField('Email', validators=[DataRequired(), Email()])
  password = PasswordField('Password', validators=[DataRequired()])
  remember_me = BooleanField('Remember Me', default=False)
  create_account = BooleanField('Create an account?', default=True)
  submit = SubmitField('Continue with Email')

  def check_email(self, field):
    if User.query.filter_by(email=field.data).first():
      raise ValidationError("Email already exists")
    
class SelectPlan(FlaskForm):
  plan_id = StringField('Plan Id')
  submit = SubmitField('Choose')
  
class ResetPassword(FlaskForm):
  email = StringField('Email', validators=[DataRequired(), Email()])
  submit = SubmitField('Submit')

class CurrencyForm(FlaskForm):
  currency = SelectField(
    'Preferred Currency',
    choices=[('USD', 'USD'), ('GBP', 'GBP'), ('EUR', 'EUR'), ('NGN', 'NGN')],
  )
  submit = SubmitField('Update')