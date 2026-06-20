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
    from app.routes.admin_exams import admin_exams_bp
    from app.routes.admin_questions import admin_questions_bp
    from app.routes.student_exams import student_exams_bp
    from app.routes.admin_backup import admin_backup_bp
    from app.routes.auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_exams_bp)
    app.register_blueprint(admin_questions_bp)
    app.register_blueprint(student_exams_bp)
    app.register_blueprint(admin_backup_bp)

    return app