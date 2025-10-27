import os
from dotenv import load_dotenv
from app import create_app

app = create_app()

if __name__ =='__main__':
  load_dotenv()
  app.run(host="0.0.0.0", port=5000, debug=True if os.getenv('FLASK_ENV') == 'development' else False)