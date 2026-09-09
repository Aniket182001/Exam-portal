from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import event

from app.extensions import db
from app.services.daily_summary_service import (
    DailyExamSummaryReport,
    DailyCompanyGroupSummary,
    DailySummaryAttemptItem,
)
from app.services.daily_summary_email_service import (
    render_daily_summary_email,
    get_daily_summary_email_subject,
    format_metric,
    format_score,
    format_percentage,
)


# ---------------------------------------------------------------------------
# Fixtures & Test Data Builders
# ---------------------------------------------------------------------------

def _build_mock_item(
    attempt_id=1,
    candidate_name="Alice Smith",
    candidate_email="alice@example.com",
    exam_id=10,
    exam_title="Certified Lean Six Sigma Green Belt",
    exam_code="LSSGB-01",
    company_name="Apex Corp",
    raw_company_name="Apex Corp",
    attempt_number=1,
    submitted_at=None,
    submitted_at_str="09-Sep-2026 04:30 PM IST",
    score=22.5,
    max_marks=25.0,
    percentage=90.0,
    result_status="Pass",
    evaluation_status="not_required",
):
    if submitted_at is None:
        submitted_at = datetime(2026, 9, 9, 16, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    return DailySummaryAttemptItem(
        attempt_id=attempt_id,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        exam_id=exam_id,
        exam_title=exam_title,
        exam_code=exam_code,
        company_name=company_name,
        raw_company_name=raw_company_name,
        attempt_number=attempt_number,
        submitted_at=submitted_at,
        submitted_at_str=submitted_at_str,
        score=score,
        max_marks=max_marks,
        percentage=percentage,
        result_status=result_status,
        evaluation_status=evaluation_status,
    )


def _build_sample_report(report_date=date(2026, 9, 9)):
    item1 = _build_mock_item(
        attempt_id=1,
        candidate_name="Alice Smith",
        exam_title="Lean Six Sigma",
        exam_code="LSS-01",
        company_name="ABC Pvt Ltd",
        attempt_number=1,
        score=20.0,
        max_marks=25.0,
        percentage=80.0,
        result_status="Pass",
        submitted_at_str="09-Sep-2026 11:00 AM IST",
    )
    item2 = _build_mock_item(
        attempt_id=2,
        candidate_name="Bob Jones",
        exam_title="Lean Six Sigma",
        exam_code="LSS-01",
        company_name="ABC Pvt Ltd",
        attempt_number=2,
        score=10.0,
        max_marks=25.0,
        percentage=40.0,
        result_status="Fail",
        submitted_at_str="09-Sep-2026 01:15 PM IST",
    )
    group1 = DailyCompanyGroupSummary(
        company_name="ABC Pvt Ltd",
        total_submissions=2,
        total_passed=1,
        total_failed=1,
        total_unevaluated=0,
        attempts=[item1, item2],
    )

    item3 = _build_mock_item(
        attempt_id=3,
        candidate_name="Charlie Brown",
        exam_title="ISO 9001 Auditor",
        exam_code="ISO-01",
        company_name="Independent / No Company",
        attempt_number=1,
        score=15.0,
        max_marks=20.0,
        percentage=None,  # pending evaluation
        result_status="Under Evaluation",
        evaluation_status="pending",
        submitted_at_str="09-Sep-2026 03:45 PM IST",
    )
    group2 = DailyCompanyGroupSummary(
        company_name="Independent / No Company",
        total_submissions=1,
        total_passed=0,
        total_failed=0,
        total_unevaluated=1,
        attempts=[item3],
    )

    return DailyExamSummaryReport(
        report_date=report_date,
        total_submissions=3,
        total_passed=1,
        total_failed=1,
        total_unevaluated=1,
        total_companies=2,
        named_companies_count=1,
        company_groups=[group1, group2],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_render_normal_report_success(app):
    """Normal report renders successfully into a valid HTML document."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "Daily Examination Summary" in html
        assert "Asian Institute of Quality Management (AIQM)" in html


def test_report_date_formatting(app):
    """Report date appears formatted as e.g. '09 September 2026'."""
    with app.app_context():
        report = _build_sample_report(date(2026, 9, 9))
        html = render_daily_summary_email(report)

        assert "09 September 2026" in html


def test_overall_totals_appear_accurately(app):
    """Overall summary statistics match the report values."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        # 3 total submissions, 1 passed, 1 failed, 1 under eval, 2 companies
        assert ">3<" in html  # Submissions count
        assert ">1<" in html  # Passed / Failed / Under Eval count
        assert ">2<" in html  # Companies count


def test_multiple_company_groups_render_as_separate_sections(app):
    """Each company group renders as its own section and table."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "ABC Pvt Ltd" in html
        assert "Independent / No Company" in html
        # Both company headers are rendered
        assert html.count("class=\"company-name\"") == 2


def test_candidate_rows_contain_expected_values(app):
    """Candidate rows display candidate name, exam title, score, percentage, etc."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "Alice Smith" in html
        assert "Bob Jones" in html
        assert "Charlie Brown" in html
        assert "Lean Six Sigma" in html
        assert "ISO 9001 Auditor" in html


def test_attempt_numbers_displayed_cleanly(app):
    """Attempt numbers are formatted cleanly as '#1', '#2'."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "#1" in html
        assert "#2" in html


def test_pass_fail_under_eval_statuses(app):
    """Result statuses 'Pass', 'Fail', 'Under Evaluation' appear with correct text and badges."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "badge-pass" in html
        assert "Pass" in html
        assert "badge-fail" in html
        assert "Fail" in html
        assert "badge-eval" in html
        assert "Under Evaluation" in html


def test_percentage_none_renders_safely(app):
    """When percentage is None, an em-dash '—' is displayed rather than 'None%'."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "—" in html
        assert "None%" not in html


def test_submission_time_uses_submitted_at_str(app):
    """Submission time displays Phase 2's pre-formatted submitted_at_str."""
    with app.app_context():
        report = _build_sample_report()
        html = render_daily_summary_email(report)

        assert "09-Sep-2026 11:00 AM IST" in html
        assert "09-Sep-2026 01:15 PM IST" in html
        assert "09-Sep-2026 03:45 PM IST" in html


def test_empty_report_renders_clean_empty_state(app):
    """When total_submissions == 0, renders a professional empty state without errors."""
    with app.app_context():
        empty_report = DailyExamSummaryReport(
            report_date=date(2026, 9, 9),
            total_submissions=0,
            total_passed=0,
            total_failed=0,
            total_unevaluated=0,
            total_companies=0,
            named_companies_count=0,
            company_groups=[],
        )
        html = render_daily_summary_email(empty_report)

        assert "No examinations were submitted on this date." in html
        assert "09 September 2026" in html
        assert "class=\"company-block\"" not in html
        assert "class=\"data-table\"" not in html


def test_company_names_with_html_characters_escaped(app):
    """Company names containing characters like '<', '>', '&', '\"' are escaped safely."""
    with app.app_context():
        item = _build_mock_item(
            candidate_name="Normal Candidate",
            company_name="Acme <Script> & \"Co\"",
        )
        group = DailyCompanyGroupSummary(
            company_name="Acme <Script> & \"Co\"",
            total_submissions=1,
            total_passed=1,
            total_failed=0,
            total_unevaluated=0,
            attempts=[item],
        )
        report = DailyExamSummaryReport(
            report_date=date(2026, 9, 9),
            total_submissions=1,
            total_passed=1,
            total_failed=0,
            total_unevaluated=0,
            total_companies=1,
            named_companies_count=1,
            company_groups=[group],
        )

        html = render_daily_summary_email(report)
        assert "<Script>" not in html
        assert "&lt;Script&gt;" in html
        assert "&amp;" in html


def test_candidate_and_exam_with_html_characters_escaped(app):
    """Candidate names and exam titles with HTML injection characters are escaped safely."""
    with app.app_context():
        item = _build_mock_item(
            candidate_name="<b>Mallory</b>",
            exam_title="Exam <img src=x onerror=alert(1)>",
            exam_code="EX<01>",
            company_name="Safe Co",
        )
        group = DailyCompanyGroupSummary(
            company_name="Safe Co",
            total_submissions=1,
            total_passed=1,
            total_failed=0,
            total_unevaluated=0,
            attempts=[item],
        )
        report = DailyExamSummaryReport(
            report_date=date(2026, 9, 9),
            total_submissions=1,
            total_passed=1,
            total_failed=0,
            total_unevaluated=0,
            total_companies=1,
            named_companies_count=1,
            company_groups=[group],
        )

        html = render_daily_summary_email(report)
        assert "<b>Mallory</b>" not in html
        assert "&lt;b&gt;Mallory&lt;/b&gt;" in html
        assert "<img src=x" not in html
        assert "&lt;img src=x" in html


def test_renderer_does_not_query_or_modify_database(app):
    """Verify that render_daily_summary_email performs ZERO database queries."""
    with app.app_context():
        report = _build_sample_report()

        executed_queries = []

        def capture_sql(conn, cursor, statement, parameters, context, executemany):
            executed_queries.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture_sql)
        try:
            html = render_daily_summary_email(report)
            assert len(executed_queries) == 0, f"Expected 0 queries, got: {executed_queries}"
            assert len(html) > 0
        finally:
            event.remove(db.engine, "before_cursor_execute", capture_sql)


def test_email_subject_generation(app):
    """Subject helper uses report date and matches specified format."""
    report = DailyExamSummaryReport(
        report_date=date(2026, 9, 9),
        total_submissions=0,
        total_passed=0,
        total_failed=0,
        total_unevaluated=0,
        total_companies=0,
        named_companies_count=0,
        company_groups=[],
    )
    subject = get_daily_summary_email_subject(report)
    assert subject == "AIQM Daily Examination Summary — 09 Sep 2026"


def test_format_helpers():
    """Unit test for formatting helpers (format_metric, format_score, format_percentage)."""
    assert format_metric(None) == "-"
    assert format_metric(20.0) == "20"
    assert format_metric(22.5) == "22.5"

    assert format_score(None, 25.0) == "-"
    assert format_score(20.0, 25.0) == "20 / 25"
    assert format_score(22.5, 50.0) == "22.5 / 50"
    assert format_score(15.0, None) == "15"

    assert format_percentage(None) == "—"
    assert format_percentage(80.0) == "80%"
    assert format_percentage(84.5) == "84.5%"
