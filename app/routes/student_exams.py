from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.extensions import db
from app.models import Exam, StudentAttempt
from datetime import datetime, timezone
import uuid

student_exams_bp = Blueprint("student_exams", __name__)

@student_exams_bp.route("/exam/<exam_code>", methods=["GET", "POST"])
def entry(exam_code):
    exam = Exam.query.filter_by(exam_code=exam_code).first_or_404()
    
    if not exam.is_active:
        flash("This exam is currently not active.", "danger")
        return render_template("student/entry.html", exam=exam, disabled=True)
        
    now = datetime.now(timezone.utc)
    
    # Validation for exam timings
    if exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc):
        flash("This exam has not started yet.", "warning")
        return render_template("student/entry.html", exam=exam, disabled=True)
        
    if exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc):
        flash("This exam has already ended.", "danger")
        return render_template("student/entry.html", exam=exam, disabled=True)

    if request.method == "POST":
        student_name = request.form.get("student_name")
        student_email = request.form.get("student_email")
        
        if not student_name or not student_email:
            flash("Name and email are required to enter the exam.", "danger")
            return render_template("student/entry.html", exam=exam)
            
        # Store securely in session for the next steps
        session['student_name'] = student_name.strip()
        session['student_email'] = student_email.strip()
        
        return redirect(url_for('student_exams.instructions', exam_code=exam_code))

    return render_template("student/entry.html", exam=exam)

@student_exams_bp.route("/exam/<exam_code>/instructions", methods=["GET"])
def instructions(exam_code):
    exam = Exam.query.filter_by(exam_code=exam_code).first_or_404()
    
    # Ensure they came through the entry page
    if not session.get('student_name') or not session.get('student_email'):
        flash("Please enter your details first.", "warning")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
        
    now = datetime.now(timezone.utc)
    if not exam.is_active or (exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc)) or (exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc)):
        flash("This exam is currently unavailable.", "danger")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))

    return render_template("student/instructions.html", exam=exam)

@student_exams_bp.route("/exam/<exam_code>/start", methods=["POST"])
def start_exam(exam_code):
    exam = Exam.query.filter_by(exam_code=exam_code).first_or_404()
    
    student_name = session.get('student_name')
    student_email = session.get('student_email')
    
    if not student_name or not student_email:
        flash("Please enter your details first.", "warning")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
        
    now = datetime.now(timezone.utc)
    if not exam.is_active or (exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc)) or (exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc)):
        flash("This exam is currently unavailable.", "danger")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
        
    attempt_token = str(uuid.uuid4())
    
    new_attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=student_name,
        student_email=student_email,
        attempt_token=attempt_token,
        status="in_progress",
        started_at=now
    )
    
    db.session.add(new_attempt)
    db.session.commit()
    
    # Optionally clear the session if no longer needed, but keeping it might be useful
    session.pop('student_name', None)
    session.pop('student_email', None)
    
    return redirect(f"/attempt/{attempt_token}/question/1")
