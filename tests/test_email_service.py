import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.services.email_service import (
    parse_recipients,
    build_submission_notification_content,
    send_smtp_email,
    trigger_submission_notification,
    _notified_attempt_ids,
    _notified_lock,
)
from app.models import Exam, StudentAttempt
from app.extensions import db


def test_parse_recipients():
    # Single email
    assert parse_recipients("admin@aiqmindia.com") == ["admin@aiqmindia.com"]

    # Comma-separated with spaces
    raw = "admin1@aiqm.com ,  admin2@aiqm.com, admin3@aiqm.com  "
    assert parse_recipients(raw) == ["admin1@aiqm.com", "admin2@aiqm.com", "admin3@aiqm.com"]

    # List of emails
    assert parse_recipients(["a@b.com", " c@d.com "]) == ["a@b.com", "c@d.com"]

    # Empty, none, invalid
    assert parse_recipients("") == []
    assert parse_recipients(None) == []
    assert parse_recipients("notanemail,   ,") == []


def test_default_submission_notification_recipients():
    from config import Config
    from app.services.email_service import get_mail_config
    recipients = parse_recipients(Config.DEFAULT_SUBMISSION_NOTIFICATION_RECIPIENTS)
    assert recipients == [
        "aniket@aiqmindia.com",
        "dskode@aiqmindia.com",
        "edu@aiqmindia.com",
        "ravi.k@aiqmindia.com",
    ]

    # Verify get_mail_config falls back to Config single source of truth
    cfg = get_mail_config()
    assert parse_recipients(cfg["recipients_raw"]) == recipients


def test_build_submission_notification_content():
    attempt_data_pass = {
        "attempt_id": 42,
        "candidate_name": "Priya Sharma",
        "candidate_email": "priya.sharma@example.com",
        "exam_title": "Certified Lean Six Sigma Green Belt",
        "exam_code": "LSSGB-2026",
        "submission_time": "06-Sep-2026 05:30 PM IST",
        "attempt_number": 2,
        "submission_type": "Manual Submission",
        "score": 82.0,
        "max_marks": 100.0,
        "percentage": 82.0,
        "result_status": "Pass",
    }

    subject, text_body, html_body = build_submission_notification_content(attempt_data_pass)

    # Check subject line
    assert "Priya Sharma" in subject
    assert "LSSGB-2026" in subject
    assert "[AIQM Alert]" in subject

    # Check text body
    assert "Priya Sharma" in text_body
    assert "priya.sharma@example.com" in text_body
    assert "Certified Lean Six Sigma Green Belt" in text_body
    assert "LSSGB-2026" in text_body
    assert "06-Sep-2026 05:30 PM IST" in text_body
    assert "Attempt #2" in text_body
    assert "Manual Submission" in text_body

    # Check result fields in text body (matching exact user example)
    assert "Score: 82 / 100" in text_body
    assert "Percentage: 82%" in text_body
    assert "Result: PASSED" in text_body

    # Check html body
    assert "Priya Sharma" in html_body
    assert "priya.sharma@example.com" in html_body
    assert "Certified Lean Six Sigma Green Belt" in html_body
    assert "LSSGB-2026" in html_body
    assert "06-Sep-2026 05:30 PM IST" in html_body
    assert "Attempt #2" in html_body
    assert "82 / 100" in html_body
    assert "82%" in html_body
    assert "PASSED" in html_body

    # Check failed attempt formatting
    attempt_data_fail = {
        "candidate_name": "Rahul Verma",
        "candidate_email": "rahul@example.com",
        "exam_title": "Certified Lean Six Sigma Green Belt",
        "exam_code": "LSSGB-2026",
        "submission_time": "06-Sep-2026 06:00 PM IST",
        "attempt_number": 1,
        "submission_type": "Auto-submitted on Timeout",
        "score": 48.0,
        "max_marks": 100.0,
        "percentage": 48.0,
        "result_status": "Fail",
    }
    _, text_fail, html_fail = build_submission_notification_content(attempt_data_fail)
    assert "Score: 48 / 100" in text_fail
    assert "Percentage: 48%" in text_fail
    assert "Result: FAILED" in text_fail
    assert "48 / 100" in html_fail
    assert "48%" in html_fail
    assert "FAILED" in html_fail


def test_send_smtp_email_missing_credentials():
    mock_config = {
        "server": "smtp-relay.brevo.com",
        "port": 587,
        "use_tls": True,
        "use_ssl": False,
        "username": None,
        "password": None,
        "sender": "aniket@aiqmindia.com",
        "recipients_raw": "admin@aiqmindia.com",
    }
    # Should safely return False and not raise an exception
    success = send_smtp_email(
        to_addresses="admin@aiqmindia.com",
        subject="Test Subject",
        text_body="Test Body",
        config=mock_config
    )
    assert success is False


@patch("smtplib.SMTP")
def test_send_smtp_email_success(mock_smtp_class):
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    mock_config = {
        "server": "smtp-relay.brevo.com",
        "port": 587,
        "use_tls": True,
        "use_ssl": False,
        "username": "brevo-smtp-user",
        "password": "brevo-smtp-key-secret",
        "sender": "aniket@aiqmindia.com",
        "recipients_raw": "admin1@aiqm.com, admin2@aiqm.com",
    }

    success = send_smtp_email(
        to_addresses="admin1@aiqm.com, admin2@aiqm.com",
        subject="Test Admin Alert",
        text_body="Candidate submitted exam.",
        html_body="<p>Candidate submitted exam.</p>",
        sender="aniket@aiqmindia.com",
        config=mock_config
    )

    assert success is True
    mock_smtp_class.assert_called_once_with("smtp-relay.brevo.com", 587, timeout=20)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("brevo-smtp-user", "brevo-smtp-key-secret")
    mock_smtp_instance.send_message.assert_called_once()


@patch("smtplib.SMTP")
def test_send_smtp_email_failure_does_not_crash(mock_smtp_class):
    mock_smtp_class.side_effect = Exception("Network unreachable or connection timeout")

    mock_config = {
        "server": "smtp-relay.brevo.com",
        "port": 587,
        "use_tls": True,
        "use_ssl": False,
        "username": "brevo-smtp-user",
        "password": "brevo-smtp-key-secret",
        "sender": "aniket@aiqmindia.com",
        "recipients_raw": "admin@aiqm.com",
    }

    # Should catch exception internally, log it, and return False
    success = send_smtp_email(
        to_addresses="admin@aiqm.com",
        subject="Test Admin Alert",
        text_body="Candidate submitted exam.",
        config=mock_config
    )
    assert success is False


def test_trigger_submission_notification_duplicate_prevention(app):
    with app.app_context():
        # Clear duplicate cache for test isolation
        with _notified_lock:
            _notified_attempt_ids.clear()

        exam = Exam(
            title="Test Quality Exam",
            exam_code="TQE-DUPE-TEST",
            duration_minutes=30,
            passing_type="percentage",
            passing_value=50.0,
            timezone="Asia/Kolkata",
            is_active=True
        )
        db.session.add(exam)
        db.session.commit()

        attempt = StudentAttempt(
            exam_id=exam.id,
            student_name="Duplicate Test Student",
            student_email="dupe@aiqmindia.com",
            attempt_token="test-dupe-token-123",
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
            score=82.0,
            total_marks_obtained=82.0,
            percentage_score=82.0,
            result_status="Pass",
        )
        db.session.add(attempt)
        db.session.commit()

        with patch("threading.Thread") as mock_thread_class:
            mock_thread_instance = MagicMock()
            mock_thread_class.return_value = mock_thread_instance

            # First trigger -> should spawn thread
            trigger_submission_notification(attempt)
            assert mock_thread_class.call_count == 1
            mock_thread_instance.start.assert_called_once()

            # Verify result fields were passed into attempt_data for the thread
            call_args = mock_thread_class.call_args[1]["args"][0]
            assert call_args["score"] == 82.0
            assert call_args["percentage"] == 82.0
            assert call_args["result_status"] == "Pass"

            # Second trigger for same attempt -> must be skipped (duplicate prevention)
            mock_thread_class.reset_mock()
            mock_thread_instance.reset_mock()
            trigger_submission_notification(attempt)
            assert mock_thread_class.call_count == 0
            assert mock_thread_instance.start.call_count == 0

        # Clean up
        db.session.delete(attempt)
        db.session.delete(exam)
        db.session.commit()


def test_student_submission_flow_unbroken_by_email_failure(client, app):
    """
    Integration test: even if SMTP fails or throws an exception,
    the candidate's exam submission transaction MUST succeed.
    """
    with app.app_context():
        # Setup test exam
        exam = Exam(
            title="Resilience Test Exam",
            exam_code="RESIL-TEST-001",
            duration_minutes=60,
            passing_type="percentage",
            passing_value=50.0,
            timezone="Asia/Kolkata",
            is_active=True
        )
        db.session.add(exam)
        db.session.commit()
        exam_id = exam.id

        attempt = StudentAttempt(
            exam_id=exam_id,
            student_name="Candidate Resilience",
            student_email="resilience@example.com",
            attempt_token="token-resilience-test",
            status="in_progress",
            started_at=datetime.now(timezone.utc)
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id

    # Mock trigger_submission_notification to raise an exception simulating fatal error
    with patch("app.routes.student_exams.trigger_submission_notification", side_effect=RuntimeError("Simulated Fatal Error in Email Service")):
        resp = client.post("/attempt/token-resilience-test/submit")
        # Submission must redirect cleanly to result
        assert resp.status_code == 302
        assert "/attempt/token-resilience-test/result" in resp.headers["Location"]

    # Verify database state was committed and is submitted
    with app.app_context():
        updated_attempt = db.session.get(StudentAttempt, attempt_id)
        assert updated_attempt.status == "submitted"
        assert updated_attempt.submitted_at is not None

        # Clean up
        db.session.delete(updated_attempt)
        exam_obj = db.session.get(Exam, exam_id)
        if exam_obj:
            db.session.delete(exam_obj)
        db.session.commit()
