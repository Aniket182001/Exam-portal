import pytest
from app.extensions import db
from app.models import User, Exam, Question, StudentAttempt, StudentAnswer, Evaluation
from datetime import datetime, timezone
import json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(role="evaluator"):
    import uuid
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"{role}_{uid}",
        email=f"{role}_{uid}@test.com",
        password_hash="test",
        role=role
    )
    db.session.add(user)
    db.session.commit()
    return user

def _make_exam():
    import uuid
    uid = str(uuid.uuid4())[:8].upper()
    exam = Exam(
        title=f"Evaluator Test Exam {uid}",
        exam_code=f"EVAL{uid}",
        duration_minutes=60,
        passing_type="marks",
        passing_value=10.0,
    )
    db.session.add(exam)
    db.session.commit()
    return exam

def _make_attempt(exam, name="Eve"):
    import uuid
    attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=name,
        student_email=f"{name.lower()}@test.com",
        attempt_token=str(uuid.uuid4()),
        status="submitted",
        evaluation_status="pending",
        total_marks_obtained=0.0
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt

def _make_subjective(exam, marks=5.0):
    q = Question(exam_id=exam.id, question_text="Subj Q", marks=marks, question_type="subjective")
    db.session.add(q)
    db.session.commit()
    return q

def _make_incident(exam, marks=10.0):
    schema = [{"label": "Part A", "max_marks": 4}, {"label": "Part B", "max_marks": 6}]
    q = Question(
        exam_id=exam.id,
        question_text="Incident Q",
        marks=marks,
        question_type="incident",
        response_schema=json.dumps(schema)
    )
    db.session.add(q)
    db.session.commit()
    return q

def _answer_subjective(attempt, q_id, text="My Subj Ans"):
    ans = StudentAnswer(attempt_id=attempt.id, question_id=q_id, answer_text=text)
    db.session.add(ans)
    db.session.commit()
    return ans

def _answer_incident(attempt, q_id):
    ans_data = {"Part A": "Ans A", "Part B": "Ans B"}
    ans = StudentAnswer(attempt_id=attempt.id, question_id=q_id, answer_text=json.dumps(ans_data))
    db.session.add(ans)
    db.session.commit()
    return ans

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluator_auth(client, app):
    with app.app_context():
        student = _make_user(role="student")
        student_id = student.id
        
    with client.session_transaction() as sess:
        sess["user_id"] = student_id
        
    # Should block access
    response = client.get('/evaluator/dashboard')
    assert response.status_code == 403

def test_evaluate_subjective_partial(client, app):
    with app.app_context():
        evaluator = _make_user(role="evaluator")
        exam = _make_exam()
        q1 = _make_subjective(exam)
        q2 = _make_subjective(exam)
        attempt = _make_attempt(exam)
        ans1 = _answer_subjective(attempt, q1.id)
        ans2 = _answer_subjective(attempt, q2.id)
        
        eval_id = evaluator.id
        a_id = attempt.id
        ans1_id = ans1.id
        
    with client.session_transaction() as sess:
        sess["user_id"] = eval_id
        
    # Evaluate ans1
    resp = client.post(f'/evaluator/evaluate/{ans1_id}', data={
        'marks_awarded': '3.5',
        'comment': 'Good start'
    }, follow_redirects=True)
    
    assert resp.status_code == 200
    assert b"Evaluation saved" in resp.data
    
    with app.app_context():
        ans1 = db.session.get(StudentAnswer, ans1_id)
        assert ans1.evaluation is not None
        assert ans1.evaluation.marks_awarded == 3.5
        assert ans1.evaluation.status == 'evaluated'
        
        attempt = db.session.get(StudentAttempt, a_id)
        assert attempt.evaluation_status == 'pending' # Still pending q2

def test_evaluate_last_answer_finalizes(client, app):
    with app.app_context():
        evaluator = _make_user(role="evaluator")
        exam = _make_exam()
        q1 = _make_subjective(exam, marks=10.0)
        attempt = _make_attempt(exam)
        ans1 = _answer_subjective(attempt, q1.id)
        
        eval_id = evaluator.id
        a_id = attempt.id
        ans1_id = ans1.id
        
    with client.session_transaction() as sess:
        sess["user_id"] = eval_id
        
    resp = client.post(f'/evaluator/evaluate/{ans1_id}', data={
        'marks_awarded': '10.0' # Pass value is 10.0
    }, follow_redirects=True)
    
    assert b"Final score computed" in resp.data
    
    with app.app_context():
        attempt = db.session.get(StudentAttempt, a_id)
        assert attempt.evaluation_status == 'completed'
        assert attempt.result_status == 'Pass'
        assert attempt.total_marks_obtained == 10.0

def test_evaluate_validation_fails(client, app):
    with app.app_context():
        evaluator = _make_user(role="evaluator")
        exam = _make_exam()
        q1 = _make_subjective(exam, marks=5.0)
        attempt = _make_attempt(exam)
        ans1 = _answer_subjective(attempt, q1.id)
        
        eval_id = evaluator.id
        ans1_id = ans1.id
        
    with client.session_transaction() as sess:
        sess["user_id"] = eval_id
        
    resp = client.post(f'/evaluator/evaluate/{ans1_id}', data={
        'marks_awarded': '6.0' # Exceeds max 5.0
    }, follow_redirects=True)
    
    assert b"Marks must be between 0 and 5.0" in resp.data
    
    with app.app_context():
        ans1 = db.session.get(StudentAnswer, ans1_id)
        assert ans1.evaluation is None

def test_evaluate_incident(client, app):
    with app.app_context():
        evaluator = _make_user(role="evaluator")
        exam = _make_exam()
        q1 = _make_incident(exam, marks=10.0)
        attempt = _make_attempt(exam)
        ans1 = _answer_incident(attempt, q1.id)
        
        eval_id = evaluator.id
        ans1_id = ans1.id
        
    with client.session_transaction() as sess:
        sess["user_id"] = eval_id
        
    # Incident question posts individual fields
    resp = client.post(f'/evaluator/evaluate/{ans1_id}', data={
        'mark_Part A': '3.0',
        'mark_Part B': '5.0'
    }, follow_redirects=True)
    
    assert resp.status_code == 200
    
    with app.app_context():
        ans1 = db.session.get(StudentAnswer, ans1_id)
        ev = ans1.evaluation
        assert ev is not None
        assert ev.marks_awarded == 8.0
        assert ev.marks_breakdown == {"Part A": 3.0, "Part B": 5.0}
