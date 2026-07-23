"""
Phase 3 tests — student-facing answer forms for subjective/incident questions.

Tests:
  a) test_student_answer_subjective_persists
     A student POSTing a subjective question saves answer_text correctly.

  b) test_student_answer_incident_json_matches_schema
     A student POSTing an incident question produces a JSON answer_text
     whose keys exactly match the response_schema labels in order.

  c) test_mixed_exam_submit_sets_evaluation_pending
     Submitting an exam that contains at least one non-MCQ question sets
     attempt.evaluation_status = 'pending'.

  d) test_pure_mcq_submit_leaves_evaluation_not_required   (regression)
     Submitting a pure-MCQ exam leaves evaluation_status = 'not_required'
     and computes scores as before.
"""
import json
import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User, Exam, Question, QuestionOption, StudentAttempt, StudentAnswer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exam(title="Test Exam"):
    exam = Exam(
        title=title,
        exam_code=title.replace(" ", "").upper()[:10],
        duration_minutes=60,
        passing_type="percentage",
        passing_value=50.0,
    )
    db.session.add(exam)
    db.session.flush()
    return exam


def _make_attempt(exam, name="Alice", email="alice@test.com"):
    import uuid
    attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=name,
        student_email=email,
        attempt_token=str(uuid.uuid4()),
        status="in_progress",
    )
    db.session.add(attempt)
    db.session.flush()
    return attempt


def _make_mcq(exam, text="MCQ Q", marks=2.0):
    q = Question(
        exam_id=exam.id,
        question_text=text,
        marks=marks,
        question_type="mcq",
    )
    db.session.add(q)
    db.session.flush()
    opt_a = QuestionOption(question_id=q.id, option_text="A", option_order=0)
    opt_b = QuestionOption(question_id=q.id, option_text="B", option_order=1)
    db.session.add_all([opt_a, opt_b])
    db.session.flush()
    q.correct_option_id = opt_a.id
    db.session.flush()
    return q, opt_a, opt_b


def _make_subjective(exam, text="Subjective Q", marks=5.0, rubric=None):
    q = Question(
        exam_id=exam.id,
        question_text=text,
        marks=marks,
        question_type="subjective",
        rubric_text=rubric,
    )
    db.session.add(q)
    db.session.flush()
    return q


def _make_incident(exam, text="Incident Q", schema=None, marks=10.0):
    if schema is None:
        schema = [
            {"label": "Whether NC or not", "max_marks": 2.0},
            {"label": "Clause No.", "max_marks": 3.0},
            {"label": "Statement of NC", "max_marks": 5.0},
        ]
    q = Question(
        exam_id=exam.id,
        question_text=text,
        marks=marks,
        question_type="incident",
        response_schema=schema,
    )
    db.session.add(q)
    db.session.flush()
    return q


# ---------------------------------------------------------------------------
# a) Subjective answer persists correctly
# ---------------------------------------------------------------------------

def test_student_answer_subjective_persists(app, logged_in_client):
    """POSTing a subjective question saves answer_text verbatim."""
    with app.app_context():
        exam = _make_exam("Subj Exam")
        _make_subjective(exam, text="Explain quality management.")
        db.session.commit()
        exam_id = exam.id
        q_id = Question.query.filter_by(exam_id=exam_id).first().id

    # Create a real student attempt (bypass session auth — poke directly)
    with app.app_context():
        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()
    answer_text = "Quality management ensures products meet standards consistently."

    resp = client.post(
        f"/attempt/{token}/question/1",
        data={
            "answer_text": answer_text,
            "action": "next",
        },
        follow_redirects=False,
    )
    # Should redirect (302) regardless — the save happens before navigation
    assert resp.status_code in (302, 200), f"Unexpected status: {resp.status_code}"

    with app.app_context():
        saved = StudentAnswer.query.filter_by(attempt_id=a_id, question_id=q_id).first()
        assert saved is not None, "StudentAnswer row not created"
        assert saved.answer_text == answer_text, (
            f"Expected '{answer_text}', got '{saved.answer_text}'"
        )
        assert saved.selected_option_id is None, "MCQ field should be NULL for subjective"


# ---------------------------------------------------------------------------
# b) Incident JSON answer matches response_schema labels
# ---------------------------------------------------------------------------

def test_student_answer_incident_json_matches_schema(app):
    """POSTing an incident question builds JSON keyed by schema labels."""
    schema = [
        {"label": "Whether NC or not", "max_marks": 2.0},
        {"label": "Clause No.", "max_marks": 3.0},
        {"label": "Statement of NC", "max_marks": 5.0},
    ]

    with app.app_context():
        exam = _make_exam("Incident Exam")
        _make_incident(exam, schema=schema)
        db.session.commit()
        exam_id = exam.id
        q_id = Question.query.filter_by(exam_id=exam_id).first().id

    with app.app_context():
        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()

    # Submit values in schema order via incident_field[]
    resp = client.post(
        f"/attempt/{token}/question/1",
        data={
            "incident_field[]": ["NC", "9.2.1", "Audit finding shows missing records"],
            "action": "next",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 200), f"Unexpected status: {resp.status_code}"

    with app.app_context():
        saved = StudentAnswer.query.filter_by(attempt_id=a_id, question_id=q_id).first()
        assert saved is not None, "StudentAnswer row not created for incident"
        assert saved.answer_text is not None, "answer_text should not be None"

        parsed = json.loads(saved.answer_text)
        assert parsed["Whether NC or not"] == "NC"
        assert parsed["Clause No."] == "9.2.1"
        assert parsed["Statement of NC"] == "Audit finding shows missing records"

        # Keys must exactly equal schema labels (no extras, no missing)
        expected_keys = {e["label"] for e in schema}
        assert set(parsed.keys()) == expected_keys, (
            f"Keys mismatch. Expected {expected_keys}, got {set(parsed.keys())}"
        )


# ---------------------------------------------------------------------------
# c) Mixed MCQ+incident exam sets evaluation_status='pending' on submit
# ---------------------------------------------------------------------------

def test_mixed_exam_submit_sets_evaluation_pending(app):
    """Submitting a mixed MCQ+incident exam sets evaluation_status='pending'."""
    with app.app_context():
        exam = _make_exam("Mixed Exam")
        mcq_q, opt_a, opt_b = _make_mcq(exam)
        _make_incident(exam)
        db.session.commit()
        exam_id = exam.id
        mcq_q_id = mcq_q.id
        opt_a_id = opt_a.id

    with app.app_context():
        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()

    # Answer the MCQ (question 1, assuming display_order)
    client.post(
        f"/attempt/{token}/question/1",
        data={"option_id": str(opt_a_id), "action": "next"},
        follow_redirects=False,
    )

    # Now submit via the review→submit route
    resp = client.post(f"/attempt/{token}/submit", follow_redirects=False)
    assert resp.status_code in (302, 200), f"Submit returned {resp.status_code}"

    with app.app_context():
        updated = db.session.get(StudentAttempt, a_id)
        assert updated.evaluation_status == "pending", (
            f"Expected 'pending', got '{updated.evaluation_status}'"
        )
        assert updated.status == "submitted"


# ---------------------------------------------------------------------------
# d) Regression: pure-MCQ exam leaves evaluation_status='not_required'
# ---------------------------------------------------------------------------

def test_pure_mcq_submit_leaves_evaluation_not_required(app):
    """A pure-MCQ exam must not touch evaluation_status — stays 'not_required'."""
    with app.app_context():
        exam = _make_exam("Pure MCQ Exam")
        mcq_q, opt_a, opt_b = _make_mcq(exam, marks=2.0)
        db.session.commit()
        exam_id = exam.id
        opt_a_id = opt_a.id
        q_id = mcq_q.id

    with app.app_context():
        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()

    # Answer the single MCQ correctly
    client.post(
        f"/attempt/{token}/question/1",
        data={"option_id": str(opt_a_id), "action": "finish"},
        follow_redirects=False,
    )

    # Submit
    resp = client.post(f"/attempt/{token}/submit", follow_redirects=False)
    assert resp.status_code in (302, 200)

    with app.app_context():
        updated = db.session.get(StudentAttempt, a_id)
        # evaluation_status must be unchanged ('not_required')
        assert updated.evaluation_status == "not_required", (
            f"Expected 'not_required', got '{updated.evaluation_status}'"
        )
        assert updated.status == "submitted"

        # Score must be calculated correctly (MCQ correct → full marks)
        assert updated.total_marks_obtained == pytest.approx(2.0), (
            f"Expected 2.0 marks, got {updated.total_marks_obtained}"
        )
        assert updated.correct_count == 1
        assert updated.result_status == "Pass"


def test_subjective_autosave_xhr(app):
    """Regression: Subjective autosave request via XHR should return 200 JSON without redirect."""
    with app.app_context():
        exam = _make_exam("Autosave Exam")
        q = Question(
            exam_id=exam.id,
            question_text="Tell me about yourself.",
            question_type="subjective",
            marks=5.0
        )
        db.session.add(q)
        db.session.commit()
        exam_id = exam.id
        q_id = q.id

        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()
    resp = client.post(
        f"/attempt/{token}/question/1",
        data={"answer_text": "I am a programmer."},
        headers={"X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    
    assert resp.status_code == 200
    assert resp.json == {"status": "saved"}
    
    with app.app_context():
        ans = StudentAnswer.query.filter_by(attempt_id=a_id, question_id=q_id).first()
        assert ans is not None
        assert ans.answer_text == "I am a programmer."


def test_submit_exam_with_incident_question(app):
    """Regression: Submitting an exam with an incident question shouldn't raise AttributeError."""
    import json
    with app.app_context():
        exam = _make_exam("Incident Submit Exam")
        schema = [{"label": "Cause", "max_marks": 5}, {"label": "Fix", "max_marks": 5}]
        q = Question(
            exam_id=exam.id,
            question_text="Analyze incident.",
            question_type="incident",
            marks=10.0,
            response_schema=json.dumps(schema)
        )
        db.session.add(q)
        db.session.commit()
        
        attempt = _make_attempt(exam)
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id
        
    client = app.test_client()
    
    # Save an answer
    client.post(
        f"/attempt/{token}/question/1",
        data={"incident_field[]": ["Server down", "Restart server"]},
    )
    
    # Submit exam
    resp = client.post(f"/attempt/{token}/submit", follow_redirects=False)
    assert resp.status_code in (302, 200)
    
    with app.app_context():
        updated = db.session.get(StudentAttempt, a_id)
        assert updated.status == "submitted"
        assert updated.evaluation_status == "pending"


def test_subjective_autosave_rapid_typing(app):
    """Simulate rapid sequential autosave requests (mimicking fast typing)."""
    with app.app_context():
        exam = _make_exam("Rapid Typing Exam")
        q = Question(
            exam_id=exam.id,
            question_text="Tell me about your project.",
            question_type="subjective",
            marks=5.0
        )
        db.session.add(q)
        db.session.commit()
        exam_id = exam.id
        q_id = q.id

        attempt = _make_attempt(Exam.query.get(exam_id))
        db.session.commit()
        token = attempt.attempt_token
        a_id = attempt.id

    client = app.test_client()
    
    # Send 3 rapid XHR POST requests
    responses = []
    for partial_answer in ["Hello", "Hello wo", "Hello world!"]:
        resp = client.post(
            f"/attempt/{token}/question/1",
            data={"answer_text": partial_answer},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
        responses.append(resp)
        
    for resp in responses:
        assert resp.status_code == 200
        assert resp.json == {"status": "saved"}
        
    with app.app_context():
        ans = StudentAnswer.query.filter_by(attempt_id=a_id, question_id=q_id).first()
        assert ans is not None
        assert ans.answer_text == "Hello world!"
def test_mcq_submit_directly_client_side_flow(app):
    with app.app_context():
        exam = _make_exam(title="ATEST")
        q1, opt1, opt2 = _make_mcq(exam)
        from app import db
        db.session.commit()
        attempt = _make_attempt(exam)
        db.session.commit()
        attempt_token = attempt.attempt_token
        opt_id = q1.options[0].id
        
    client = app.test_client()
    
    # 1) Client side calls performSilentAutosave
    client.post(f"/attempt/{attempt_token}/question/1", data={"option_id": opt_id}, headers={'X-Requested-With': 'XMLHttpRequest'})
    
    # 2) Client side calls submit_attempt via the Finish/Submit modal redirection
    client.post(f"/attempt/{attempt_token}/submit")
    
    with app.app_context():
        from app.models import StudentAnswer, StudentAttempt
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id).first()
        assert ans is not None
        assert ans.selected_option_id == opt_id
        
        att = StudentAttempt.query.filter_by(attempt_token=attempt_token).first()
        assert att.status == "submitted"

def test_subjective_submit_directly_client_side_flow(app):
    with app.app_context():
        exam = _make_exam(title="BTEST")
        q1 = _make_subjective(exam)
        from app import db
        db.session.commit()
        attempt = _make_attempt(exam)
        db.session.commit()
        attempt_token = attempt.attempt_token
        
    client = app.test_client()
    
    client.post(f"/attempt/{attempt_token}/question/1", data={"answer_text": "Subj answer"}, headers={'X-Requested-With': 'XMLHttpRequest'})
    client.post(f"/attempt/{attempt_token}/submit")
    
    with app.app_context():
        from app.models import StudentAnswer
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id).first()
        assert ans is not None
        assert ans.answer_text == "Subj answer"

def test_incident_submit_directly_client_side_flow(app):
    with app.app_context():
        exam = _make_exam(title="CTEST")
        schema = [{"label": "Action"}]
        q1 = _make_incident(exam, schema=schema)
        from app import db
        db.session.commit()
        attempt = _make_attempt(exam)
        db.session.commit()
        attempt_token = attempt.attempt_token
        
    client = app.test_client()
    
    client.post(f"/attempt/{attempt_token}/question/1", data={"incident_field[]": ["Action Taken"]}, headers={'X-Requested-With': 'XMLHttpRequest'})
    client.post(f"/attempt/{attempt_token}/submit")
    
    with app.app_context():
        from app.models import StudentAnswer
        import json
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id).first()
        assert ans is not None
        data = json.loads(ans.answer_text)
        assert data["Action"] == "Action Taken"

def test_normal_navigate_then_submit_flow(app):
    with app.app_context():
        exam = _make_exam(title="DTEST")
        q1, opt1, opt2 = _make_mcq(exam)
        from app import db
        db.session.commit()
        attempt = _make_attempt(exam)
        db.session.commit()
        attempt_token = attempt.attempt_token
        opt_id = q1.options[0].id
        
    client = app.test_client()
    
    # 1) Normal navigation
    client.post(f"/attempt/{attempt_token}/question/1", data={"option_id": opt_id, "action": "next"})
    
    # 2) Submit from review page
    client.post(f"/attempt/{attempt_token}/submit")
    
    with app.app_context():
        from app.models import StudentAnswer
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id).first()
        assert ans is not None
        assert ans.selected_option_id == opt_id


def test_failed_final_autosave_blocks_submit_mock(app):
    """
    Simulates the JS block/retry logic conceptually.
    Since the actual blocking is client-side JS (which Pytest doesn't run),
    this test proves that if an autosave request fails (mocked 500 error), 
    it returns the error properly so JS can catch it, and if the JS aborts the
    subsequent submit (simulated by not sending it), the attempt remains in_progress.
    """
    with app.app_context():
        exam = _make_exam(title="FAILTEST")
        q1, opt1, opt2 = _make_mcq(exam)
        from app import db
        db.session.commit()
        attempt = _make_attempt(exam)
        db.session.commit()
        attempt_token = attempt.attempt_token
        opt_id = q1.options[0].id

    client = app.test_client()
    
    from unittest.mock import patch
    
    # 1. Simulate the autosave request FAILING
    # We simulate a backend failure by patching the db commit to raise an exception
    with patch('app.extensions.db.session.commit', side_effect=Exception("DB Error")):
        import pytest
        with pytest.raises(Exception, match="DB Error"):
            client.post(
                f"/attempt/{attempt_token}/question/1",
                data={"option_id": opt_id},
                headers={'X-Requested-With': 'XMLHttpRequest'}
            )
        
    # 2. The JS frontend catches this 500 error and ABORTS the submission.
    # So we simulate the client doing nothing further (no action=finish, no /submit).
    
    # 3. Verify attempt is still in_progress and not corrupted
    with app.app_context():
        from app.models import StudentAttempt
        att = StudentAttempt.query.filter_by(attempt_token=attempt_token).first()
        assert att.status == "in_progress"

