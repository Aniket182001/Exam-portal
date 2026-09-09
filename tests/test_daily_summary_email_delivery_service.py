import smtplib
from datetime import date, datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
import pytest

from config import Config
from app.services.daily_summary_service import (
    DailyExamSummaryReport,
    DailyCompanyGroupSummary,
    DailySummaryAttemptItem,
)
from app.services.daily_summary_email_service import (
    render_daily_summary_email,
    get_daily_summary_email_subject,
)
from app.services.daily_summary_email_delivery_service import (
    send_daily_exam_summary_email,
    get_daily_summary_recipients,
    build_daily_summary_text_fallback,
    DailySummaryDeliveryResult,
)


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

def _build_mock_item(
    candidate_name="Alice Smith",
    exam_title="Lean Six Sigma",
    exam_code="LSS-01",
    score=20.0,
    max_marks=25.0,
    percentage=80.0,
    result_status="Pass",
):
    return DailySummaryAttemptItem(
        attempt_id=1,
        candidate_name=candidate_name,
        candidate_email="alice@example.com",
        exam_id=10,
        exam_title=exam_title,
        exam_code=exam_code,
        company_name="Apex Corp",
        raw_company_name="Apex Corp",
        attempt_number=1,
        submitted_at=datetime(2026, 9, 9, 16, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
        submitted_at_str="09-Sep-2026 04:30 PM IST",
        score=score,
        max_marks=max_marks,
        percentage=percentage,
        result_status=result_status,
        evaluation_status="not_required",
    )


def _build_sample_report(report_date=date(2026, 9, 9), total_submissions=1):
    if total_submissions == 0:
        return DailyExamSummaryReport(
            report_date=report_date,
            total_submissions=0,
            total_passed=0,
            total_failed=0,
            total_unevaluated=0,
            total_companies=0,
            named_companies_count=0,
            company_groups=[],
        )

    item = _build_mock_item()
    group = DailyCompanyGroupSummary(
        company_name="Apex Corp",
        total_submissions=1,
        total_passed=1,
        total_failed=0,
        total_unevaluated=0,
        attempts=[item],
    )
    return DailyExamSummaryReport(
        report_date=report_date,
        total_submissions=1,
        total_passed=1,
        total_failed=0,
        total_unevaluated=0,
        total_companies=1,
        named_companies_count=1,
        company_groups=[group],
    )


# ---------------------------------------------------------------------------
# Unit & Integration Tests
# ---------------------------------------------------------------------------

def test_successful_delivery_mocked_smtp(app):
    """Verifies successful delivery of daily summary email via mocked SMTP."""
    report = _build_sample_report()

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        result = send_daily_exam_summary_email(report)

        assert isinstance(result, DailySummaryDeliveryResult)
        assert result.success is True
        assert result.status == "sent"
        assert result.report_date == report.report_date
        assert result.subject == "AIQM Daily Examination Summary — 09 Sep 2026"
        assert result.recipient_count == 4
        assert "aniket@aiqmindia.com" in result.recipients

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["subject"] == "AIQM Daily Examination Summary — 09 Sep 2026"
        assert "Alice Smith" in call_kwargs["html_body"]
        assert "Alice Smith" in call_kwargs["text_body"]


def test_correct_subject_from_report_date(app):
    """Subject passed to SMTP is strictly derived from report.report_date."""
    test_date = date(2026, 11, 25)
    report = _build_sample_report(report_date=test_date)

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        result = send_daily_exam_summary_email(report)

        expected_subject = get_daily_summary_email_subject(report)
        assert expected_subject == "AIQM Daily Examination Summary — 25 Nov 2026"
        assert result.subject == expected_subject

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["subject"] == expected_subject


def test_html_body_comes_from_phase3_renderer(app):
    """HTML body dispatched to SMTP matches the output of render_daily_summary_email."""
    report = _build_sample_report()
    expected_html = render_daily_summary_email(report)

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        send_daily_exam_summary_email(report)

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["html_body"] == expected_html


def test_configured_recipients_derive_from_authoritative_config(app):
    """Recipients derive from authoritative configuration without duplicated hardcoded lists."""
    recipients = get_daily_summary_recipients()
    assert recipients == [
        "aniket@aiqmindia.com",
        "dskode@aiqmindia.com",
        "edu@aiqmindia.com",
        "ravi@aiqmindia.com",
    ]

    report = _build_sample_report()
    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        result = send_daily_exam_summary_email(report)

        assert result.recipients == recipients
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to_addresses"] == recipients


def test_custom_recipient_override(app):
    """Explicit recipient passed to send_daily_exam_summary_email overrides the default."""
    report = _build_sample_report()

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        result = send_daily_exam_summary_email(report, recipients="supervisor@aiqmindia.com, ops@aiqmindia.com")

        assert result.recipients == ["supervisor@aiqmindia.com", "ops@aiqmindia.com"]
        assert result.recipient_count == 2
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to_addresses"] == ["supervisor@aiqmindia.com", "ops@aiqmindia.com"]


def test_daily_summary_recipients_env_override(app, monkeypatch):
    """DAILY_SUMMARY_RECIPIENTS environment variable allows independent recipient configuration."""
    monkeypatch.setenv("DAILY_SUMMARY_RECIPIENTS", "exec1@aiqmindia.com, exec2@aiqmindia.com")

    # When inside app context with current_app
    with app.app_context():
        app.config["DAILY_SUMMARY_RECIPIENTS"] = "exec1@aiqmindia.com, exec2@aiqmindia.com"
        recipients = get_daily_summary_recipients()
        assert recipients == ["exec1@aiqmindia.com", "exec2@aiqmindia.com"]


def test_smtp_send_failure_handled_cleanly(app):
    """When send_smtp_email returns False, delivery service returns a clean failed result without crashing."""
    report = _build_sample_report()

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=False) as mock_send:
        result = send_daily_exam_summary_email(report)

        assert result.success is False
        assert result.status == "failed"
        assert "failed" in result.message.lower()
        mock_send.assert_called_once()


def test_smtp_exception_handled_cleanly(app):
    """When send_smtp_email raises an exception, delivery service catches it and returns failed status."""
    report = _build_sample_report()

    with patch(
        "app.services.daily_summary_email_delivery_service.send_smtp_email",
        side_effect=smtplib.SMTPException("Relay timeout")
    ):
        result = send_daily_exam_summary_email(report)

        assert result.success is False
        assert result.status == "failed"
        assert "Relay timeout" in result.message


def test_empty_daily_report_skipped_by_default(app):
    """When total_submissions == 0 and skip_if_empty is True (default), email delivery is suppressed."""
    report = _build_sample_report(total_submissions=0)

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email") as mock_send:
        result = send_daily_exam_summary_email(report)

        assert result.success is True
        assert result.status == "skipped_empty"
        assert result.recipient_count == 0
        assert "skipped" in result.message.lower()

        # send_smtp_email must NOT be called
        mock_send.assert_not_called()


def test_empty_daily_report_sent_when_skip_if_empty_false(app):
    """When total_submissions == 0 and skip_if_empty is False, email is sent with empty state HTML."""
    report = _build_sample_report(total_submissions=0)

    with patch("app.services.daily_summary_email_delivery_service.send_smtp_email", return_value=True) as mock_send:
        result = send_daily_exam_summary_email(report, skip_if_empty=False)

        assert result.success is True
        assert result.status == "sent"
        mock_send.assert_called_once()

        call_kwargs = mock_send.call_args.kwargs
        assert "No examinations were submitted on this date" in call_kwargs["html_body"]


def test_no_recipients_configured_handled_cleanly(app):
    """When no recipients are available, returns no_recipients status without attempting SMTP."""
    report = _build_sample_report()

    with patch("app.services.daily_summary_email_delivery_service.get_daily_summary_recipients", return_value=[]):
        with patch("app.services.daily_summary_email_delivery_service.send_smtp_email") as mock_send:
            result = send_daily_exam_summary_email(report)

            assert result.success is False
            assert result.status == "no_recipients"
            assert "No valid recipients" in result.message
            mock_send.assert_not_called()


def test_plain_text_fallback_generation():
    """Verifies plain-text fallback summary structure for both submitted and empty reports."""
    # 1. Report with submissions
    report = _build_sample_report(total_submissions=1)
    text = build_daily_summary_text_fallback(report)
    assert "Daily Examination Summary" in text
    assert "• Total Submissions : 1" in text
    assert "• Passed            : 1" in text
    assert "Apex Corp" in text
    assert "Alice Smith" in text

    # 2. Empty report
    empty_report = _build_sample_report(total_submissions=0)
    empty_text = build_daily_summary_text_fallback(empty_report)
    assert "No examinations were submitted on this date" in empty_text
