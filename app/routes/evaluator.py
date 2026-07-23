from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from app.extensions import db
from app.models import StudentAnswer, StudentAttempt, Question, Evaluation
from app.utils.auth import evaluator_required
from datetime import datetime, timezone
import json

evaluator_bp = Blueprint("evaluator", __name__, url_prefix="/evaluator")

@evaluator_bp.route("/dashboard")
@evaluator_required
def dashboard():
    pending_answers = db.session.query(StudentAnswer).join(
        StudentAttempt
    ).join(
        Question
    ).outerjoin(
        Evaluation
    ).filter(
        StudentAttempt.evaluation_status == 'pending',
        Question.question_type.in_(['subjective', 'incident']),
        db.or_(
            Evaluation.id.is_(None),
            Evaluation.status == 'pending'
        )
    ).all()
    
    return render_template("evaluator/dashboard.html", answers=pending_answers)

@evaluator_bp.route("/evaluate/<int:answer_id>", methods=["GET", "POST"])
@evaluator_required
def evaluate(answer_id):
    answer = StudentAnswer.query.get_or_404(answer_id)
    attempt = StudentAttempt.query.get(answer.attempt_id)
    question = Question.query.get(answer.question_id)
    
    if attempt.evaluation_status != 'pending':
        flash("This attempt is no longer pending evaluation.", "warning")
        return redirect(url_for("evaluator.dashboard"))
        
    if request.method == "POST":
        eval_status = "evaluated"
        comment = request.form.get("comment", "")
        
        if question.question_type == 'subjective':
            marks = request.form.get("marks_awarded", type=float)
            if marks is None or marks < 0 or marks > question.marks:
                flash(f"Marks must be between 0 and {question.marks}", "danger")
                return redirect(request.url)
                
            marks_awarded = marks
            marks_breakdown = None
            
        elif question.question_type == 'incident':
            schema = []
            if question.response_schema:
                schema = question.response_schema
                if isinstance(schema, str):
                    try:
                        schema = json.loads(schema)
                    except Exception:
                        schema = []
                    
            marks_awarded = 0.0
            marks_breakdown = {}
            for field in schema:
                label = field.get("label", "")
                max_marks = float(field.get("max_marks", 0))
                
                # Fetch mark for this specific label
                field_val = request.form.get(f"mark_{label}", type=float)
                if field_val is None or field_val < 0 or field_val > max_marks:
                    flash(f"Invalid marks for '{label}'. Must be between 0 and {max_marks}.", "danger")
                    return redirect(request.url)
                    
                marks_breakdown[label] = field_val
                marks_awarded += field_val
                
        # Create or update Evaluation
        ev = answer.evaluation
        if not ev:
            ev = Evaluation(student_answer_id=answer.id)
            db.session.add(ev)
            
        ev.evaluator_id = session.get("user_id")
        ev.marks_awarded = marks_awarded
        ev.marks_breakdown = marks_breakdown
        ev.comment = comment
        ev.status = eval_status
        ev.evaluated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Check if attempt can be finalized
        from app.routes.student_exams import finalize_evaluation
        if finalize_evaluation(attempt):
            flash("All answers for this attempt evaluated. Final score computed.", "success")
        else:
            flash("Evaluation saved. Pending other manual answers.", "success")
            
        return redirect(url_for("evaluator.dashboard"))
        
    return render_template("evaluator/evaluate.html", answer=answer, question=question)
