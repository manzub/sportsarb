import os

sql_alchemy_url = os.getenv('DATABASE_URL', "postgresql://postgres:postgres@localhost:5437/sportsarb")
class AppConfigs(object):
  SECRET_KEY = 'sports-arb-finder'
  SQLALCHEMY_DATABASE_URI = sql_alchemy_url
  SQLALCHEMY_TRACK_MODIFICATIONS = False
  pool_size = 32
  max_overflow = 64
  MAIL_SERVER = 'smtp.gmail.com'
  MAIL_PORT = 587
  MAIL_USE_TLS = True
  MAIL_USE_SSL = False
  MAIL_USERNAME = 'hadipartiv21@gmail.com'
  MAIL_PASSWORD = 'sbuhtolkbkggvobx'