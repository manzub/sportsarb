class AppConfigs(object):
  SECRET_KEY = 'sports-arb-finder'
  SQLALCHEMY_DATABASE_URI = "postgresql://postgres:postgres@localhost:5437/sportsarb"
  SQLALCHEMY_TRACK_MODIFICATIONS = False
  pool_size = 32
  max_overflow = 64
  SITE_URL = "http://localhost:5001"
  broker_url = "redis://redis:6379/0"
  result_backend = "redis://redis:6379/0"
  MAIL_SERVER = 'smtp.gmail.com'
  MAIL_PORT = 587
  MAIL_USE_TLS = True
  MAIL_USE_SSL = False
  MAIL_USERNAME = 'hadipartiv21@gmail.com'
  MAIL_PASSWORD = 'sbuhtolkbkggvobx'