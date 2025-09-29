from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

login_manager = LoginManager()
app = Flask(__name__)
app.config.from_object('app.config.AppConfigs')
db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager.init_app(app)
login_manager.login_view = 'login'