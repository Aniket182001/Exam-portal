from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, jsonify
from app.extensions import db
from app.models import Exam, StudentAttempt, Question, QuestionOption, StudentAnswer, CandidateRegistration
from datetime import datetime, timezone, timedelta
import uuid
import random
import json
from sqlalchemy import func
import logging
from app.services.email_service import trigger_submission_notification

logger = logging.getLogger(__name__)

student_exams_bp = Blueprint("student_exams", __name__)

@student_exams_bp.after_request
def add_cache_headers(response):
    """Prevent browsers from caching exam pages to avoid issues with the Back button."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

def _get_exam_or_redirect(exam_code, current_endpoint):
    """Helper to perform case-insensitive lookup or redirect with a warning instead of 404."""
    exam = Exam.query.filter_by(exam_code=exam_code).first()
    if exam:
        return exam, None
        
    exam_ci = Exam.query.filter(func.lower(Exam.exam_code) == func.lower(exam_code)).first()
    if exam_ci:
        return None, redirect(url_for(current_endpoint, exam_code=exam_ci.exam_code))
        
    flash("Exam not found: We couldn't find an exam with that code. Please check the exam code and try again. Exam codes are case-sensitive.", "warning")
    return None, redirect(url_for('main.home'))

@student_exams_bp.route("/exam/<exam_code>", methods=["GET", "POST"])
def entry(exam_code):
    exam, redirect_resp = _get_exam_or_redirect(exam_code, 'student_exams.entry')
    if redirect_resp:
        return redirect_resp
    
    if not exam.is_active:
        flash("This exam is currently not active.", "danger")
        return render_template("student/entry.html", exam=exam, disabled=True)
        
    now = datetime.now(timezone.utc)
    
    # Validation for exam timings
    if exam.restrict_to_time_window:
        if exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc):
            flash("This exam has not started yet.", "warning")
            return render_template("student/entry.html", exam=exam, disabled=True)
            
        if exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc):
            flash("This exam window has closed.", "danger")
            return render_template("student/entry.html", exam=exam, disabled=True)

    if request.method == "POST":
        student_name = request.form.get("student_name")
        student_email = request.form.get("student_email")
        company_name_raw = request.form.get("company_name", "")
        
        if not student_name or not student_email:
            flash("Name and email are required to enter the exam.", "danger")
            return render_template("student/entry.html", exam=exam)
            
        student_name = student_name.strip()
        student_email = student_email.strip()

        # Normalize company: trim, collapse internal whitespace, max 150 chars
        company_name = None
        if company_name_raw:
            cleaned_company = " ".join(company_name_raw.strip().split())
            if cleaned_company:
                company_name = cleaned_company[:150]

        if exam.require_candidate_registration:
            registration = CandidateRegistration.query.filter_by(
                exam_id=exam.id,
                email=student_email
            ).first()
            
            if not registration:
                flash("Your email is not registered for this examination. Please contact AIQM for assistance.", "danger")
                return render_template("student/entry.html", exam=exam)
            
        # Store securely in session for the next steps
        session['student_name'] = student_name
        session['student_email'] = student_email.strip()
        session['company_name'] = company_name
        
        return redirect(url_for('student_exams.instructions', exam_code=exam_code))

    return render_template("student/entry.html", exam=exam)

@student_exams_bp.route("/exam/<exam_code>/instructions", methods=["GET"])
def instructions(exam_code):
    exam, redirect_resp = _get_exam_or_redirect(exam_code, 'student_exams.instructions')
    if redirect_resp:
        return redirect_resp
    
    # Ensure they came through the entry page
    if not session.get('student_name') or not session.get('student_email'):
        flash("Please enter your details first.", "warning")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
        
    now = datetime.now(timezone.utc)
    time_invalid = exam.restrict_to_time_window and (
        (exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc)) or 
        (exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc))
    )
    if not exam.is_active or time_invalid:
        flash("This exam is currently unavailable.", "danger")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))

    return render_template("student/instructions.html", exam=exam)

@student_exams_bp.route("/exam/<exam_code>/start", methods=["POST"])
def start_exam(exam_code):
    exam, redirect_resp = _get_exam_or_redirect(exam_code, 'student_exams.start_exam')
    if redirect_resp:
        return redirect_resp
    
    student_name = session.get('student_name')
    student_email = session.get('student_email')
    company_name = session.get('company_name')
    
    if not student_name or not student_email:
        flash("Please enter your details first.", "warning")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
        
    now = datetime.now(timezone.utc)
    time_invalid = exam.restrict_to_time_window and (
        (exam.start_datetime and now < exam.start_datetime.replace(tzinfo=timezone.utc)) or 
        (exam.end_datetime and now > exam.end_datetime.replace(tzinfo=timezone.utc))
    )
    if not exam.is_active or time_invalid:
        flash("This exam is currently unavailable.", "danger")
        return redirect(url_for('student_exams.entry', exam_code=exam_code))
    # Resume existing attempt & Retest logic
    existing_attempts = StudentAttempt.query.filter_by(
        exam_id=exam.id,
        student_email=student_email
    ).order_by(StudentAttempt.started_at.asc()).all()

    if existing_attempts:
        # 1. Block entry if ANY attempt passed
        for attempt in existing_attempts:
            if attempt.result_status == "Pass":
                flash("You have already completed this examination.", "info")
                return redirect(url_for('student_exams.entry', exam_code=exam_code))

        # 2. Check for an active in_progress attempt to resume
        in_progress_attempt = next((a for a in existing_attempts if a.status == "in_progress" and a.submitted_at is None), None)
        if in_progress_attempt:
            resume_q_num = 1
            if in_progress_attempt.answers:
                ordered_questions = get_ordered_questions(in_progress_attempt)
                answered_q_ids = {ans.question_id for ans in in_progress_attempt.answers}
                highest_index = -1
                for idx, q in enumerate(ordered_questions):
                    if q.id in answered_q_ids:
                        highest_index = idx
                
                if highest_index != -1:
                    resume_q_num = min(highest_index + 2, len(ordered_questions))
                    
            return redirect(f"/attempt/{in_progress_attempt.attempt_token}/question/{resume_q_num}")

        # 3. All existing attempts are submitted and failed. Check retest limits.
        if not exam.allow_retest_on_failure or len(existing_attempts) >= exam.max_attempts:
            flash("You have already used all available attempts for this examination. Please contact AIQM for assistance.", "danger")
            return redirect(url_for('student_exams.entry', exam_code=exam_code))

    attempt_token = str(uuid.uuid4())
    question_order = None
    if exam.shuffle_questions:
        q_ids = [q.id for q in Question.query.filter_by(exam_id=exam.id).all()]
        random.shuffle(q_ids)
        question_order = q_ids
        
    new_attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=student_name,
        student_email=student_email,
        company_name=company_name,
        attempt_token=attempt_token,
        status="in_progress",
        started_at=now,
        question_order=question_order
    )
    
    db.session.add(new_attempt)
    db.session.commit()
    
    # Optionally clear the session if no longer needed, but keeping it might be useful
    session.pop('student_name', None)
    session.pop('student_email', None)
    session.pop('company_name', None)
    
    return redirect(f"/attempt/{attempt_token}/question/1")

def get_ordered_questions(attempt):
    questions = Question.query.filter_by(exam_id=attempt.exam_id).all()
    if attempt.question_order:
        q_dict = {q.id: q for q in questions}
        ordered_qs = []
        for qid in attempt.question_order:
            if qid in q_dict:
                ordered_qs.append(q_dict[qid])
        
        ordered_ids = set(attempt.question_order)
        for q in sorted(questions, key=lambda x: x.display_order if x.display_order is not None else 0):
            if q.id not in ordered_ids:
                ordered_qs.append(q)
                
        return ordered_qs
    else:
        return sorted(questions, key=lambda x: x.display_order if x.display_order is not None else 0)

def get_remaining_seconds(attempt):
    now = datetime.now(timezone.utc)
    started_at = attempt.started_at or now
    started_at_utc = started_at.replace(tzinfo=timezone.utc) if started_at.tzinfo is None else started_at.astimezone(timezone.utc)
    end_time = started_at_utc + timedelta(minutes=attempt.exam.duration_minutes)
    remaining = int((end_time - now).total_seconds())
    return max(0, remaining)

def handle_attempt_timeout(attempt):
    if attempt.status != "in_progress":
        return
    exam = attempt.exam
    now = datetime.now(timezone.utc)
    if exam.auto_submit_on_timeout:
        attempt.status = "submitted"
        attempt.submitted_at = now
        calculate_result(attempt)
        db.session.commit()

        # Trigger fail-safe admin email notification
        try:
            trigger_submission_notification(attempt, submission_type="Auto-submitted on Timeout")
        except Exception as e:
            logger.error("Failed to trigger timeout submission notification: %s", e, exc_info=True)

        flash("Your time has expired. Your exam has been automatically submitted.", "warning")
    else:
        attempt.status = "expired"
        db.session.commit()
        flash("Your time has expired. This exam attempt has expired.", "danger")

def calculate_result(attempt):
    exam = attempt.exam
    questions = Question.query.filter_by(exam_id=exam.id).all()
    total_possible_marks = sum(q.marks for q in questions)
    
    answers = {ans.question_id: ans for ans in attempt.answers}
    
    correct_count = 0
    wrong_count = 0
    unanswered_count = 0
    total_marks = 0.0
    
    # Phase 3/4: Detect if there are manual questions requiring evaluation
    has_manual_questions = any((q.question_type or 'mcq') in ('subjective', 'incident') for q in questions)
    
    for q in questions:
        ans = answers.get(q.id)
        q_type = q.question_type or 'mcq'
        
        # Only count MCQ statistics for the MCQ subtotal logic
        if q_type == 'mcq':
            if ans is None or ans.selected_option_id is None:
                unanswered_count += 1
            elif ans.selected_option_id == q.correct_option_id:
                correct_count += 1
                total_marks += q.marks
            else:
                wrong_count += 1
                if exam.negative_marking_enabled:
                    total_marks -= exam.negative_marks
        else:
            # Phase 5: Backfill skipped manual questions
            if ans is None or not ans.answer_text:
                from app.models.user import User
                from app.models.evaluation import Evaluation
                
                # If ans is None, create it
                if ans is None:
                    ans = StudentAnswer(
                        attempt_id=attempt.id,
                        question_id=q.id,
                        answer_text=""
                    )
                    db.session.add(ans)
                    db.session.flush() # get ID
                    
                # Auto-evaluate with 0 marks
                if not ans.evaluation:
                    system_admin = User.query.filter_by(role='admin').first()
                    evaluator_id = system_admin.id if system_admin else 1 # Fallback
                    
                    ev = Evaluation(
                        student_answer_id=ans.id,
                        evaluator_id=evaluator_id,
                        marks_awarded=0.0,
                        comment="Auto-evaluated (Skipped)",
                        status="evaluated",
                        evaluated_at=datetime.now(timezone.utc)
                    )
                    db.session.add(ev)
                
    percentage_score = (total_marks / total_possible_marks * 100) if total_possible_marks > 0 else 0.0
    
    # Pass/Fail determination
    if exam.passing_type == "percentage":
        passed = percentage_score >= exam.passing_value
    else:  # exam.passing_type == "marks"
        passed = total_marks >= exam.passing_value
        
    result_status = "Pass" if passed else "Fail"
    
    # Save to database (this acts as MCQ subtotal for mixed exams)
    attempt.total_marks_obtained = total_marks
    attempt.percentage_score = percentage_score
    attempt.correct_count = correct_count
    attempt.wrong_count = wrong_count
    attempt.unanswered_count = unanswered_count
    attempt.score = total_marks
    
    # Do not set result_status for mixed exams until evaluation is complete
    if has_manual_questions:
        attempt.evaluation_status = 'pending'
        attempt.result_status = None
    else:
        attempt.evaluation_status = 'not_required'
        attempt.result_status = result_status
    
    db.session.commit()

def finalize_evaluation(attempt):
    """Called after an evaluator grades a student's answers to compute final score."""
    if attempt.evaluation_status != 'pending':
        return False
        
    exam = attempt.exam
    questions = Question.query.filter_by(exam_id=exam.id).all()
    total_possible_marks = sum(q.marks for q in questions)
    
    non_mcq_questions = [q for q in questions if (q.question_type or 'mcq') in ('subjective', 'incident')]
    if not non_mcq_questions:
        return False
        
    # Gather all non-MCQ answers the student actually saved
    non_mcq_answers = [
        ans for ans in attempt.answers 
        if ans.question_id in [q.id for q in non_mcq_questions]
    ]
    
    # Verify every non-MCQ answer has a completed evaluation
    eval_sum = 0.0
    for ans in non_mcq_answers:
        if not ans.evaluation or ans.evaluation.status != 'evaluated':
            return False  # partial evaluation; cannot finalize yet
        eval_sum += (ans.evaluation.marks_awarded or 0.0)
        
    # Combine MCQ subtotal with evaluator marks
    combined_marks = (attempt.total_marks_obtained or 0.0) + eval_sum
    percentage_score = (combined_marks / total_possible_marks * 100) if total_possible_marks > 0 else 0.0
    
    if exam.passing_type == "percentage":
        passed = percentage_score >= exam.passing_value
    else:
        passed = combined_marks >= exam.passing_value
        
    attempt.score = combined_marks
    attempt.total_marks_obtained = combined_marks
    attempt.percentage_score = percentage_score
    attempt.result_status = "Pass" if passed else "Fail"
    attempt.evaluation_status = 'completed'
    
    db.session.commit()
    return True

@student_exams_bp.route("/attempt/<attempt_token>/question/<int:question_number>", methods=["GET", "POST"])
def question_attempt(attempt_token, question_number):
    logger.info("--- Enter question_attempt route ---")
    logger.info(f"Attempt token: {attempt_token}, Question number: {question_number}")
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    logger.info(f"Loaded attempt ID: {attempt.id}")

    if attempt.status != "in_progress":
        flash("This exam attempt has already been submitted.", "info")
        return redirect(url_for('student_exams.view_result', attempt_token=attempt_token))
        
    exam = attempt.exam
    
    # Calculate time remaining Authoritatively using helper
    remaining_seconds = get_remaining_seconds(attempt)
    
    # Calculate absolute end timestamp for client-side single source of truth
    started_at = attempt.started_at or datetime.now(timezone.utc)
    started_at_utc = started_at.replace(tzinfo=timezone.utc) if started_at.tzinfo is None else started_at.astimezone(timezone.utc)
    end_time = started_at_utc + timedelta(minutes=exam.duration_minutes)
    end_timestamp = int(end_time.timestamp() * 1000)
    
    # Server-side Expiration Check
    if remaining_seconds == 0:
        handle_attempt_timeout(attempt)
        return redirect(f"/attempt/{attempt_token}/review")
        
    # Fetch questions ordered by logic
    questions = get_ordered_questions(attempt)
    total_questions = len(questions)
    
    # Boundary validation
    if question_number < 1 or question_number > total_questions:
        abort(404, description="Question not found.")
        
    current_question = questions[question_number - 1]
    
    # NEW logic: identify question type
    q_type = current_question.question_type or 'mcq'
    logger.info(f"Question ID: {current_question.id}, Question type: {current_question.question_type}, q_type evaluated: {q_type}")  
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

        q_type = current_question.question_type or 'mcq'

        if q_type == 'mcq':
            # ── MCQ: save selected_option_id (unchanged) ───────────────────────
            option_id_str = request.form.get("option_id")

            if option_id_str:
                try:
                    option_id = int(option_id_str)
                except ValueError:
                    abort(400, description="Invalid option structure.")

                logger.info(f"Saving answer: option_id={option_id}")

                # Verify the option belongs to the current question
                valid_option = any(opt.id == option_id for opt in current_question.options)
                if not valid_option:
                    abort(400, description="Selected option does not belong to this question.")

                existing_answer = StudentAnswer.query.filter_by(
                    attempt_id=attempt.id,
                    question_id=current_question.id
                ).first()

                if existing_answer:
                    logger.info(f"Updating existing answer ID: {existing_answer.id}")
                    existing_answer.selected_option_id = option_id
                else:
                    logger.info("Creating new answer")
                    new_answer = StudentAnswer(
                        attempt_id=attempt.id,
                        question_id=current_question.id,
                        selected_option_id=option_id
                    )
                    db.session.add(new_answer)

                try:
                    logger.info("Committing database...")
                    db.session.commit()
                    logger.info("Database commit successful")
                except Exception as e:
                    logger.error(f"Error during database commit: {str(e)}", exc_info=True)
                    raise

        elif q_type == 'subjective':
            # ── Subjective: save raw textarea text ─────────────────────────────
            answer_text = request.form.get("answer_text", "").strip()
            logger.info(f"Subjective block hit, answer_text: {answer_text}")
            # Allow empty — students may leave blank (same as unanswered MCQ)
            existing_answer = StudentAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=current_question.id
            ).first()
            if answer_text:
                if existing_answer:
                    logger.info("Updating existing answer")
                    existing_answer.answer_text = answer_text
                else:
                    logger.info("Adding new answer")
                    db.session.add(StudentAnswer(
                        attempt_id=attempt.id,
                        question_id=current_question.id,
                        answer_text=answer_text
                    ))
                db.session.commit()
            # If empty and there was a prior answer, leave it (don't delete on autosave)

        elif q_type == 'incident':
            # ── Incident: serialize sub-field values into JSON answer_text ─────
            schema = current_question.response_schema or []
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    schema = []
            sub_values = request.form.getlist("incident_field[]")
            # Build dict keyed by label in schema order
            payload = {}
            for idx, entry in enumerate(schema):
                lbl = entry.get("label", f"Field {idx+1}")
                val = sub_values[idx].strip() if idx < len(sub_values) else ""
                payload[lbl] = val

            answer_text = json.dumps(payload, ensure_ascii=False)
            has_content = any(v for v in payload.values())

            existing_answer = StudentAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=current_question.id
            ).first()
            if has_content:
                if existing_answer:
                    existing_answer.answer_text = answer_text
                else:
                    db.session.add(StudentAnswer(
                        attempt_id=attempt.id,
                        question_id=current_question.id,
                        answer_text=answer_text
                    ))
                db.session.commit()

        # ── Navigation (same for all types) ───────────────────────────────────
        action = request.form.get("action")
        goto_question = request.form.get("goto_question")
        
        is_autosave = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        
        logger.info(f"Navigation action: {action}, goto_question: {goto_question}, is_autosave: {is_autosave}")

        if is_autosave:
            return jsonify({"status": "saved"})

        if goto_question:
            try:
                target_q = int(goto_question)
                if 1 <= target_q <= total_questions:
                    logger.info(f"Redirecting to goto_question: {target_q}")
                    return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=target_q))
                else:
                    abort(400, description="Sidebar target question out of range.")
            except ValueError:
                abort(400, description="Invalid sidebar target question.")

        if action == "prev" and question_number > 1:
            logger.info("Redirecting to previous question")
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number - 1))
        elif action == "next" and question_number < total_questions:
            logger.info("Redirecting to next question")
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number + 1))
        elif action == "finish" and question_number == total_questions:
            logger.info("Redirecting to review page")
            return redirect(f"/attempt/{attempt_token}/review")
        else:
            # Fallback if no action or out-of-bounds sequential navigation
            logger.info("Fallback redirect to current question")
            return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=question_number))
            
    # GET logic
    # Fetch existing answer for pre-selection
    existing_answer = StudentAnswer.query.filter_by(
        attempt_id=attempt.id,
        question_id=current_question.id
    ).first()

    answered_option_id = existing_answer.selected_option_id if existing_answer else None

    # For subjective/incident: pre-populate saved text
    existing_answer_text = existing_answer.answer_text if existing_answer else None

    # For incident: parse saved JSON back into a dict for the template
    existing_incident_values = {}
    if existing_answer_text and (current_question.question_type or 'mcq') == 'incident':
        try:
            existing_incident_values = json.loads(existing_answer_text)
        except (ValueError, TypeError):
            existing_incident_values = {}

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
        existing_answer_text=existing_answer_text,
        existing_incident_values=existing_incident_values,
        progress=progress,
        questions=questions,
        answered_question_ids=answered_question_ids,
        remaining_seconds=remaining_seconds,
        end_timestamp=end_timestamp
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
        # Already submitted
        flash("This exam attempt has already been submitted.", "info")
        return redirect(url_for('student_exams.view_result', attempt_token=attempt_token))

    questions = get_ordered_questions(attempt)
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
        flash("This exam attempt has already been submitted.", "info")
        return redirect(url_for('student_exams.view_result', attempt_token=attempt_token))

    remaining_seconds = get_remaining_seconds(attempt)
    if remaining_seconds == 0:
        handle_attempt_timeout(attempt)
        return redirect(url_for('student_exams.review', attempt_token=attempt_token))

    # Mark as submitted
    attempt.status = "submitted"
    attempt.submitted_at = datetime.now(timezone.utc)
    calculate_result(attempt)

    db.session.commit()

    # Trigger fail-safe admin email notification
    try:
        trigger_submission_notification(attempt, submission_type="Manual Submission")
    except Exception as e:
        logger.error("Failed to trigger submission notification: %s", e, exc_info=True)

    flash("Your exam has been successfully submitted.", "success")
    return redirect(url_for('student_exams.view_result', attempt_token=attempt_token))

@student_exams_bp.route("/attempt/<attempt_token>/result", methods=["GET"])
def view_result(attempt_token):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    
    if attempt.status == "in_progress":
        remaining_seconds = get_remaining_seconds(attempt)
        if remaining_seconds == 0:
            handle_attempt_timeout(attempt)
        else:
            flash("Your exam is still in progress. Please complete your exam first.", "info")
            # Find the first unanswered question
            questions = get_ordered_questions(attempt)
            answered_question_ids = {ans.question_id for ans in attempt.answers}
            
            first_unanswered_number = None
            for idx, q in enumerate(questions, start=1):
                if q.id not in answered_question_ids:
                    first_unanswered_number = idx
                    break
                    
            if first_unanswered_number is not None:
                return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=first_unanswered_number))
            else:
                return redirect(url_for('student_exams.review', attempt_token=attempt_token))
                
    # Calculate and save if not already calculated
    if attempt.result_status is None:
        calculate_result(attempt)
            
    if not attempt.exam.show_result_immediately:
        return render_template(
            "student/thank_you.html",
            exam=attempt.exam,
            attempt=attempt
        )
            
    return render_template(
        "student/result.html",
        exam=attempt.exam,
        attempt=attempt
    )

@student_exams_bp.route("/attempt/<attempt_token>/answer-sheet", methods=["GET"])
def view_answer_sheet(attempt_token):
    attempt = StudentAttempt.query.filter_by(attempt_token=attempt_token).first_or_404()
    
    if not attempt.exam.show_result_immediately:
        flash("Answer sheet is not available for this exam.", "danger")
        return redirect(url_for('student_exams.view_result', attempt_token=attempt_token))
        
    if attempt.status == "in_progress":
        remaining_seconds = get_remaining_seconds(attempt)
        if remaining_seconds == 0:
            handle_attempt_timeout(attempt)
        else:
            flash("Your exam is still in progress. Please complete your exam first.", "info")
            # Find the first unanswered question
            questions = Question.query.filter_by(exam_id=attempt.exam_id).order_by(Question.display_order.asc()).all()
            answered_question_ids = {ans.question_id for ans in attempt.answers}
            
            first_unanswered_number = None
            for idx, q in enumerate(questions, start=1):
                if q.id not in answered_question_ids:
                    first_unanswered_number = idx
                    break
                    
            if first_unanswered_number is not None:
                return redirect(url_for('student_exams.question_attempt', attempt_token=attempt_token, question_number=first_unanswered_number))
            else:
                return redirect(url_for('student_exams.review', attempt_token=attempt_token))
                
    questions = get_ordered_questions(attempt)
    student_answers = {ans.question_id: ans for ans in attempt.answers}
    
    return render_template(
        "student/answer_sheet.html",
        exam=attempt.exam,
        attempt=attempt,
        questions=questions,
        student_answers=student_answers
    )
