import os
from dotenv import load_dotenv
from app import app
from flask import render_template
from app.models import User

@app.route('/')
def hello_world():
    return render_template('homepage.html')

if __name__ =='__main__':
    load_dotenv()
    app.run(host="0.0.0.0", port=5111, debug=True if os.getenv('FLASK_ENV') == 'development' else False)