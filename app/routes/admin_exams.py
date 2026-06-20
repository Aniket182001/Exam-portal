from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from app.extensions import db
from app.models import Exam, StudentAttempt, Question, QuestionOption, StudentAnswer
from datetime import datetime
import io
import openpyxl
import uuid
from app.services.email_templates import generate_result_email

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
        restrict_to_time_window = request.form.get("restrict_to_time_window") == 'on'
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
            restrict_to_time_window=restrict_to_time_window,
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

        exam.restrict_to_time_window = request.form.get("restrict_to_time_window") == 'on'
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

@admin_exams_bp.route("/<int:exam_id>/duplicate", methods=["POST"])
def duplicate_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    
    # Duplicate exam
    new_exam = Exam(
        title=f"Copy of {exam.title}",
        exam_code=f"COPY-{uuid.uuid4().hex[:8].upper()}",
        description=exam.description,
        instructions=exam.instructions,
        duration_minutes=exam.duration_minutes,
        passing_type=exam.passing_type,
        passing_value=exam.passing_value,
        show_question_numbers=exam.show_question_numbers,
        allow_question_navigation=exam.allow_question_navigation,
        show_progress_bar=exam.show_progress_bar,
        auto_submit_on_timeout=exam.auto_submit_on_timeout,
        negative_marking_enabled=exam.negative_marking_enabled,
        negative_marks=exam.negative_marks,
        show_result_immediately=exam.show_result_immediately,
        restrict_to_time_window=exam.restrict_to_time_window,
        start_datetime=exam.start_datetime,
        end_datetime=exam.end_datetime,
        is_active=False
    )
    db.session.add(new_exam)
    db.session.flush()

    # Duplicate questions
    questions = Question.query.filter_by(exam_id=exam.id).all()
    for q in questions:
        new_q = Question(
            exam_id=new_exam.id,
            question_text=q.question_text,
            marks=q.marks,
            display_order=q.display_order
        )
        db.session.add(new_q)
        db.session.flush()

        options = QuestionOption.query.filter_by(question_id=q.id).all()
        for o in options:
            new_o = QuestionOption(
                question_id=new_q.id,
                option_text=o.option_text,
                display_order=o.display_order
            )
            db.session.add(new_o)
            db.session.flush()
            if o.id == q.correct_option_id:
                new_q.correct_option_id = new_o.id
                
    db.session.commit()
    flash(f"Exam duplicated successfully as '{new_exam.title}'.", "success")
    return redirect(url_for('admin_exams.list_exams'))

@admin_exams_bp.route("/<int:exam_id>/delete", methods=["POST"])
def delete_exam(exam_id):
    if not session.get("sensitive_action_verified"):
        session["post_verification_redirect"] = url_for('admin_exams.list_exams')
        return redirect(url_for('admin_backup.auth'))
        
    exam = Exam.query.get_or_404(exam_id)
    
    # 1. Delete StudentAnswers and Attempts
    attempts = StudentAttempt.query.filter_by(exam_id=exam.id).all()
    attempt_ids = [a.id for a in attempts]
    if attempt_ids:
        StudentAnswer.query.filter(StudentAnswer.attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
        StudentAttempt.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)

    # 2. Delete QuestionOptions and Questions
    questions = Question.query.filter_by(exam_id=exam.id).all()
    question_ids = [q.id for q in questions]
    if question_ids:
        QuestionOption.query.filter(QuestionOption.question_id.in_(question_ids)).delete(synchronize_session=False)
        Question.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)

    # 3. Delete Exam
    db.session.delete(exam)
    db.session.commit()
    
    flash("Exam deleted successfully.", "success")
    return redirect(url_for('admin_exams.list_exams'))

@admin_exams_bp.route("/<int:exam_id>/attempts")
def view_attempts(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # Order by submitted_at desc, but some might be null (in_progress).
    attempts = StudentAttempt.query.filter_by(exam_id=exam.id).order_by(StudentAttempt.submitted_at.desc()).all()
    return render_template("admin/exams/attempts.html", exam=exam, attempts=attempts)

@admin_exams_bp.route("/<int:exam_id>/export-results")
def export_results(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    attempts = StudentAttempt.query.filter_by(exam_id=exam.id).order_by(StudentAttempt.submitted_at.desc()).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"
    
    headers = [
        "Student Name", "Student Email", "Attempt Status", 
        "Marks Obtained", "Percentage Score", "Correct Answers", 
        "Wrong Answers", "Unanswered Questions", "Pass/Fail Status", "Submitted At"
    ]
    ws.append(headers)
    
    for attempt in attempts:
        row = [
            attempt.student_name,
            attempt.student_email,
            attempt.status.title(),
            attempt.total_marks_obtained if attempt.total_marks_obtained is not None else "-",
            f"{attempt.percentage_score:.1f}%" if attempt.percentage_score is not None else "-",
            attempt.correct_count if attempt.correct_count is not None else "-",
            attempt.wrong_count if attempt.wrong_count is not None else "-",
            attempt.unanswered_count if attempt.unanswered_count is not None else "-",
            attempt.result_status if attempt.result_status is not None else "-",
            attempt.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if attempt.submitted_at else "-"
        ]
        ws.append(row)
        
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    
    filename = f"{exam.exam_code}_results.xlsx"
    return send_file(out, download_name=filename, as_attachment=True)

@admin_exams_bp.route("/<int:exam_id>/export-selected-results", methods=["POST"])
def export_selected_results(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    attempt_ids = request.form.getlist("attempt_ids")
    
    if not attempt_ids:
        flash("Please select at least one attempt.", "warning")
        return redirect(url_for('admin_exams.view_attempts', exam_id=exam.id))
        
    attempts = StudentAttempt.query.filter(
        StudentAttempt.exam_id == exam.id,
        StudentAttempt.id.in_(attempt_ids)
    ).order_by(StudentAttempt.submitted_at.desc()).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"
    
    headers = [
        "Student Name", "Student Email", "Attempt Status", 
        "Marks Obtained", "Percentage Score", "Correct Answers", 
        "Wrong Answers", "Unanswered Questions", "Pass/Fail Status", "Submitted At"
    ]
    ws.append(headers)
    
    for attempt in attempts:
        row = [
            attempt.student_name,
            attempt.student_email,
            attempt.status.title(),
            attempt.total_marks_obtained if attempt.total_marks_obtained is not None else "-",
            f"{attempt.percentage_score:.1f}%" if attempt.percentage_score is not None else "-",
            attempt.correct_count if attempt.correct_count is not None else "-",
            attempt.wrong_count if attempt.wrong_count is not None else "-",
            attempt.unanswered_count if attempt.unanswered_count is not None else "-",
            attempt.result_status if attempt.result_status is not None else "-",
            attempt.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if attempt.submitted_at else "-"
        ]
        ws.append(row)
        
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    
    filename = f"{exam.exam_code}_results.xlsx"
    return send_file(out, download_name=filename, as_attachment=True)

@admin_exams_bp.route("/attempts/<int:attempt_id>/compose-email")
def compose_result_email(attempt_id):
    attempt = StudentAttempt.query.get_or_404(attempt_id)
    
    # Calculate total marks from questions
    total_marks = sum([q.marks for q in attempt.exam.questions])
    
    email_data = generate_result_email(attempt, total_marks)
    
    return render_template("admin/attempts/compose_email.html", 
                           attempt=attempt, 
                           email_data=email_data)
