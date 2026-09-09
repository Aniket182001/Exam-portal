"""
Daily Examination Summary Email Delivery Service.

Responsible for sending a DailyExamSummaryReport as an HTML email using the project's
existing Brevo SMTP email infrastructure (send_smtp_email from app.services.email_service).
"""

import logging
from dataclasses import dataclass
from datetime import date
from flask import current_app

from config import Config
from app.services.daily_summary_service import DailyExamSummaryReport
from app.services.daily_summary_email_service import (
    render_daily_summary_email,
    get_daily_summary_email_subject,
)
from app.services.email_service import send_smtp_email, parse_recipients

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result Data Structure
# ---------------------------------------------------------------------------

@dataclass
class DailySummaryDeliveryResult:
    success: bool
    status: str             # "sent", "skipped_empty", "failed", "no_recipients"
    message: str            # Human-readable status description
    report_date: date
    recipient_count: int
    recipients: list[str]
    subject: str | None = None


# ---------------------------------------------------------------------------
# Recipient Resolution
# ---------------------------------------------------------------------------

def get_daily_summary_recipients() -> list[str]:
    """
    Resolves the configured recipient email addresses for the Daily Examination Summary.
    Priority:
    1. current_app.config['DAILY_SUMMARY_RECIPIENTS'] if running in Flask app context
    2. Config.DAILY_SUMMARY_RECIPIENTS
    Parsed using parse_recipients() to ensure valid email strings.
    """
    if current_app:
        raw = current_app.config.get("DAILY_SUMMARY_RECIPIENTS", Config.DAILY_SUMMARY_RECIPIENTS)
    else:
        raw = Config.DAILY_SUMMARY_RECIPIENTS

    return parse_recipients(raw)


# ---------------------------------------------------------------------------
# Plain-Text Fallback Generator
# ---------------------------------------------------------------------------

def build_daily_summary_text_fallback(report: DailyExamSummaryReport) -> str:
    """
    Builds a clean plain-text fallback representation of the Daily Examination Summary.
    Ensures email readability on clients that do not render HTML.
    """
    date_str = report.report_date.strftime("%d %B %Y")
    lines = [
        "Asian Institute of Quality Management (AIQM)",
        "Daily Examination Summary",
        f"Date: {date_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "OVERALL SUMMARY",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• Total Submissions : {report.total_submissions}",
        f"• Passed            : {report.total_passed}",
        f"• Failed            : {report.total_failed}",
        f"• Under Evaluation  : {report.total_unevaluated}",
        f"• Companies         : {report.total_companies}",
        "",
    ]

    if report.total_submissions == 0:
        lines.append("No examinations were submitted on this date.")
        lines.append("")
    else:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("COMPANY-WISE SUBMISSIONS")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for group in report.company_groups:
            lines.append("")
            lines.append(f"[{group.company_name}]")
            lines.append(
                f"Submissions: {group.total_submissions} | "
                f"Passed: {group.total_passed} | "
                f"Failed: {group.total_failed}"
                + (f" | Under Eval: {group.total_unevaluated}" if group.total_unevaluated > 0 else "")
            )
            for it in group.attempts:
                score_str = f"{it.score} / {it.max_marks}" if it.max_marks else str(it.score)
                pct_str = f"{it.percentage}%" if it.percentage is not None else "—"
                lines.append(
                    f"  • {it.candidate_name} | {it.exam_title} | Attempt #{it.attempt_number} | "
                    f"Score: {score_str} ({pct_str}) | Result: {it.result_status} | {it.submitted_at_str}"
                )
        lines.append("")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Notice: This is an automated internal report for AIQM Administrators.",
        "Secure Examination & Evaluation Management — AIQM Exam Portal",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email Delivery Function
# ---------------------------------------------------------------------------

def send_daily_exam_summary_email(
    report: DailyExamSummaryReport,
    recipients: list[str] | str | None = None,
    skip_if_empty: bool = True
) -> DailySummaryDeliveryResult:
    """
    Sends a DailyExamSummaryReport as an HTML email using the existing Brevo SMTP relay.

    Arguments:
    - report: DailyExamSummaryReport instance from Phase 2.
    - recipients: Optional explicit recipient(s). If None, uses get_daily_summary_recipients().
    - skip_if_empty: If True (default), suppresses email transmission when total_submissions == 0.

    Returns:
    - DailySummaryDeliveryResult with delivery status and diagnostic details.
    """
    # 1. Handle empty daily report suppression
    if report.total_submissions == 0 and skip_if_empty:
        logger.info(
            "Daily summary for %s has 0 submissions and skip_if_empty is True. Skipping email delivery.",
            report.report_date
        )
        return DailySummaryDeliveryResult(
            success=True,
            status="skipped_empty",
            message=f"No submitted examinations on {report.report_date}. Email delivery skipped.",
            report_date=report.report_date,
            recipient_count=0,
            recipients=[],
            subject=None
        )

    # 2. Resolve recipients
    if recipients is not None:
        target_recipients = parse_recipients(recipients)
    else:
        target_recipients = get_daily_summary_recipients()

    if not target_recipients:
        logger.warning(
            "Cannot send daily examination summary for %s: No valid recipients configured.",
            report.report_date
        )
        return DailySummaryDeliveryResult(
            success=False,
            status="no_recipients",
            message="No valid recipients configured for daily examination summary.",
            report_date=report.report_date,
            recipient_count=0,
            recipients=[],
            subject=None
        )

    # 3. Generate subject, HTML body, and plain-text fallback
    subject = get_daily_summary_email_subject(report)
    html_body = render_daily_summary_email(report)
    text_body = build_daily_summary_text_fallback(report)

    # 4. Transmit via existing SMTP infrastructure
    try:
        sent = send_smtp_email(
            to_addresses=target_recipients,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

        if sent:
            logger.info(
                "Daily examination summary for %s delivered successfully to %s.",
                report.report_date, target_recipients
            )
            return DailySummaryDeliveryResult(
                success=True,
                status="sent",
                message="Daily examination summary email delivered successfully.",
                report_date=report.report_date,
                recipient_count=len(target_recipients),
                recipients=target_recipients,
                subject=subject
            )
        else:
            logger.error(
                "Failed to deliver daily examination summary for %s via Brevo SMTP.",
                report.report_date
            )
            return DailySummaryDeliveryResult(
                success=False,
                status="failed",
                message="Brevo SMTP transmission failed. Check server logs for details.",
                report_date=report.report_date,
                recipient_count=len(target_recipients),
                recipients=target_recipients,
                subject=subject
            )
    except Exception as e:
        logger.error(
            "Unexpected error while sending daily examination summary for %s: %s",
            report.report_date, e, exc_info=True
        )
        return DailySummaryDeliveryResult(
            success=False,
            status="failed",
            message=f"Delivery failed due to unexpected error: {e}",
            report_date=report.report_date,
            recipient_count=len(target_recipients),
            recipients=target_recipients,
            subject=subject
        )
