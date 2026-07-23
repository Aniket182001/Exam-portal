"""
Phase 4 tests — evaluation finalization logic.

Tests:
  a) test_pure_mcq_regression
     Pure-MCQ exam submit produces identical result_status/score.
  b) test_mixed_exam_partial_evaluation
     Mixed exam, partial evaluation -> doesn't finalize.
  c) test_mixed_exam_full_evaluation
     Mixed exam, full evaluation -> finalizes correctly and computes score.
  d) test_pure_manual_exam_evaluation
     Zero MCQs, relies entirely on evaluator marks.
"""
import pytest
from app.extensions import db
from app.models import User, Exam, Question, QuestionOption, StudentAttempt, StudentAnswer, Evaluation
from app.routes.student_exams import calculate_result, finalize_evaluation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evaluator():
    import uuid
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"evaluator_{uid}",
        email=f"evaluator_{uid}@test.com",
        password_hash="test",
        role="admin"
    )
    db.session.add(user)
    db.session.commit()
    return user

def _make_exam(title="Test Exam", pass_type="percentage", pass_val=50.0):
    exam = Exam(
        title=title,
        exam_code=title.replace(" ", "").upper()[:10],
        duration_minutes=60,
        passing_type=pass_type,
        passing_value=pass_val,
    )
    db.session.add(exam)
    db.session.flush()
    return exam

def _make_attempt(exam, name="Alice"):
    import uuid
    attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=name,
        student_email=f"{name.lower()}@test.com",
        attempt_token=str(uuid.uuid4()),
        status="in_progress",
    )
    db.session.add(attempt)
    db.session.flush()
    return attempt

def _make_mcq(exam, marks=2.0):
    q = Question(exam_id=exam.id, question_text="MCQ Q", marks=marks, question_type="mcq")
    db.session.add(q)
    db.session.flush()
    opt_a = QuestionOption(question_id=q.id, option_text="A", option_order=0)
    opt_b = QuestionOption(question_id=q.id, option_text="B", option_order=1)
    db.session.add_all([opt_a, opt_b])
    db.session.flush()
    q.correct_option_id = opt_a.id
    db.session.flush()
    return q, opt_a, opt_b

def _make_subjective(exam, marks=5.0):
    q = Question(exam_id=exam.id, question_text="Subj Q", marks=marks, question_type="subjective")
    db.session.add(q)
    db.session.flush()
    return q

def _answer_mcq(attempt, q_id, opt_id):
    ans = StudentAnswer(attempt_id=attempt.id, question_id=q_id, selected_option_id=opt_id)
    db.session.add(ans)
    db.session.flush()
    return ans

def _answer_subjective(attempt, q_id, text="My Answer"):
    ans = StudentAnswer(attempt_id=attempt.id, question_id=q_id, answer_text=text)
    db.session.add(ans)
    db.session.flush()
    return ans

# ---------------------------------------------------------------------------
# a) Pure-MCQ regression
# ---------------------------------------------------------------------------
def test_pure_mcq_regression(app):
    with app.app_context():
        exam = _make_exam("Pure MCQ", pass_type="percentage", pass_val=50.0)
        q1, opt1_a, opt1_b = _make_mcq(exam, marks=10.0)
        q2, opt2_a, opt2_b = _make_mcq(exam, marks=10.0)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        _answer_mcq(attempt, q1.id, opt1_a.id)  # Correct
        _answer_mcq(attempt, q2.id, opt2_b.id)  # Wrong
        db.session.commit()
        
        a_id = attempt.id

    with app.app_context():
        attempt = db.session.get(StudentAttempt, a_id)
        calculate_result(attempt)
        
        # Check assertions
        assert attempt.evaluation_status == 'not_required'
        assert attempt.result_status == 'Pass'  # 10/20 = 50%
        assert attempt.total_marks_obtained == 10.0
        
        # Calling finalize_evaluation should do nothing and return False
        assert finalize_evaluation(attempt) is False

# ---------------------------------------------------------------------------
# b) Mixed exam, partial evaluation -> doesn't finalize
# ---------------------------------------------------------------------------
def test_mixed_exam_partial_evaluation(app):
    with app.app_context():
        evaluator = _make_evaluator()
        exam = _make_exam("Mixed Eval", pass_type="percentage", pass_val=50.0)
        q1, opt1_a, opt1_b = _make_mcq(exam, marks=4.0)
        q2 = _make_subjective(exam, marks=6.0)
        q3 = _make_subjective(exam, marks=10.0)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        _answer_mcq(attempt, q1.id, opt1_a.id)
        ans2 = _answer_subjective(attempt, q2.id, "Ans 2")
        ans3 = _answer_subjective(attempt, q3.id, "Ans 3")
        db.session.commit()
        
        # Calculate result (sets pending)
        calculate_result(attempt)
        assert attempt.evaluation_status == 'pending'
        assert attempt.result_status is None
        
        # Evaluate ONE of the subjective questions
        ev2 = Evaluation(
            student_answer_id=ans2.id,
            evaluator_id=evaluator.id,
            marks_awarded=5.0,
            status='evaluated'
        )
        db.session.add(ev2)
        db.session.commit()
        
        a_id = attempt.id

    with app.app_context():
        attempt = db.session.get(StudentAttempt, a_id)
        
        # Try to finalize
        finalized = finalize_evaluation(attempt)
        
        assert finalized is False
        assert attempt.evaluation_status == 'pending'
        assert attempt.result_status is None

# ---------------------------------------------------------------------------
# c) Mixed exam, full evaluation -> finalizes correctly
# ---------------------------------------------------------------------------
def test_mixed_exam_full_evaluation(app):
    with app.app_context():
        evaluator = _make_evaluator()
        exam = _make_exam("Mixed Full Eval", pass_type="percentage", pass_val=60.0)
        # Total possible: 4 (MCQ) + 6 (Subj) = 10 marks. Pass = 6.0
        q1, opt1_a, opt1_b = _make_mcq(exam, marks=4.0)
        q2 = _make_subjective(exam, marks=6.0)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        _answer_mcq(attempt, q1.id, opt1_a.id) # 4 marks
        ans2 = _answer_subjective(attempt, q2.id, "Good answer")
        db.session.commit()
        
        calculate_result(attempt)
        
        # Evaluate all manual questions (i.e. ans2)
        ev2 = Evaluation(
            student_answer_id=ans2.id,
            evaluator_id=evaluator.id,
            marks_awarded=5.0,  # Total = 4 + 5 = 9 marks (90%)
            status='evaluated'
        )
        db.session.add(ev2)
        db.session.commit()
        
        a_id = attempt.id

    with app.app_context():
        attempt = db.session.get(StudentAttempt, a_id)
        
        finalized = finalize_evaluation(attempt)
        
        assert finalized is True
        assert attempt.evaluation_status == 'completed'
        assert attempt.result_status == 'Pass'  # 90% >= 60%
        assert attempt.total_marks_obtained == 9.0

# ---------------------------------------------------------------------------
# d) Pure-manual exam, zero MCQs
# ---------------------------------------------------------------------------
def test_pure_manual_exam_evaluation(app):
    with app.app_context():
        evaluator = _make_evaluator()
        exam = _make_exam("Pure Manual Eval", pass_type="marks", pass_val=15.0)
        # Pass mark = 15.0 absolute marks
        q1 = _make_subjective(exam, marks=10.0)
        q2 = _make_subjective(exam, marks=10.0)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        ans1 = _answer_subjective(attempt, q1.id, "Ans 1")
        ans2 = _answer_subjective(attempt, q2.id, "Ans 2")
        db.session.commit()
        
        calculate_result(attempt)
        assert attempt.total_marks_obtained == 0.0  # MCQ subtotal is 0
        
        # Evaluate both
        db.session.add(Evaluation(student_answer_id=ans1.id, evaluator_id=evaluator.id, marks_awarded=7.0, status='evaluated'))
        db.session.add(Evaluation(student_answer_id=ans2.id, evaluator_id=evaluator.id, marks_awarded=7.0, status='evaluated'))
        db.session.commit()
        
        a_id = attempt.id

    with app.app_context():
        attempt = db.session.get(StudentAttempt, a_id)
        
        finalized = finalize_evaluation(attempt)
        
        assert finalized is True
        assert attempt.evaluation_status == 'completed'
        assert attempt.result_status == 'Fail'  # 14.0 < 15.0
        assert attempt.total_marks_obtained == 14.0

# ---------------------------------------------------------------------------
# e) Pure-MCQ timeout submission
# ---------------------------------------------------------------------------
def test_pure_mcq_timeout(app):
    with app.app_context():
        exam = _make_exam("Pure MCQ Timeout", pass_type="percentage", pass_val=50.0)
        exam.auto_submit_on_timeout = True
        q1, opt1_a, opt1_b = _make_mcq(exam, marks=10.0)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        _answer_mcq(attempt, q1.id, opt1_a.id)
        db.session.commit()
        
        a_id = attempt.id

    with app.app_context():
        from app.routes.student_exams import handle_attempt_timeout
        attempt = db.session.get(StudentAttempt, a_id)
        # Timeout will internally call calculate_result
        handle_attempt_timeout(attempt)
        
        assert attempt.status == 'submitted'
        assert attempt.evaluation_status == 'not_required'
        assert attempt.result_status == 'Pass'
        assert attempt.total_marks_obtained == 10.0
