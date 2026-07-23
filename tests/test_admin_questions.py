"""
tests/test_admin_questions.py

Three focused tests for the Phase-2 question-type feature:

  1. MCQ regression   – create an MCQ question via the admin route and
                        assert it saves with question_type='mcq' and all
                        existing fields intact (marks, options, correct option).

  2. Subjective       – create a subjective question and assert it saves
                        with question_type='subjective', no options, and
                        rubric_text stored.

  3. Incident         – create an incident question with two sub-fields and
                        assert it saves with question_type='incident',
                        response_schema stored as a list, and marks equal to
                        the sum of sub-field max_marks.
"""

import json
import pytest

from app.extensions import db
from app.models import Exam, Question, QuestionOption


# ── Helper ──────────────────────────────────────────────────────────────────

def make_exam(app):
    """Create a minimal exam and return it (must be called inside app context)."""
    exam = Exam(
        title="Test Exam",
        exam_code="TEST001",
        duration_minutes=60,
        passing_type="percentage",
        passing_value=50.0,
    )
    db.session.add(exam)
    db.session.commit()
    return Exam.query.filter_by(exam_code="TEST001").first()


# ─────────────────────────────────────────────────────────────────────────────
# 1. MCQ regression
# ─────────────────────────────────────────────────────────────────────────────

def test_create_mcq_question_regression(logged_in_client, app):
    """
    Submitting the MCQ create form must produce a Question with:
      - question_type == 'mcq'
      - correct_option_id set
      - marks preserved
      - options count matching input
    """
    with app.app_context():
        exam = make_exam(app)
        exam_id = exam.id

    response = logged_in_client.post(
        f"/admin/exams/{exam_id}/questions/create",
        data={
            "question_type": "mcq",
            "question_text": "What is 2 + 2?",
            "marks": "2.0",
            "option_text[]": ["3", "4", "5"],
            "correct_option_index": "1",   # index 1 → "4"
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.data[:300]}"
    )

    with app.app_context():
        q = Question.query.filter_by(question_text="What is 2 + 2?").first()
        assert q is not None, "Question was not saved to the database"
        assert q.question_type == "mcq",     f"Expected 'mcq', got '{q.question_type}'"
        assert q.marks == 2.0,               f"Expected marks=2.0, got {q.marks}"
        assert len(q.options) == 3,          f"Expected 3 options, got {len(q.options)}"
        assert q.correct_option_id is not None, "correct_option_id should be set for MCQ"

        # The correct option should map to "4"
        correct_opt = QuestionOption.query.get(q.correct_option_id)
        assert correct_opt.option_text == "4", (
            f"Expected correct option text '4', got '{correct_opt.option_text}'"
        )
        assert q.response_schema is None,    "MCQ should have no response_schema"
        # Clean up
        db.session.delete(q)
        db.session.delete(Exam.query.get(exam_id))
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Subjective question creation
# ─────────────────────────────────────────────────────────────────────────────

def test_create_subjective_question(logged_in_client, app):
    """
    Submitting the Subjective create form must produce a Question with:
      - question_type == 'subjective'
      - no options
      - no correct_option_id
      - rubric_text stored
      - marks from the marks field
    """
    with app.app_context():
        exam = make_exam(app)
        exam_id = exam.id

    response = logged_in_client.post(
        f"/admin/exams/{exam_id}/questions/create",
        data={
            "question_type": "subjective",
            "question_text": "Explain the ISO 9001 Plan-Do-Check-Act cycle.",
            "marks": "5.0",
            "rubric_text": "Award full marks for correctly describing all four stages.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.data[:300]}"
    )

    with app.app_context():
        q = Question.query.filter_by(
            question_text="Explain the ISO 9001 Plan-Do-Check-Act cycle."
        ).first()
        assert q is not None,                    "Subjective question was not saved"
        assert q.question_type == "subjective",  f"Expected 'subjective', got '{q.question_type}'"
        assert q.marks == 5.0,                   f"Expected marks=5.0, got {q.marks}"
        assert len(q.options) == 0,              f"Subjective should have 0 options, got {len(q.options)}"
        assert q.correct_option_id is None,      "Subjective should not have correct_option_id"
        assert q.response_schema is None,        "Subjective should not have response_schema"
        assert q.rubric_text is not None,        "rubric_text should be stored"
        assert "Plan-Do-Check-Act" in q.rubric_text or "full marks" in q.rubric_text, (
            f"rubric_text content unexpected: {q.rubric_text!r}"
        )
        # Clean up
        db.session.delete(q)
        db.session.delete(Exam.query.get(exam_id))
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Incident question creation with sub-fields
# ─────────────────────────────────────────────────────────────────────────────

def test_create_incident_question_with_subfields(logged_in_client, app):
    """
    Submitting the Incident create form with 3 sub-fields must produce a Question with:
      - question_type == 'incident'
      - response_schema == list of dicts with label + max_marks
      - marks == sum of all sub-field max_marks
      - no options
      - no correct_option_id
    """
    with app.app_context():
        exam = make_exam(app)
        exam_id = exam.id

    sub_labels = ["Whether NC or not", "Clause No.", "Statement of NC"]
    sub_marks  = ["2",                 "1",          "3"             ]
    expected_total = 6.0  # 2 + 1 + 3

    response = logged_in_client.post(
        f"/admin/exams/{exam_id}/questions/create",
        data={
            "question_type": "incident",
            "question_text": "Review the supplied audit evidence and identify the non-conformity.",
            "rubric_text": "Marks awarded per sub-field as defined in the schema.",
            "sub_label[]": sub_labels,
            "sub_marks[]": sub_marks,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.data[:300]}"
    )

    with app.app_context():
        q = Question.query.filter_by(
            question_text="Review the supplied audit evidence and identify the non-conformity."
        ).first()
        assert q is not None,                    "Incident question was not saved"
        assert q.question_type == "incident",    f"Expected 'incident', got '{q.question_type}'"
        assert q.marks == expected_total,        f"Expected marks={expected_total}, got {q.marks}"
        assert q.correct_option_id is None,      "Incident should not have correct_option_id"
        assert len(q.options) == 0,              "Incident should have no MCQ options"

        schema = q.response_schema
        assert isinstance(schema, list),         f"response_schema should be a list, got {type(schema)}"
        assert len(schema) == 3,                 f"Expected 3 sub-fields, got {len(schema)}"

        for entry in schema:
            assert "label" in entry,     f"Sub-field missing 'label': {entry}"
            assert "max_marks" in entry, f"Sub-field missing 'max_marks': {entry}"

        labels_stored = [s["label"] for s in schema]
        assert "Whether NC or not" in labels_stored, "First sub-field label not found in schema"
        assert "Clause No."        in labels_stored, "Second sub-field label not found in schema"

        marks_sum = sum(s["max_marks"] for s in schema)
        assert marks_sum == expected_total, (
            f"Sum of schema max_marks ({marks_sum}) != Question.marks ({expected_total})"
        )

        # Clean up
        db.session.delete(q)
        db.session.delete(Exam.query.get(exam_id))
        db.session.commit()
