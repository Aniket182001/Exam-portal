import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.exam import Exam
from app.models.student_attempt import StudentAttempt
from app.services import company_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class DailySummaryAttemptItem:
    attempt_id: int
    candidate_name: str
    candidate_email: str
    exam_id: int
    exam_title: str
    exam_code: str
    company_name: str
    raw_company_name: str | None
    attempt_number: int
    submitted_at: datetime
    submitted_at_str: str
    score: float
    max_marks: float
    percentage: float | None
    result_status: str
    evaluation_status: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["submitted_at"] = self.submitted_at.isoformat() if self.submitted_at else None
        return d


@dataclass
class DailyCompanyGroupSummary:
    company_name: str
    total_submissions: int
    total_passed: int
    total_failed: int
    total_unevaluated: int
    attempts: list[DailySummaryAttemptItem]

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "total_submissions": self.total_submissions,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_unevaluated": self.total_unevaluated,
            "attempts": [a.to_dict() for a in self.attempts],
        }


@dataclass
class DailyExamSummaryReport:
    report_date: date
    total_submissions: int
    total_passed: int
    total_failed: int
    total_unevaluated: int
    total_companies: int
    named_companies_count: int
    company_groups: list[DailyCompanyGroupSummary]

    def to_dict(self) -> dict:
        return {
            "report_date": self.report_date.isoformat(),
            "total_submissions": self.total_submissions,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_unevaluated": self.total_unevaluated,
            "total_companies": self.total_companies,
            "named_companies_count": self.named_companies_count,
            "company_groups": [g.to_dict() for g in self.company_groups],
        }


# ---------------------------------------------------------------------------
# Timezone & Datetime Utilities
# ---------------------------------------------------------------------------

def to_utc_aware(dt: datetime | None) -> datetime | None:
    """
    Ensures a datetime is timezone-aware in UTC.
    The exam portal stores datetimes as naive UTC in PostgreSQL/SQLite.
    If tzinfo is None, it is safely marked as UTC.
    If tzinfo is already present, it is converted to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_exam_local_datetime(dt: datetime | None, exam_tz_name: str | None) -> datetime | None:
    """
    Converts a stored datetime to the exam's configured IANA timezone.
    Falls back to 'Asia/Kolkata' if invalid or not specified.
    """
    utc_dt = to_utc_aware(dt)
    if utc_dt is None:
        return None
    tz_str = exam_tz_name or "Asia/Kolkata"
    try:
        exam_tz = ZoneInfo(tz_str)
    except Exception:
        exam_tz = ZoneInfo("Asia/Kolkata")
    return utc_dt.astimezone(exam_tz)


def format_attempt_submission_time(dt_local: datetime) -> str:
    """Formats an aware local datetime as '09-Sep-2026 08:30 PM IST'."""
    return dt_local.strftime("%d-%b-%Y %I:%M %p %Z")


# ---------------------------------------------------------------------------
# Attempt Sequence & Numbering Helpers
# ---------------------------------------------------------------------------

def _batch_calculate_attempt_numbers(
    candidate_exam_pairs: set[tuple[int, str]]
) -> dict[int, int]:
    """
    For a set of (exam_id, student_email) pairs, loads all attempts chronologically
    and computes their 1-based attempt sequence numbers.
    Returns mapping: attempt_id -> attempt_number (1, 2, 3...).
    """
    if not candidate_exam_pairs:
        return {}

    attempt_num_map: dict[int, int] = {}

    for exam_id, email in candidate_exam_pairs:
        all_candidate_attempts = StudentAttempt.query.filter(
            StudentAttempt.exam_id == exam_id,
            StudentAttempt.student_email == email
        ).order_by(
            StudentAttempt.started_at.asc(),
            StudentAttempt.id.asc()
        ).all()

        for idx, att in enumerate(all_candidate_attempts, start=1):
            attempt_num_map[att.id] = idx

    return attempt_num_map


# ---------------------------------------------------------------------------
# Main Report Generator
# ---------------------------------------------------------------------------

def generate_daily_exam_summary(report_date: date | str | datetime) -> DailyExamSummaryReport:
    """
    Generates a consolidated Daily Examination Summary for the given calendar date.

    Authoritative inclusion rules:
    - Only attempts with status == 'submitted' and submitted_at is not None qualify.
    - An attempt belongs to report_date if its submitted_at timestamp, when converted
      to the specific Exam.timezone, falls on report_date.
    - Reuses Phase 1 company normalization & alias mapping.
    - Reuses existing scoring / percentage / result_status logic.
    - Deterministic ordering:
        * Company groups sorted alphabetically, with 'Independent / No Company' at end.
        * Candidates within group sorted by submitted_at ascending, candidate_name ascending, attempt_id ascending.
    """
    # 1. Parse / normalize report_date
    if isinstance(report_date, str):
        target_date = date.fromisoformat(report_date)
    elif isinstance(report_date, datetime):
        target_date = report_date.date()
    elif isinstance(report_date, date):
        target_date = report_date
    else:
        raise ValueError(f"Unsupported report_date type: {type(report_date)}")

    # 2. Database query with broad UTC pre-filter window.
    # Across any IANA timezone on Earth (UTC-12 to UTC+14), local times on target_date
    # fall strictly within [target_date - 1 day 00:00:00 UTC, target_date + 2 days 23:59:59 UTC].
    # NOTE: This window is used strictly as an indexed DB pre-filter; authoritative
    # inclusion is verified per attempt against its specific exam.timezone below.
    utc_prefilter_start = datetime.combine(target_date - timedelta(days=1), time.min)
    utc_prefilter_end = datetime.combine(target_date + timedelta(days=2), time.max)

    candidate_attempts = StudentAttempt.query.options(
        joinedload(StudentAttempt.exam).joinedload(Exam.questions)
    ).filter(
        StudentAttempt.status == "submitted",
        StudentAttempt.submitted_at.isnot(None),
        StudentAttempt.submitted_at >= utc_prefilter_start,
        StudentAttempt.submitted_at <= utc_prefilter_end
    ).all()

    # 3. Authoritative timezone evaluation per attempt
    qualifying_items: list[tuple[StudentAttempt, datetime]] = []
    candidate_pairs: set[tuple[int, str]] = set()

    for att in candidate_attempts:
        exam_tz = att.exam.timezone if att.exam else "Asia/Kolkata"
        local_dt = to_exam_local_datetime(att.submitted_at, exam_tz)
        if local_dt and local_dt.date() == target_date:
            qualifying_items.append((att, local_dt))
            candidate_pairs.add((att.exam_id, att.student_email))

    # 4. Handle day with zero qualifying attempts cleanly
    if not qualifying_items:
        return DailyExamSummaryReport(
            report_date=target_date,
            total_submissions=0,
            total_passed=0,
            total_failed=0,
            total_unevaluated=0,
            total_companies=0,
            named_companies_count=0,
            company_groups=[]
        )

    # 5. Batch-calculate attempt numbers (zero N+1)
    attempt_num_map = _batch_calculate_attempt_numbers(candidate_pairs)

    # 6. Preload company groups & aliases cache (zero N+1)
    company_cache = company_service.build_company_lookup_cache()

    # 7. Build item structures
    grouped_buckets: dict[str, list[DailySummaryAttemptItem]] = {}

    for att, local_dt in qualifying_items:
        exam = att.exam

        # Company resolution
        canonical_company = company_service.resolve_canonical_company(
            att.company_name,
            cache=company_cache
        )
        group_label = canonical_company if canonical_company else company_service.NO_COMPANY_LABEL

        # Attempt number
        att_num = attempt_num_map.get(att.id, 1)

        # Scoring logic reused from existing admin / email views
        score_val = att.total_marks_obtained if att.total_marks_obtained is not None else att.score
        max_marks_val = sum(q.marks for q in exam.questions) if exam and exam.questions else 0.0
        percentage_val = att.percentage_score

        # Result status terminology
        if att.result_status:
            res_status = att.result_status
        elif att.evaluation_status == "pending":
            res_status = "Under Evaluation"
        else:
            res_status = "N/A"

        item = DailySummaryAttemptItem(
            attempt_id=att.id,
            candidate_name=att.student_name,
            candidate_email=att.student_email,
            exam_id=exam.id if exam else 0,
            exam_title=exam.title if exam else "Exam",
            exam_code=exam.exam_code if exam else "",
            company_name=group_label,
            raw_company_name=att.company_name,
            attempt_number=att_num,
            submitted_at=local_dt,
            submitted_at_str=format_attempt_submission_time(local_dt),
            score=score_val,
            max_marks=max_marks_val,
            percentage=percentage_val,
            result_status=res_status,
            evaluation_status=att.evaluation_status
        )

        if group_label not in grouped_buckets:
            grouped_buckets[group_label] = []
        grouped_buckets[group_label].append(item)

    # 8. Deterministic Ordering
    # Company groups: alphabetical by name, with NO_COMPANY_LABEL placed at the end
    no_comp_label = company_service.NO_COMPANY_LABEL
    sorted_group_names = sorted(
        [name for name in grouped_buckets if name != no_comp_label],
        key=lambda s: s.lower()
    )
    if no_comp_label in grouped_buckets:
        sorted_group_names.append(no_comp_label)

    company_group_summaries: list[DailyCompanyGroupSummary] = []
    overall_total_passed = 0
    overall_total_failed = 0
    overall_total_unevaluated = 0

    for name in sorted_group_names:
        items = grouped_buckets[name]
        # Candidates within group: submitted_at asc, candidate_name asc, attempt_id asc
        items.sort(key=lambda it: (it.submitted_at, it.candidate_name.lower(), it.attempt_id))

        grp_passed = sum(1 for it in items if it.result_status == "Pass")
        grp_failed = sum(1 for it in items if it.result_status == "Fail")
        grp_unevaluated = sum(1 for it in items if it.result_status not in ("Pass", "Fail"))

        overall_total_passed += grp_passed
        overall_total_failed += grp_failed
        overall_total_unevaluated += grp_unevaluated

        company_group_summaries.append(
            DailyCompanyGroupSummary(
                company_name=name,
                total_submissions=len(items),
                total_passed=grp_passed,
                total_failed=grp_failed,
                total_unevaluated=grp_unevaluated,
                attempts=items
            )
        )

    named_count = sum(1 for g in company_group_summaries if g.company_name != no_comp_label)

    return DailyExamSummaryReport(
        report_date=target_date,
        total_submissions=len(qualifying_items),
        total_passed=overall_total_passed,
        total_failed=overall_total_failed,
        total_unevaluated=overall_total_unevaluated,
        total_companies=len(company_group_summaries),
        named_companies_count=named_count,
        company_groups=company_group_summaries
    )
