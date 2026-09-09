import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest

from app.extensions import db
from app.models import Exam, Question, QuestionOption, StudentAttempt, CompanyGroup, CompanyAlias
from app.services.company_service import create_company_group, add_alias_to_group
from app.services.daily_summary_service import (
    generate_daily_exam_summary,
    to_utc_aware,
    to_exam_local_datetime,
    DailyExamSummaryReport,
    DailyCompanyGroupSummary,
    DailySummaryAttemptItem,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_test_data(app):
    """Ensure a clean database state for every test."""
    with app.app_context():
        StudentAttempt.query.delete()
        QuestionOption.query.delete()
        Question.query.delete()
        Exam.query.delete()
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()
        yield
        StudentAttempt.query.delete()
        QuestionOption.query.delete()
        Question.query.delete()
        Exam.query.delete()
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()


def _create_test_exam(title="Daily Exam", code="DLY01", tz="Asia/Kolkata", passing_val=50.0):
    exam = Exam(
        title=title,
        exam_code=code,
        duration_minutes=60,
        passing_type="percentage",
        passing_value=passing_val,
        timezone=tz,
    )
    db.session.add(exam)
    db.session.flush()

    q1 = Question(exam_id=exam.id, question_text="Question 1", marks=10.0, question_type="mcq")
    q2 = Question(exam_id=exam.id, question_text="Question 2", marks=15.0, question_type="mcq")
    db.session.add_all([q1, q2])
    db.session.flush()

    opt1 = QuestionOption(question_id=q1.id, option_text="Opt A", option_order=0)
    opt2 = QuestionOption(question_id=q1.id, option_text="Opt B", option_order=1)
    db.session.add_all([opt1, opt2])
    db.session.flush()
    q1.correct_option_id = opt1.id

    db.session.commit()
    return exam


def _create_attempt(
    exam,
    student_name="Candidate",
    student_email="candidate@example.com",
    company_name=None,
    status="submitted",
    submitted_at=None,
    started_at=None,
    score=20.0,
    percentage_score=80.0,
    result_status="Pass",
    evaluation_status="not_required",
):
    if submitted_at and started_at is None:
        started_at = submitted_at - timedelta(minutes=30)
    elif started_at is None:
        started_at = datetime.now(timezone.utc) - timedelta(minutes=30)

    attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=student_name,
        student_email=student_email,
        company_name=company_name,
        attempt_token=f"token-{uuid.uuid4().hex[:10]}",
        status=status,
        started_at=started_at,
        submitted_at=submitted_at,
        score=score,
        total_marks_obtained=score,
        percentage_score=percentage_score,
        result_status=result_status,
        evaluation_status=evaluation_status,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_submitted_attempts_returns_empty_report(app):
    """When there are no qualifying submitted attempts, return valid report with 0 submissions."""
    with app.app_context():
        report_date = date(2026, 9, 9)
        report = generate_daily_exam_summary(report_date)

        assert isinstance(report, DailyExamSummaryReport)
        assert report.report_date == report_date
        assert report.total_submissions == 0
        assert report.total_passed == 0
        assert report.total_failed == 0
        assert report.total_unevaluated == 0
        assert report.total_companies == 0
        assert report.named_companies_count == 0
        assert report.company_groups == []

        d = report.to_dict()
        assert d["total_submissions"] == 0
        assert d["company_groups"] == []


def test_single_submitted_attempt_appears_correctly(app):
    """A single submitted attempt appears in the summary with all fields populated accurately."""
    with app.app_context():
        exam = _create_test_exam("LSS Green Belt", "LSSGB-01", tz="Asia/Kolkata")
        sub_utc = datetime(2026, 9, 9, 10, 0, 0)  # 15:30 IST on 2026-09-09

        att = _create_attempt(
            exam,
            student_name="Alice Smith",
            student_email="alice@example.com",
            company_name="Apex Corp",
            status="submitted",
            submitted_at=sub_utc,
            score=25.0,
            percentage_score=100.0,
            result_status="Pass",
        )

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 1
        assert report.total_passed == 1
        assert report.total_failed == 0
        assert report.total_unevaluated == 0
        assert report.total_companies == 1
        assert report.named_companies_count == 1
        assert len(report.company_groups) == 1

        grp = report.company_groups[0]
        assert grp.company_name == "Apex Corp"
        assert grp.total_submissions == 1
        assert grp.total_passed == 1
        assert len(grp.attempts) == 1

        item = grp.attempts[0]
        assert item.attempt_id == att.id
        assert item.candidate_name == "Alice Smith"
        assert item.candidate_email == "alice@example.com"
        assert item.exam_title == "LSS Green Belt"
        assert item.exam_code == "LSSGB-01"
        assert item.company_name == "Apex Corp"
        assert item.raw_company_name == "Apex Corp"
        assert item.attempt_number == 1
        assert item.score == 25.0
        assert item.max_marks == 25.0  # 10 + 15 marks
        assert item.percentage == 100.0
        assert item.result_status == "Pass"
        assert item.evaluation_status == "not_required"
        assert "09-Sep-2026" in item.submitted_at_str
        assert "IST" in item.submitted_at_str


def test_in_progress_and_expired_attempts_are_excluded(app):
    """In-progress, expired, or unsubmitted attempts must NOT appear in the daily report."""
    with app.app_context():
        exam = _create_test_exam("Lean Practitioner", "LP-01", tz="Asia/Kolkata")
        sub_utc = datetime(2026, 9, 9, 8, 0, 0)

        # 1. Submitted attempt (should appear)
        _create_attempt(exam, student_name="Submitted Bob", status="submitted", submitted_at=sub_utc)

        # 2. In-progress attempt without submission (should NOT appear)
        _create_attempt(exam, student_name="In-Progress Carol", status="in_progress", submitted_at=None)

        # 3. Expired attempt without submission (should NOT appear)
        _create_attempt(exam, student_name="Expired Dan", status="expired", submitted_at=None)

        # 4. Attempt with submitted_at on a different day (should NOT appear)
        diff_day_utc = datetime(2026, 9, 10, 8, 0, 0)
        _create_attempt(exam, student_name="Tomorrow Eve", status="submitted", submitted_at=diff_day_utc)

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 1
        candidate_names = [a.candidate_name for g in report.company_groups for a in g.attempts]
        assert candidate_names == ["Submitted Bob"]


def test_passed_failed_and_unevaluated_results(app):
    """Report accurately tallies passed, failed, and under-evaluation attempts."""
    with app.app_context():
        exam = _create_test_exam("Six Sigma Black Belt", "SSBB-01", tz="Asia/Kolkata")
        sub_utc = datetime(2026, 9, 9, 6, 0, 0)

        # Passed
        _create_attempt(
            exam,
            student_name="Passer",
            student_email="passer@example.com",
            score=20.0,
            percentage_score=80.0,
            result_status="Pass",
            submitted_at=sub_utc,
        )

        # Failed
        _create_attempt(
            exam,
            student_name="Failer",
            student_email="failer@example.com",
            score=5.0,
            percentage_score=20.0,
            result_status="Fail",
            submitted_at=sub_utc + timedelta(minutes=10),
        )

        # Pending evaluation (mixed exam question)
        _create_attempt(
            exam,
            student_name="Pending Student",
            student_email="pending@example.com",
            score=10.0,
            percentage_score=40.0,
            result_status=None,
            evaluation_status="pending",
            submitted_at=sub_utc + timedelta(minutes=20),
        )

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 3
        assert report.total_passed == 1
        assert report.total_failed == 1
        assert report.total_unevaluated == 1

        all_items = [item for g in report.company_groups for item in g.attempts]
        statuses = {item.candidate_name: item.result_status for item in all_items}
        assert statuses["Passer"] == "Pass"
        assert statuses["Failer"] == "Fail"
        assert statuses["Pending Student"] == "Under Evaluation"


def test_multiple_exams_on_same_day_unified(app):
    """Attempts from multiple distinct exams on the same date are consolidated into ONE report."""
    with app.app_context():
        exam1 = _create_test_exam("CKLM Exam", "CKLM-01", tz="Asia/Kolkata")
        exam2 = _create_test_exam("CLP Exam", "CLP-01", tz="Asia/Kolkata")

        sub_utc = datetime(2026, 9, 9, 9, 0, 0)

        _create_attempt(exam1, student_name="CKLM Student", company_name="Company X", submitted_at=sub_utc)
        _create_attempt(exam2, student_name="CLP Student", company_name="Company X", submitted_at=sub_utc)

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 2
        assert report.total_companies == 1  # Both under Company X
        grp = report.company_groups[0]
        assert len(grp.attempts) == 2
        exam_titles = {a.exam_title for a in grp.attempts}
        assert exam_titles == {"CKLM Exam", "CLP Exam"}


def test_company_grouping_normalization_and_aliases(app):
    """
    Verifies:
    - Case/whitespace/period variations normalize into the canonical group.
    - Explicit alias resolves to the canonical group.
    - Similar but unmapped company remains separate.
    - Unassigned candidate groups under 'Independent / No Company'.
    """
    with app.app_context():
        # Setup canonical group & alias
        CompanyAlias.query.delete()
        CompanyGroup.query.delete()
        db.session.commit()

        group, err = create_company_group("ABC Pvt Ltd", aliases=["ABC Private Limited", "ABC India"])
        assert err is None

        # Similar but unmapped group created intentionally
        group2, err2 = create_company_group("ABC Technologies")
        assert err2 is None

        exam = _create_test_exam("Quality Specialist", "QS-01", tz="Asia/Kolkata")
        sub_utc = datetime(2026, 9, 9, 8, 0, 0)

        # 1. Exact canonical name
        _create_attempt(exam, student_name="User 1", company_name="ABC Pvt Ltd", submitted_at=sub_utc)
        # 2. Case, whitespace, period variation
        _create_attempt(exam, student_name="User 2", company_name="  ABC   PVT.   LTD.  ", submitted_at=sub_utc + timedelta(minutes=5))
        # 3. Explicit alias
        _create_attempt(exam, student_name="User 3", company_name="ABC Private Limited", submitted_at=sub_utc + timedelta(minutes=10))
        # 4. Similar but separate organization
        _create_attempt(exam, student_name="User 4", company_name="ABC Technologies", submitted_at=sub_utc + timedelta(minutes=15))
        # 5. Unmapped independent company
        _create_attempt(exam, student_name="User 5", company_name="Acme Solutions", submitted_at=sub_utc + timedelta(minutes=20))
        # 6. No company entered
        _create_attempt(exam, student_name="User 6", company_name="", submitted_at=sub_utc + timedelta(minutes=25))
        # 7. None company entered
        _create_attempt(exam, student_name="User 7", company_name=None, submitted_at=sub_utc + timedelta(minutes=30))

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 7
        # 4 distinct groups: ABC Pvt Ltd (3), ABC Technologies (1), Acme Solutions (1), Independent / No Company (2)
        assert report.total_companies == 4
        assert report.named_companies_count == 3

        group_map = {g.company_name: g for g in report.company_groups}

        # ABC Pvt Ltd has 3 candidates
        assert "ABC Pvt Ltd" in group_map
        assert len(group_map["ABC Pvt Ltd"].attempts) == 3
        assert [a.candidate_name for a in group_map["ABC Pvt Ltd"].attempts] == ["User 1", "User 2", "User 3"]

        # ABC Technologies is kept separate
        assert "ABC Technologies" in group_map
        assert len(group_map["ABC Technologies"].attempts) == 1
        assert group_map["ABC Technologies"].attempts[0].candidate_name == "User 4"

        # Acme Solutions is kept separate
        assert "Acme Solutions" in group_map
        assert len(group_map["Acme Solutions"].attempts) == 1
        assert group_map["Acme Solutions"].attempts[0].candidate_name == "User 5"

        # Independent / No Company has the 2 unassigned candidates
        assert "Independent / No Company" in group_map
        assert len(group_map["Independent / No Company"].attempts) == 2
        assert [a.candidate_name for a in group_map["Independent / No Company"].attempts] == ["User 6", "User 7"]


def test_multiple_attempts_by_same_candidate(app):
    """Multiple submitted attempts by the same candidate receive sequential attempt numbers."""
    with app.app_context():
        exam = _create_test_exam("Retest Exam", "RET-01", tz="Asia/Kolkata")
        base_time = datetime(2026, 9, 9, 7, 0, 0)

        # Attempt 1 (earlier)
        att1 = _create_attempt(
            exam,
            student_name="Retest Bob",
            student_email="bob@example.com",
            started_at=base_time,
            submitted_at=base_time + timedelta(minutes=25),
            score=10.0,
            percentage_score=40.0,
            result_status="Fail",
        )

        # Attempt 2 (later on same day)
        att2 = _create_attempt(
            exam,
            student_name="Retest Bob",
            student_email="bob@example.com",
            started_at=base_time + timedelta(hours=2),
            submitted_at=base_time + timedelta(hours=2, minutes=25),
            score=22.0,
            percentage_score=88.0,
            result_status="Pass",
        )

        report = generate_daily_exam_summary(date(2026, 9, 9))

        assert report.total_submissions == 2
        items = [a for g in report.company_groups for a in g.attempts]
        items_by_id = {it.attempt_id: it for it in items}

        assert items_by_id[att1.id].attempt_number == 1
        assert items_by_id[att1.id].result_status == "Fail"
        assert items_by_id[att2.id].attempt_number == 2
        assert items_by_id[att2.id].result_status == "Pass"


def test_date_boundary_and_exam_timezone_handling(app):
    """
    Verifies that submission inclusion strictly follows the exam's timezone:
    1. Asia/Kolkata (UTC+5:30):
       - 2026-09-08 18:29:59 UTC -> 2026-09-08 23:59:59 IST (Excluded from 2026-09-09)
       - 2026-09-08 18:30:00 UTC -> 2026-09-09 00:00:00 IST (Included in 2026-09-09)
       - 2026-09-09 18:29:59 UTC -> 2026-09-09 23:59:59 IST (Included in 2026-09-09)
       - 2026-09-09 18:30:00 UTC -> 2026-09-10 00:00:00 IST (Excluded from 2026-09-09)
    2. America/New_York (EDT = UTC-4):
       - 2026-09-09 03:59:59 UTC -> 2026-09-08 23:59:59 EDT (Excluded from 2026-09-09)
       - 2026-09-09 04:00:00 UTC -> 2026-09-09 00:00:00 EDT (Included in 2026-09-09)
       - 2026-09-10 03:59:59 UTC -> 2026-09-09 23:59:59 EDT (Included in 2026-09-09)
       - 2026-09-10 04:00:00 UTC -> 2026-09-10 00:00:00 EDT (Excluded from 2026-09-09)
    """
    with app.app_context():
        exam_ist = _create_test_exam("Kolkata Exam", "TZ-IST", tz="Asia/Kolkata")
        exam_ny = _create_test_exam("New York Exam", "TZ-NY", tz="America/New_York")

        # IST boundary cases
        att_ist_before = _create_attempt(exam_ist, student_name="IST Before", submitted_at=datetime(2026, 9, 8, 18, 29, 59))
        att_ist_start = _create_attempt(exam_ist, student_name="IST Start", submitted_at=datetime(2026, 9, 8, 18, 30, 0))
        att_ist_end = _create_attempt(exam_ist, student_name="IST End", submitted_at=datetime(2026, 9, 9, 18, 29, 59))
        att_ist_after = _create_attempt(exam_ist, student_name="IST After", submitted_at=datetime(2026, 9, 9, 18, 30, 0))

        # NY boundary cases
        att_ny_before = _create_attempt(exam_ny, student_name="NY Before", submitted_at=datetime(2026, 9, 9, 3, 59, 59))
        att_ny_start = _create_attempt(exam_ny, student_name="NY Start", submitted_at=datetime(2026, 9, 9, 4, 0, 0))
        att_ny_end = _create_attempt(exam_ny, student_name="NY End", submitted_at=datetime(2026, 9, 10, 3, 59, 59))
        att_ny_after = _create_attempt(exam_ny, student_name="NY After", submitted_at=datetime(2026, 9, 10, 4, 0, 0))

        report = generate_daily_exam_summary(date(2026, 9, 9))

        included_names = {a.candidate_name for g in report.company_groups for a in g.attempts}

        # IST checks
        assert "IST Before" not in included_names
        assert "IST Start" in included_names
        assert "IST End" in included_names
        assert "IST After" not in included_names

        # NY checks
        assert "NY Before" not in included_names
        assert "NY Start" in included_names
        assert "NY End" in included_names
        assert "NY After" not in included_names

        assert report.total_submissions == 4


def test_deterministic_ordering(app):
    """
    Repeated generation produces the exact same ordering:
    - Company groups: alphabetical by name, with 'Independent / No Company' last.
    - Candidates within group: submitted_at asc, candidate_name asc, attempt_id asc.
    """
    with app.app_context():
        exam = _create_test_exam("Order Exam", "ORD-01", tz="Asia/Kolkata")
        base = datetime(2026, 9, 9, 8, 0, 0)

        _create_attempt(exam, student_name="Zack", company_name="Zeta Ltd", submitted_at=base)
        _create_attempt(exam, student_name="Anna", company_name="Alpha Corp", submitted_at=base + timedelta(minutes=5))
        _create_attempt(exam, student_name="Aaron", company_name="Alpha Corp", submitted_at=base)
        _create_attempt(exam, student_name="Solo", company_name=None, submitted_at=base)

        report1 = generate_daily_exam_summary(date(2026, 9, 9))
        report2 = generate_daily_exam_summary(date(2026, 9, 9))

        # Check company groups ordering
        group_names1 = [g.company_name for g in report1.company_groups]
        group_names2 = [g.company_name for g in report2.company_groups]
        assert group_names1 == group_names2
        assert group_names1 == ["Alpha Corp", "Zeta Ltd", "Independent / No Company"]

        # Check candidates within Alpha Corp: Aaron (base) before Anna (base + 5m)
        alpha_candidates = [a.candidate_name for a in report1.company_groups[0].attempts]
        assert alpha_candidates == ["Aaron", "Anna"]


def test_summary_matches_authoritative_attempt_result_logic(app):
    """
    User Correction 3:
    Explicitly verifies that the daily summary's score, percentage, maximum marks,
    and result status match the existing authoritative attempt/result values.
    """
    with app.app_context():
        exam = _create_test_exam("Auth Logic Exam", "AUTH-01", tz="Asia/Kolkata")
        sub_utc = datetime(2026, 9, 9, 10, 0, 0)

        # 1. Passed MCQ Attempt
        att_pass = _create_attempt(
            exam,
            student_name="Passed Student",
            student_email="pass@example.com",
            company_name="Acme",
            score=20.0,
            percentage_score=80.0,
            result_status="Pass",
            evaluation_status="not_required",
            submitted_at=sub_utc,
        )

        # 2. Failed MCQ Attempt
        att_fail = _create_attempt(
            exam,
            student_name="Failed Student",
            student_email="fail@example.com",
            company_name="Acme",
            score=5.0,
            percentage_score=20.0,
            result_status="Fail",
            evaluation_status="not_required",
            submitted_at=sub_utc + timedelta(minutes=5),
        )

        # 3. Mixed exam / Subjective pending evaluation
        att_pending = _create_attempt(
            exam,
            student_name="Pending Student",
            student_email="pending@example.com",
            company_name="Acme",
            score=12.0,
            percentage_score=48.0,
            result_status=None,
            evaluation_status="pending",
            submitted_at=sub_utc + timedelta(minutes=10),
        )

        report = generate_daily_exam_summary(date(2026, 9, 9))

        items_by_id = {
            item.attempt_id: item
            for g in report.company_groups
            for item in g.attempts
        }

        # Check Passed
        item_p = items_by_id[att_pass.id]
        expected_score_p = att_pass.total_marks_obtained if att_pass.total_marks_obtained is not None else att_pass.score
        expected_max_p = sum(q.marks for q in exam.questions)
        assert item_p.score == expected_score_p == 20.0
        assert item_p.max_marks == expected_max_p == 25.0
        assert item_p.percentage == att_pass.percentage_score == 80.0
        assert item_p.result_status == att_pass.result_status == "Pass"
        assert item_p.evaluation_status == att_pass.evaluation_status == "not_required"

        # Check Failed
        item_f = items_by_id[att_fail.id]
        expected_score_f = att_fail.total_marks_obtained if att_fail.total_marks_obtained is not None else att_fail.score
        assert item_f.score == expected_score_f == 5.0
        assert item_f.max_marks == expected_max_p == 25.0
        assert item_f.percentage == att_fail.percentage_score == 20.0
        assert item_f.result_status == att_fail.result_status == "Fail"
        assert item_f.evaluation_status == att_fail.evaluation_status == "not_required"

        # Check Pending
        item_pend = items_by_id[att_pending.id]
        expected_score_pend = att_pending.total_marks_obtained if att_pending.total_marks_obtained is not None else att_pending.score
        assert item_pend.score == expected_score_pend == 12.0
        assert item_pend.max_marks == expected_max_p == 25.0
        assert item_pend.percentage == att_pending.percentage_score == 48.0
        assert item_pend.result_status == "Under Evaluation"  # authoritative display for pending
        assert item_pend.evaluation_status == att_pending.evaluation_status == "pending"
