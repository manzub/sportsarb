from pywebpush import webpush, WebPushException
import json
import os
from app.extensions import db


VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_CLAIMS = {"sub": "mailto:noreply@surebets.com"}

def send_webpush(subscription_info, title, body):
  try:
    webpush(
      subscription_info=subscription_info,
      data=json.dumps({"title": title, "body": body}),
      vapid_private_key=VAPID_PRIVATE_KEY,
      vapid_claims=VAPID_CLAIMS
    )
  except WebPushException as ex:
    # Chrome returns 410 or 404 when a subscription is dead
    if ex.response and ex.response.status_code in [404, 410]:
      print("Deleting expired subscription...")
      # You can either delete it here or mark inactive
      # Example:
      from app.models import Alerts
      alert = Alerts.query.filter(Alerts.webpush_info == subscription_info).first()
      if alert:
        alert.webpush_info = None
        db.session.commit()
    else:
      print("WebPush error:", repr(ex))
