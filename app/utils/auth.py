from functools import wraps
from flask import session, redirect, url_for, request, abort, flash
from app.models.user import User

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            session["post_login_redirect"] = request.url
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login"))
            
        user = User.query.get(user_id)
        if not user or not user.is_active:
            session.pop("user_id", None)
            flash("Your account is inactive or has been removed.", "danger")
            return redirect(url_for("auth.login"))
            
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            session["post_login_redirect"] = request.url
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("auth.login"))
            
        user = User.query.get(user_id)
        if not user or not user.is_active:
            session.pop("user_id", None)
            flash("Your account is inactive or has been removed.", "danger")
            return redirect(url_for("auth.login"))
            
        if user.role != "admin":
            abort(403)
            
        return f(*args, **kwargs)
    return decorated_function
