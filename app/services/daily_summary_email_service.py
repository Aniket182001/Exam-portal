"""
Daily Examination Summary Email Generation Service.

Pure presentation layer responsible for transforming a Phase 2 DailyExamSummaryReport
into a self-contained, responsive HTML email for AIQM administrators.
Strictly decoupled from SMTP, Brevo delivery, and database operations.
"""

import os
import jinja2
from datetime import date
from flask import current_app

from app.services.daily_summary_service import DailyExamSummaryReport


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def format_metric(val: float | int | None) -> str:
    """Formats a number without redundant decimal places (e.g. 20.0 -> '20', 22.5 -> '22.5')."""
    if val is None:
        return "-"
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else f"{f:.1f}"
    except (ValueError, TypeError):
        return str(val)


def format_score(score: float | None, max_marks: float | None) -> str:
    """Formats score as 'score / max_marks' (e.g. '20 / 25' or '42.5 / 50')."""
    if score is None:
        return "-"
    score_str = format_metric(score)
    if max_marks is not None and max_marks > 0:
        max_str = format_metric(max_marks)
        return f"{score_str} / {max_str}"
    return score_str


def format_percentage(pct: float | None) -> str:
    """Formats percentage as '84%' or '84.5%'. Returns '—' if None."""
    if pct is None:
        return "—"
    return f"{format_metric(pct)}%"


# ---------------------------------------------------------------------------
# Subject Helper
# ---------------------------------------------------------------------------

def get_daily_summary_email_subject(report: DailyExamSummaryReport) -> str:
    """
    Generates the standardized subject line for the daily summary email.
    Format: 'AIQM Daily Examination Summary — 09 Sep 2026'
    Strictly uses report.report_date, never the system clock.
    """
    date_str = report.report_date.strftime("%d %b %Y")
    return f"AIQM Daily Examination Summary — {date_str}"


# ---------------------------------------------------------------------------
# Template Loader & HTML Renderer
# ---------------------------------------------------------------------------

def _get_jinja_environment() -> jinja2.Environment:
    """
    Returns a configured Jinja Environment with HTML autoescaping.
    Works whether inside an active Flask application context or standalone.
    """
    if current_app:
        return current_app.jinja_env

    # Standalone fallback: locate templates/ directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(base_dir, "templates")
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )


def render_daily_summary_email(report: DailyExamSummaryReport) -> str:
    """
    Renders a self-contained, responsive HTML email string from a DailyExamSummaryReport.

    Key behaviors:
    - Pure presentation layer: executes 0 database queries.
    - Full HTML autoescaping for all dynamic fields (candidate name, company, exam, etc.).
    - Human-friendly date: '09 September 2026'.
    - Separate company sections for each DailyCompanyGroupSummary.
    - Clean empty state if report.total_submissions == 0.
    - Does NOT connect to Brevo or send real emails.
    """
    env = _get_jinja_environment()
    template = env.get_template("emails/daily_summary.html")

    report_date_display = report.report_date.strftime("%d %B %Y")
    subject = get_daily_summary_email_subject(report)

    return template.render(
        report=report,
        subject=subject,
        report_date_display=report_date_display,
        format_score=format_score,
        format_percentage=format_percentage,
    )
