from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import Exam
from datetime import datetime

admin_exams_bp = Blueprint("admin_exams", __name__, url_prefix="/admin/exams")

@admin_exams_bp.route("/")
def list_exams():
    exams = Exam.query.order_by(Exam.created_at.desc()).all()
    return render_template("admin/exams/list.html", exams=exams)

@admin_exams_bp.route("/create", methods=["GET", "POST"])
def create_exam():
    if request.method == "POST":
        title = request.form.get("title")
        exam_code = request.form.get("exam_code")
        description = request.form.get("description")
        duration_minutes = request.form.get("duration_minutes")
        passing_type = request.form.get("passing_type")
        passing_value = request.form.get("passing_value")
        negative_marking_enabled = request.form.get("negative_marking_enabled") == 'on'
        negative_marks = request.form.get("negative_marks", 0)
        show_result_immediately = request.form.get("show_result_immediately") == 'on'
        start_datetime = request.form.get("start_datetime")
        end_datetime = request.form.get("end_datetime")
        is_active = request.form.get("is_active") == 'on'

        instructions = request.form.get("instructions")
        show_question_numbers = request.form.get("show_question_numbers") == 'on'
        allow_question_navigation = request.form.get("allow_question_navigation") == 'on'
        show_progress_bar = request.form.get("show_progress_bar") == 'on'
        auto_submit_on_timeout = request.form.get("auto_submit_on_timeout") == 'on'

        # Basic Validation
        if not title or not exam_code or not duration_minutes or not passing_type or not passing_value:
            flash("Please fill out all required fields.", "danger")
            return render_template("admin/exams/form.html", action="Create")

        # Check for unique exam_code
        existing_exam = Exam.query.filter_by(exam_code=exam_code).first()
        if existing_exam:
            flash("Exam Code already exists. Please choose a different one.", "danger")
            return render_template("admin/exams/form.html", action="Create")

        # Parse dates if provided
        start_dt = datetime.fromisoformat(start_datetime) if start_datetime else None
        end_dt = datetime.fromisoformat(end_datetime) if end_datetime else None

        new_exam = Exam(
            title=title,
            exam_code=exam_code,
            description=description,
            duration_minutes=int(duration_minutes),
            passing_type=passing_type,
            passing_value=float(passing_value),
            negative_marking_enabled=negative_marking_enabled,
            negative_marks=float(negative_marks) if negative_marks else 0.0,
            show_result_immediately=show_result_immediately,
            instructions=instructions,
            show_question_numbers=show_question_numbers,
            allow_question_navigation=allow_question_navigation,
            show_progress_bar=show_progress_bar,
            auto_submit_on_timeout=auto_submit_on_timeout,
            start_datetime=start_dt,
            end_datetime=end_dt,
            is_active=is_active
        )

        db.session.add(new_exam)
        db.session.commit()
        flash("Exam created successfully.", "success")
        return redirect(url_for("admin_exams.list_exams"))

    return render_template("admin/exams/form.html", action="Create")

@admin_exams_bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit_exam(id):
    exam = Exam.query.get_or_404(id)
    if request.method == "POST":
        title = request.form.get("title")
        exam_code = request.form.get("exam_code")
        
        # Check uniqueness of exam_code if changed
        if exam_code != exam.exam_code:
            existing_exam = Exam.query.filter_by(exam_code=exam_code).first()
            if existing_exam:
                flash("Exam Code already exists. Please choose a different one.", "danger")
                return render_template("admin/exams/form.html", action="Edit", exam=exam)
            exam.exam_code = exam_code

        exam.title = title
        exam.description = request.form.get("description")
        exam.duration_minutes = int(request.form.get("duration_minutes") or 0)
        exam.passing_type = request.form.get("passing_type")
        exam.passing_value = float(request.form.get("passing_value") or 0.0)
        exam.negative_marking_enabled = request.form.get("negative_marking_enabled") == 'on'
        exam.negative_marks = float(request.form.get("negative_marks") or 0.0)
        exam.show_result_immediately = request.form.get("show_result_immediately") == 'on'
        
        exam.instructions = request.form.get("instructions")
        exam.show_question_numbers = request.form.get("show_question_numbers") == 'on'
        exam.allow_question_navigation = request.form.get("allow_question_navigation") == 'on'
        exam.show_progress_bar = request.form.get("show_progress_bar") == 'on'
        exam.auto_submit_on_timeout = request.form.get("auto_submit_on_timeout") == 'on'

        start_datetime = request.form.get("start_datetime")
        end_datetime = request.form.get("end_datetime")
        exam.start_datetime = datetime.fromisoformat(start_datetime) if start_datetime else None
        exam.end_datetime = datetime.fromisoformat(end_datetime) if end_datetime else None
        
        exam.is_active = request.form.get("is_active") == 'on'

        db.session.commit()
        flash("Exam updated successfully.", "success")
        return redirect(url_for("admin_exams.list_exams"))

    return render_template("admin/exams/form.html", action="Edit", exam=exam)

@admin_exams_bp.route("/<int:id>/toggle", methods=["POST"])
def toggle_exam(id):
    exam = Exam.query.get_or_404(id)
    exam.is_active = not exam.is_active
    db.session.commit()
    status = "activated" if exam.is_active else "deactivated"
    flash(f"Exam '{exam.title}' has been {status}.", "success")
    return redirect(url_for("admin_exams.list_exams"))
