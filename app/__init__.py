from flask import Flask
from config import Config
from app.extensions import db, migrate
from app.routes import main_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models

    app.register_blueprint(main_bp)

    return app