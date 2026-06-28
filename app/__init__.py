from datetime import datetime, UTC
from flask import Flask
from config import Config
from app.extensions import db, migrate
from app.routes import main_bp
from zoneinfo import ZoneInfo

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
    from app.routes.admin_bp import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_exams_bp)
    app.register_blueprint(admin_questions_bp)
    app.register_blueprint(student_exams_bp)
    app.register_blueprint(admin_backup_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_current_year():
        return {
            "current_year": datetime.now(UTC).year
        }

    @app.template_filter('format_datetime_tz')
    def format_datetime_tz(dt, tz_name="Asia/Kolkata", format='%Y-%m-%d %H:%M:%S'):
        if not dt:
            return 'N/A'
        try:
            tz = ZoneInfo(tz_name)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(tz).strftime(format)
        except Exception:
            return dt.strftime(format)

    # Register CLI commands
    from app.cli import create_admin_command
    app.cli.add_command(create_admin_command)

    return app