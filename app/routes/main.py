from flask import Blueprint, render_template
from datetime import datetime, timezone
from app.utils.auth import login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("index.html", now=datetime.now(timezone.utc))


@main_bp.route("/portal")
@login_required
def portal_select():
    """Portal Selection Hub (Exam Portal vs LMS)."""
    return render_template("portal_select.html")