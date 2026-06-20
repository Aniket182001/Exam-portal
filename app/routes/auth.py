from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from app.models.user import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, redirect to admin
    if session.get("user_id"):
        return redirect(url_for("admin_exams.list_exams"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("This account has been deactivated.", "danger")
                return redirect(url_for("auth.login"))
                
            session["user_id"] = user.id
            flash("Successfully logged in.", "success")
            
            # Redirect to originally requested page, or default to admin dashboard
            redirect_target = session.pop("post_login_redirect", url_for("admin_exams.list_exams"))
            return redirect(redirect_target)
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template("auth/login.html")

@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))
