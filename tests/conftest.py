"""
Minimal pytest fixtures for the exam-portal test suite.

Uses an isolated in-memory SQLite database so it NEVER touches the real dev DB.
All migrations are applied fresh via flask_migrate before each test session.
"""
import os
import pytest

# Point at an in-memory SQLite BEFORE the app is created so Config picks it up.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


from app import create_app
from app.extensions import db as _db
from app.models import User
from werkzeug.security import generate_password_hash


# ── App / DB fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create a test Flask application backed by an in-memory SQLite DB."""
    _app = create_app()
    _app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SERVER_NAME=None,
    )

    with _app.app_context():
        # Apply all migrations to the in-memory DB so the schema is identical
        # to production.  We use flask_migrate so this exercises the real DDL.
        from flask_migrate import upgrade as migrate_upgrade
        migrate_upgrade()
        yield _app


@pytest.fixture(scope="session")
def db(app):
    """Return the SQLAlchemy db instance (session-scoped)."""
    yield _db


@pytest.fixture(autouse=True)
def clean_tables(db, app):
    """Rollback every test's writes so tests stay independent."""
    with app.app_context():
        yield
        db.session.rollback()


# ── HTTP client fixture ────────────────────────────────────────────────────────

@pytest.fixture
def client(app):
    return app.test_client()


# ── Admin session helper ──────────────────────────────────────────────────────

@pytest.fixture
def admin_user(db, app):
    """Create a throwaway admin user and return it."""
    with app.app_context():
        user = User(
            username="test_admin",
            email="test_admin@example.com",
            password_hash=generate_password_hash("testpass"),
            role="admin",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        # Re-query to get a fresh object inside this context
        user = User.query.filter_by(username="test_admin").first()
        yield user
        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def logged_in_client(client, admin_user, app):
    """A test client with an active admin session."""
    with client.session_transaction() as sess:
        sess["user_id"] = admin_user.id
    yield client
