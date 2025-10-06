class AppConfigs(object):
  SECRET_KEY = 'sports-arb-finder'
  SQLALCHEMY_DATABASE_URI = "postgresql://postgres:postgres@localhost:5432/sportsarb"
  SQLALCHEMY_TRACK_MODIFICATIONS = False
  pool_size = 32
  max_overflow = 64
  SITE_URL = "http://127.0.0.1:5000"
  CELERY_BROKER_URL="redis://redis:6379/0"
  CELERY_RESULT_BACKEND="redis://redis:6379/0"