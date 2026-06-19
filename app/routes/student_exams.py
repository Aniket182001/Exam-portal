from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from app.extensions import db
from app.models import Exam, StudentAttempt, Question, QuestionOption, StudentAnswer
from datetime import datetime, timezone, timedelta
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

def get_remaining_seconds(attempt):
    now = datetime.now(timezone.utc)
    started_at_utc = attempt.started_at.replace(tzinfo=timezone.utc)
    end_time = started_at_utc + timedelta(minutes=attempt.exam.duration_minutes)
    remaining = int((end_time - now).total_seconds())
    return max(0, remaining)

def handle_attempt_timeout(attempt):
    exam = attempt.exam
    now = datetime.now(timezone.utc)
    if exam.auto_submit_on_timeout:
        attempt.status = "submitted"
        attempt.submitted_at = now
        db.session.commit()
        flash("Your time has expired. Your exam has been automatically submitted.", "warning")
    else:
        attempt.status = "expired"
        db.session.commit()
        flash("Your time has expired. This exam attempt has expired.", "danger")

@student_exams_bp.route("/attempt/<attempt_token>/question/<int:question_number>", methods=["GET", "POST"])
def question_attempt(attempt_token, question_number):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    
    if attempt.status != "in_progress":
        abort(403, description="This attempt is no longer active.")
        
    exam = attempt.exam
    
    # Calculate time remaining Authoritatively using helper
    remaining_seconds = get_remaining_seconds(attempt)
    
    # Server-side Expiration Check
    if remaining_seconds == 0:
        handle_attempt_timeout(attempt)
        return redirect(f"/attempt/{attempt_token}/review")
        
    # Fetch questions ordered by display_order ASC
    questions = Question.query.filter_by(exam_id=exam.id).order_by(Question.display_order.asc()).all()
    total_questions = len(questions)
    
    # Boundary validation
    if question_number < 1 or question_number > total_questions:
        abort(404, description="Question not found.")
        
    current_question = questions[question_number - 1]
    
    if request.method == "POST":
        # Check if they clicked clear_response
        if "clear_response" in request.form:
            existing_answer = StudentAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=current_question.id
            ).first()
            if existing_answer:
                db.session.delete(existing_answer)
                db.session.commit()
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number))
            
        # Get selected option ID
        option_id_str = request.form.get("option_id")
        
        if option_id_str:
            try:
                option_id = int(option_id_str)
            except ValueError:
                abort(400, description="Invalid option structure.")
                
            # Verify the option belongs to the current question
            valid_option = any(opt.id == option_id for opt in current_question.options)
            if not valid_option:
                abort(400, description="Selected option does not belong to this question.")
                
            existing_answer = StudentAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=current_question.id
            ).first()
            
            if existing_answer:
                existing_answer.selected_option_id = option_id
            else:
                new_answer = StudentAnswer(
                    attempt_id=attempt.id,
                    question_id=current_question.id,
                    selected_option_id=option_id
                )
                db.session.add(new_answer)
                
            db.session.commit()
        
        # Navigation
        action = request.form.get("action")
        goto_question = request.form.get("goto_question")
        
        if goto_question:
            try:
                target_q = int(goto_question)
                if 1 <= target_q <= total_questions:
                    return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=target_q))
                else:
                    abort(400, description="Sidebar target question out of range.")
            except ValueError:
                abort(400, description="Invalid sidebar target question.")
                
        if action == "prev" and question_number > 1:
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number - 1))
        elif action == "next" and question_number < total_questions:
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number + 1))
        elif action == "finish" and question_number == total_questions:
            return redirect(f"/attempt/{attempt_token}/review")
        else:
            # Fallback if no action or out-of-bounds sequential navigation
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number))
            
    # GET logic
    # Fetch existing answer for pre-selection
    existing_answer = StudentAnswer.query.filter_by(
        attempt_id=attempt.id,
        question_id=current_question.id
    ).first()
    
    answered_option_id = existing_answer.selected_option_id if existing_answer else None
    
    # Calculate progress bar percentage
    progress = (question_number / total_questions) * 100 if total_questions > 0 else 0
    
    # Gather set of answered question IDs for sidebar color highlight
    answered_question_ids = {ans.question_id for ans in attempt.answers}
    
    return render_template(
        "student/question.html",
        exam=exam,
        attempt_token=attempt_token,
        question=current_question,
        question_number=question_number,
        total_questions=total_questions,
        answered_option_id=answered_option_id,
        progress=progress,
        questions=questions,
        answered_question_ids=answered_question_ids,
        remaining_seconds=remaining_seconds
    )

@student_exams_bp.route("/attempt/<attempt_token>/review", methods=["GET"])
def review(attempt_token):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    exam = attempt.exam
    
    # Check timeout if attempt is still in progress
    if attempt.status == "in_progress":
        remaining_seconds = get_remaining_seconds(attempt)
        if remaining_seconds == 0:
            handle_attempt_timeout(attempt)
            # Reload to reflect transition
            return redirect(url_for('student_exams.review', attempt_token=attempt_token))
    else:
        remaining_seconds = 0

    questions = Question.query.filter_by(exam_id=exam.id).order_by(Question.display_order.asc()).all()
    total_questions = len(questions)
    
    # Calculate answered statistics
    answered_question_ids = {ans.question_id for ans in attempt.answers}
    answered_questions_count = len(attempt.answers)
    unanswered_questions_count = total_questions - answered_questions_count
    
    return render_template(
        "student/review.html",
        attempt=attempt,
        exam=exam,
        attempt_token=attempt_token,
        questions=questions,
        total_questions=total_questions,
        answered_question_ids=answered_question_ids,
        answered_questions_count=answered_questions_count,
        unanswered_questions_count=unanswered_questions_count,
        remaining_seconds=remaining_seconds
    )

@student_exams_bp.route("/attempt/<attempt_token>/submit", methods=["POST"])
def submit_attempt(attempt_token):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    
    if attempt.status != "in_progress":
        abort(403, description="This attempt is no longer active.")
        
    remaining_seconds = get_remaining_seconds(attempt)
    if remaining_seconds == 0:
        handle_attempt_timeout(attempt)
        return redirect(url_for('student_exams.review', attempt_token=attempt_token))
        
    # Mark as submitted
    attempt.status = "submitted"
    attempt.submitted_at = datetime.now(timezone.utc)
    db.session.commit()
    
    flash("Your exam has been successfully submitted.", "success")
    return redirect(url_for('student_exams.result_placeholder', attempt_token=attempt_token))

@student_exams_bp.route("/attempt/<attempt_token>/result", methods=["GET"])
def result_placeholder(attempt_token):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    
    if attempt.status == "in_progress":
        remaining_seconds = get_remaining_seconds(attempt)
        if remaining_seconds == 0:
            handle_attempt_timeout(attempt)
        else:
            flash("Your exam is still in progress. Please complete your exam first.", "info")
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=1))
            
    return render_template(
        "student/result_placeholder.html",
        exam=attempt.exam,
        attempt=attempt
    )
