# tasks to save to redis here and run in celery
from app import create_app

app = create_app()
celery = app.celery

@celery.task
def fetch_odds_task():
  pass

celery.conf.beat_schedule = {
  'fetch-odds-every-5-minutes': {
    'task': 'app.tasks.fetch_odds_task', # task here
    'schedule': 300.0,  # 5 minutes
  },
}