"""
tests/test_admin_improvements.py

Tests for the three admin experience improvements:
1. "Save Exam" button text on edit exam page.
2. Safe cascading deletions for questions and exams that have student responses/attempts,
   including cross-exam security validation on bulk question deletion.
3. Activity-based sorting on the Admin Dashboard exams list using real datetime values.
"""

from datetime import datetime, timezone, timedelta
import uuid
import pytest
from app.extensions import db
from app.models import (
    Exam,
    Question,
    QuestionOption,
    StudentAttempt,
    StudentAnswer,
    CandidateRegistration,
    Evaluation,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_test_exam(title="Test Exam", exam_code=None, created_at=None, **kwargs):
    """Create a minimal exam in the database."""
    if exam_code is None:
        exam_code = f"EXAM-{uuid.uuid4().hex[:8].upper()}"
    exam = Exam(
        title=title,
        exam_code=exam_code,
        duration_minutes=60,
        passing_type="percentage",
        passing_value=50.0,
        is_active=True,
        **kwargs,
    )
    if created_at is not None:
        exam.created_at = created_at
    db.session.add(exam)
    db.session.commit()
    return exam


def create_test_question(exam_id, question_text="What is 2+2?", marks=1.0, display_order=1):
    """Create a question with 2 options."""
    q = Question(
        exam_id=exam_id,
        question_text=question_text,
        marks=marks,
        display_order=display_order,
        question_type="mcq",
    )
    db.session.add(q)
    db.session.flush()

    opt1 = QuestionOption(question_id=q.id, option_text="4", option_order=1)
    opt2 = QuestionOption(question_id=q.id, option_text="5", option_order=2)
    db.session.add_all([opt1, opt2])
    db.session.flush()

    q.correct_option_id = opt1.id
    db.session.commit()
    return q, [opt1, opt2]


def create_test_attempt(exam_id, student_name="Student One", student_email="s1@example.com",
                        started_at=None, submitted_at=None, status="in_progress"):
    """Create a student attempt."""
    now = datetime.now(timezone.utc)
    attempt = StudentAttempt(
        exam_id=exam_id,
        student_name=student_name,
        student_email=student_email,
        attempt_token=str(uuid.uuid4()),
        started_at=started_at or now,
        submitted_at=submitted_at,
        status=status,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


@pytest.fixture(autouse=True)
def clean_test_records(app):
    """Clean up any database records created by tests in this module."""
    yield
    with app.app_context():
        test_exams = Exam.query.filter(
            db.or_(
                Exam.title.in_([
                    "Test Exam",
                    "Edit Exam Test",
                    "Question Delete Exam",
                    "Bulk Question Delete Exam",
                    "Exam 1",
                    "Exam 2",
                    "Exam To Delete",
                    "Exam To Keep",
                    "Exam Protected",
                    "Exam Alpha",
                    "Exam Beta",
                    "Exam Gamma",
                    "Exam Delta",
                    "Python Certification Level 1",
                    "Python Certification Level 2",
                    "Java Associate Exam",
                ]),
                Exam.exam_code.like("EXAM-%"),
                Exam.exam_code.like("CODE-%"),
                Exam.exam_code.in_(["PY-101", "PY-201", "JAVA-101"]),
            )
        ).all()
        for exam in test_exams:
            attempts = StudentAttempt.query.filter_by(exam_id=exam.id).all()
            att_ids = [a.id for a in attempts]
            if att_ids:
                ans_ids = [ans.id for ans in StudentAnswer.query.filter(StudentAnswer.attempt_id.in_(att_ids)).all()]
                if ans_ids:
                    Evaluation.query.filter(Evaluation.student_answer_id.in_(ans_ids)).delete(synchronize_session=False)
                    StudentAnswer.query.filter(StudentAnswer.id.in_(ans_ids)).delete(synchronize_session=False)
                StudentAttempt.query.filter(StudentAttempt.id.in_(att_ids)).delete(synchronize_session=False)

            CandidateRegistration.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)

            questions = Question.query.filter_by(exam_id=exam.id).all()
            q_ids = [q.id for q in questions]
            if q_ids:
                ans_ids = [ans.id for ans in StudentAnswer.query.filter(StudentAnswer.question_id.in_(q_ids)).all()]
                if ans_ids:
                    Evaluation.query.filter(Evaluation.student_answer_id.in_(ans_ids)).delete(synchronize_session=False)
                    StudentAnswer.query.filter(StudentAnswer.id.in_(ans_ids)).delete(synchronize_session=False)
                QuestionOption.query.filter(QuestionOption.question_id.in_(q_ids)).delete(synchronize_session=False)
                Question.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)

            db.session.delete(exam)
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Button Text Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_edit_exam_button_text(logged_in_client, app):
    """Verify that the edit exam page displays 'Save Exam' instead of 'Edit Exam'."""
    with app.app_context():
        exam = create_test_exam(title="Edit Exam Test")
        exam_id = exam.id

    # GET edit form
    res = logged_in_client.get(f"/admin/exams/{exam_id}/edit")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Save Exam" in html
    # Ensure the button does not display "Edit Exam"
    assert "<i class=\"bi bi-save-fill me-2\"></i> Edit Exam" not in html

    # GET create form to ensure 'Create Exam' is still preserved
    create_res = logged_in_client.get("/admin/exams/create")
    assert create_res.status_code == 200
    create_html = create_res.get_data(as_text=True)
    assert "Create Exam" in create_html


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cascading Question Deletion
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_question_with_student_responses(logged_in_client, app, admin_user):
    """Deleting a question with student answers and evaluations must succeed and cascade cleanly."""
    with app.app_context():
        exam = create_test_exam(title="Question Delete Exam")
        q1, opts1 = create_test_question(exam.id, "Question 1")
        q2, opts2 = create_test_question(exam.id, "Question 2")

        attempt = create_test_attempt(exam.id, status="submitted")

        # Answer for q1
        ans1 = StudentAnswer(
            attempt_id=attempt.id,
            question_id=q1.id,
            selected_option_id=opts1[0].id,
            answer_text="4",
        )
        db.session.add(ans1)
        db.session.flush()

        # Evaluation for ans1
        eval1 = Evaluation(
            student_answer_id=ans1.id,
            evaluator_id=admin_user.id,
            marks_awarded=1.0,
            status="evaluated",
        )
        db.session.add(eval1)
        db.session.commit()

        q1_id = q1.id
        q2_id = q2.id
        ans1_id = ans1.id
        eval1_id = eval1.id
        attempt_id = attempt.id
        exam_id = exam.id

    # Delete question 1
    res = logged_in_client.post(f"/admin/questions/{q1_id}/delete", follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # Q1 and its dependents are gone
        assert db.session.get(Question, q1_id) is None
        assert QuestionOption.query.filter_by(question_id=q1_id).count() == 0
        assert db.session.get(StudentAnswer, ans1_id) is None
        assert db.session.get(Evaluation, eval1_id) is None

        # Q2, attempt, and exam are untouched
        assert db.session.get(Question, q2_id) is not None
        assert db.session.get(StudentAttempt, attempt_id) is not None
        assert db.session.get(Exam, exam_id) is not None


def test_delete_selected_questions_with_responses(logged_in_client, app, admin_user):
    """Bulk question deletion with existing student answers and evaluations must cascade cleanly."""
    with app.app_context():
        exam = create_test_exam(title="Bulk Question Delete Exam")
        q1, opts1 = create_test_question(exam.id, "Q1")
        q2, opts2 = create_test_question(exam.id, "Q2")
        q3, opts3 = create_test_question(exam.id, "Q3")

        attempt = create_test_attempt(exam.id, status="submitted")

        ans1 = StudentAnswer(attempt_id=attempt.id, question_id=q1.id, selected_option_id=opts1[0].id)
        ans2 = StudentAnswer(attempt_id=attempt.id, question_id=q2.id, selected_option_id=opts2[0].id)
        db.session.add_all([ans1, ans2])
        db.session.flush()

        eval1 = Evaluation(student_answer_id=ans1.id, evaluator_id=admin_user.id, marks_awarded=1.0)
        db.session.add(eval1)
        db.session.commit()

        q1_id, q2_id, q3_id = q1.id, q2.id, q3.id
        exam_id = exam.id

    # Post bulk delete for q1 and q2
    res = logged_in_client.post(
        f"/admin/exams/{exam_id}/questions/delete_selected",
        data={"question_ids": [str(q1_id), str(q2_id)]},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        assert db.session.get(Question, q1_id) is None
        assert db.session.get(Question, q2_id) is None
        assert db.session.get(Question, q3_id) is not None
        assert StudentAnswer.query.filter(StudentAnswer.question_id.in_([q1_id, q2_id])).count() == 0


def test_delete_selected_questions_cross_exam_security(logged_in_client, app):
    """Security test: delete_selected_questions must never delete questions belonging to another exam."""
    with app.app_context():
        exam1 = create_test_exam(title="Exam 1")
        exam2 = create_test_exam(title="Exam 2")
        q1, _ = create_test_question(exam1.id, "Question in Exam 1")
        q2, _ = create_test_question(exam2.id, "Question in Exam 2")

        exam1_id = exam1.id
        exam2_id = exam2.id
        q1_id = q1.id
        q2_id = q2.id

    # Malicious attempt: delete Exam 2's question via Exam 1's endpoint
    res = logged_in_client.post(
        f"/admin/exams/{exam1_id}/questions/delete_selected",
        data={"question_ids": [str(q2_id)]},
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "do not belong to this exam" in html

    # Mixed attempt: both Exam 1's and Exam 2's questions submitted together
    res_mixed = logged_in_client.post(
        f"/admin/exams/{exam1_id}/questions/delete_selected",
        data={"question_ids": [str(q1_id), str(q2_id)]},
        follow_redirects=True,
    )
    assert res_mixed.status_code == 200
    html_mixed = res_mixed.get_data(as_text=True)
    assert "do not belong to this exam" in html_mixed

    with app.app_context():
        # Both questions must remain completely untouched!
        assert db.session.get(Question, q1_id) is not None
        assert db.session.get(Question, q2_id) is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cascading Exam Deletion
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_exam_with_attempts_and_registrations(logged_in_client, app, admin_user):
    """Deleting an exam must cascade to attempts, answers, evaluations, candidates, and questions."""
    with app.app_context():
        exam1 = create_test_exam(title="Exam To Delete")
        exam2 = create_test_exam(title="Exam To Keep")

        q1, opts1 = create_test_question(exam1.id, "Q in Exam 1")
        q2, opts2 = create_test_question(exam2.id, "Q in Exam 2")

        reg1 = CandidateRegistration(
            candidate_name="John Doe",
            email="john@example.com",
            exam_id=exam1.id,
        )
        db.session.add(reg1)

        att1 = create_test_attempt(exam1.id, status="submitted")
        ans1 = StudentAnswer(attempt_id=att1.id, question_id=q1.id, selected_option_id=opts1[0].id)
        db.session.add(ans1)
        db.session.flush()

        eval1 = Evaluation(student_answer_id=ans1.id, evaluator_id=admin_user.id, marks_awarded=1.0)
        db.session.add(eval1)

        att2 = create_test_attempt(exam2.id, status="submitted")
        ans2 = StudentAnswer(attempt_id=att2.id, question_id=q2.id, selected_option_id=opts2[0].id)
        db.session.add(ans2)

        db.session.commit()

        exam1_id = exam1.id
        exam2_id = exam2.id
        q1_id = q1.id
        q2_id = q2.id
        att1_id = att1.id
        att2_id = att2.id

    # Authenticate sensitive action
    with logged_in_client.session_transaction() as sess:
        sess["sensitive_action_verified"] = True

    res = logged_in_client.post(f"/admin/exams/{exam1_id}/delete", follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # Exam 1 and all related data are deleted
        assert db.session.get(Exam, exam1_id) is None
        assert db.session.get(Question, q1_id) is None
        assert QuestionOption.query.filter_by(question_id=q1_id).count() == 0
        assert db.session.get(StudentAttempt, att1_id) is None
        assert StudentAnswer.query.filter_by(attempt_id=att1_id).count() == 0
        assert CandidateRegistration.query.filter_by(exam_id=exam1_id).count() == 0

        # Exam 2 and all its data are untouched
        assert db.session.get(Exam, exam2_id) is not None
        assert db.session.get(Question, q2_id) is not None
        assert db.session.get(StudentAttempt, att2_id) is not None


def test_delete_exam_requires_sensitive_verification(logged_in_client, app):
    """Deleting an exam without sensitive action verification must redirect to PIN authentication."""
    with app.app_context():
        exam = create_test_exam(title="Exam Protected")
        exam_id = exam.id

    res = logged_in_client.post(f"/admin/exams/{exam_id}/delete", follow_redirects=False)
    assert res.status_code == 302
    assert "/admin/backup/auth" in res.headers["Location"]

    with app.app_context():
        # Exam is not deleted
        assert db.session.get(Exam, exam_id) is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Activity-Based Exam Sorting on Admin Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_dashboard_sorting_by_activity(logged_in_client, app):
    """
    Exams must be sorted by latest student attempt activity:
    - Active exams (with attempts) come first, ordered by latest submitted_at or started_at.
    - Inactive exams (no attempts) follow, ordered by created_at descending.
    Real datetime values matching model field types are used.
    """
    base_time = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

    with app.app_context():
        # Exam A: created 10 days ago, attempt submitted 5 days ago
        exam_a = create_test_exam(
            title="Exam Alpha",
            exam_code="CODE-ALPHA",
            created_at=base_time - timedelta(days=10),
        )
        create_test_attempt(
            exam_a.id,
            started_at=base_time - timedelta(days=5, hours=1),
            submitted_at=base_time - timedelta(days=5),
            status="submitted",
        )

        # Exam B: created 8 days ago, attempt in progress (started 2 days ago, not yet submitted)
        exam_b = create_test_exam(
            title="Exam Beta",
            exam_code="CODE-BETA",
            created_at=base_time - timedelta(days=8),
        )
        create_test_attempt(
            exam_b.id,
            started_at=base_time - timedelta(days=2),
            submitted_at=None,
            status="in_progress",
        )

        # Exam C: created 4 days ago, NO attempts
        exam_c = create_test_exam(
            title="Exam Gamma",
            exam_code="CODE-GAMMA",
            created_at=base_time - timedelta(days=4),
        )

        # Exam D: created 3 days ago, NO attempts
        exam_d = create_test_exam(
            title="Exam Delta",
            exam_code="CODE-DELTA",
            created_at=base_time - timedelta(days=3),
        )

    res = logged_in_client.get("/admin/exams/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Expected order:
    # 1. Exam Beta (activity 2 days ago)
    # 2. Exam Alpha (activity 5 days ago)
    # 3. Exam Delta (created 3 days ago)
    # 4. Exam Gamma (created 4 days ago)
    pos_beta = html.find("CODE-BETA")
    pos_alpha = html.find("CODE-ALPHA")
    pos_delta = html.find("CODE-DELTA")
    pos_gamma = html.find("CODE-GAMMA")

    assert pos_beta != -1, "CODE-BETA not found in dashboard"
    assert pos_alpha != -1, "CODE-ALPHA not found in dashboard"
    assert pos_delta != -1, "CODE-DELTA not found in dashboard"
    assert pos_gamma != -1, "CODE-GAMMA not found in dashboard"

    assert pos_beta < pos_alpha, "Exam Beta (2 days ago) should appear before Exam Alpha (5 days ago)"
    assert pos_alpha < pos_delta, "Active exams should appear before exams with no attempts"
    assert pos_delta < pos_gamma, "Exam Delta (created 3 days ago) should appear before Exam Gamma (created 4 days ago)"


def test_admin_dashboard_search_and_sorting(logged_in_client, app):
    """Dashboard search query filters exams while preserving sorting order."""
    base_time = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

    with app.app_context():
        exam_1 = create_test_exam(
            title="Python Certification Level 1",
            exam_code="PY-101",
            created_at=base_time - timedelta(days=5),
        )
        exam_2 = create_test_exam(
            title="Python Certification Level 2",
            exam_code="PY-201",
            created_at=base_time - timedelta(days=6),
        )
        exam_3 = create_test_exam(
            title="Java Associate Exam",
            exam_code="JAVA-101",
            created_at=base_time - timedelta(days=1),
        )

        # Python Level 2 had an attempt 1 day ago
        create_test_attempt(
            exam_2.id,
            started_at=base_time - timedelta(days=1),
            submitted_at=base_time - timedelta(days=1),
            status="submitted",
        )

    res = logged_in_client.get("/admin/exams/?search=Python")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "PY-101" in html
    assert "PY-201" in html
    assert "JAVA-101" not in html

    # PY-201 has activity, PY-101 has no activity
    pos_py201 = html.find("PY-201")
    pos_py101 = html.find("PY-101")
    assert pos_py201 < pos_py101, "Active PY-201 should appear before inactive PY-101"
