import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    ADMIN_SECURITY_PIN = os.getenv("ADMIN_SECURITY_PIN", "0007")

    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "exam_portal.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Brevo SMTP Mail Settings
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in ["true", "1", "yes"]
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() in ["true", "1", "yes"]
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")  # Brevo SMTP key
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "aniket@aiqmindia.com")
    DEFAULT_SUBMISSION_NOTIFICATION_RECIPIENTS = (
        "aniket@aiqmindia.com,dskode@aiqmindia.com,edu@aiqmindia.com,ravi.k@aiqmindia.com"
    )
    EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS = os.getenv(
        "EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS",
        DEFAULT_SUBMISSION_NOTIFICATION_RECIPIENTS
    )