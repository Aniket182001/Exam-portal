"""
Email Service for AIQM Exam Portal.

Handles SMTP delivery (configured for Brevo SMTP) and administrative notifications
upon candidate exam submission. Designed to be completely fail-safe, asynchronous,
and decoupled from candidate transaction flows.
"""

import os
import smtplib
import threading
import logging
from email.message import EmailMessage
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import current_app

logger = logging.getLogger(__name__)

# In-memory thread-safe cache for duplicate prevention
_notified_attempt_ids = set()
_notified_lock = threading.Lock()


DEFAULT_NOTIFICATION_RECIPIENTS = (
    "aniket@aiqmindia.com,dskode@aiqmindia.com,edu@aiqmindia.com,ravi.k@aiqmindia.com"
)


def get_mail_config():
    """
    Retrieves email configuration from Flask current_app if inside app context,
    or falls back to environment variables.
    """
    if current_app:
        cfg = current_app.config
        return {
            "server": cfg.get("MAIL_SERVER", "smtp-relay.brevo.com"),
            "port": int(cfg.get("MAIL_PORT", 587)),
            "use_tls": bool(cfg.get("MAIL_USE_TLS", True)),
            "use_ssl": bool(cfg.get("MAIL_USE_SSL", False)),
            "username": cfg.get("MAIL_USERNAME"),
            "password": cfg.get("MAIL_PASSWORD"),  # Brevo SMTP key
            "sender": cfg.get("MAIL_DEFAULT_SENDER", "aniket@aiqmindia.com"),
            "recipients_raw": cfg.get("EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS", DEFAULT_NOTIFICATION_RECIPIENTS),
        }
    return {
        "server": os.getenv("MAIL_SERVER", "smtp-relay.brevo.com"),
        "port": int(os.getenv("MAIL_PORT", 587)),
        "use_tls": os.getenv("MAIL_USE_TLS", "true").lower() in ["true", "1", "yes"],
        "use_ssl": os.getenv("MAIL_USE_SSL", "false").lower() in ["true", "1", "yes"],
        "username": os.getenv("MAIL_USERNAME"),
        "password": os.getenv("MAIL_PASSWORD"),
        "sender": os.getenv("MAIL_DEFAULT_SENDER", "aniket@aiqmindia.com"),
        "recipients_raw": os.getenv("EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS", DEFAULT_NOTIFICATION_RECIPIENTS),
    }


def parse_recipients(recipients_raw):
    """
    Splits a comma-separated or list of recipient emails, stripping whitespace.
    Returns a clean list of email strings.
    """
    if not recipients_raw:
        return []
    if isinstance(recipients_raw, list):
        items = recipients_raw
    else:
        items = str(recipients_raw).split(",")

    valid_recipients = []
    for item in items:
        clean = item.strip()
        if clean and "@" in clean:
            valid_recipients.append(clean)
    return valid_recipients


def send_smtp_email(to_addresses, subject, text_body, html_body=None, sender=None, config=None):
    """
    Direct SMTP transmission via smtplib (supporting Brevo SMTP).
    Returns True on success, False on failure.
    Logs clear diagnostic messages without raising exceptions.
    """
    cfg = config or get_mail_config()
    server_host = cfg["server"]
    server_port = cfg["port"]
    username = cfg["username"]
    password = cfg["password"]
    from_sender = sender or cfg["sender"] or "aniket@aiqmindia.com"

    recipients = parse_recipients(to_addresses)
    if not recipients:
        logger.warning("SMTP abort: No valid recipients provided.")
        return False

    if not username or not password:
        logger.warning(
            "SMTP abort: MAIL_USERNAME or MAIL_PASSWORD (Brevo SMTP key) not configured. "
            "Email notification skipped."
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if cfg["use_ssl"] or server_port == 465:
            logger.info(f"Connecting to SMTP server {server_host}:{server_port} via SSL...")
            with smtplib.SMTP_SSL(server_host, server_port, timeout=20) as server:
                server.login(username, password)
                server.send_message(msg)
        else:
            logger.info(f"Connecting to SMTP server {server_host}:{server_port}...")
            with smtplib.SMTP(server_host, server_port, timeout=20) as server:
                if cfg["use_tls"]:
                    server.starttls()
                server.login(username, password)
                server.send_message(msg)

        logger.info(f"Successfully delivered email '{subject}' to {recipients} via Brevo SMTP.")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(
            f"Brevo SMTP Authentication Error: Check MAIL_USERNAME and MAIL_PASSWORD (SMTP Key). Error: {e}"
        )
        return False
    except smtplib.SMTPException as e:
        logger.error(f"Brevo SMTP Exception while sending email to {recipients}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error while sending email via SMTP to {recipients}: {e}", exc_info=True)
        return False


def _format_metric_number(val):
    if val is None:
        return "-"
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else f"{f:.1f}"
    except (ValueError, TypeError):
        return str(val)


def build_submission_notification_content(attempt_data):
    """
    Builds subject, plain text body, and responsive HTML body for the admin alert.
    Includes already-calculated candidate result information for internal admin review.
    """
    candidate_name = attempt_data.get("candidate_name", "N/A")
    candidate_email = attempt_data.get("candidate_email", "N/A")
    exam_title = attempt_data.get("exam_title", "N/A")
    exam_code = attempt_data.get("exam_code", "N/A")
    submission_time = attempt_data.get("submission_time", "N/A")
    attempt_number = attempt_data.get("attempt_number", 1)
    submission_type = attempt_data.get("submission_type", "Manual Submission")

    # Read already-calculated result fields
    score = attempt_data.get("score")
    max_marks = attempt_data.get("max_marks")
    percentage = attempt_data.get("percentage")
    result_status = attempt_data.get("result_status")
    evaluation_status = attempt_data.get("evaluation_status")

    if score is not None and max_marks is not None and max_marks > 0:
        score_display = f"{_format_metric_number(score)} / {_format_metric_number(max_marks)}"
    elif score is not None:
        score_display = _format_metric_number(score)
    else:
        score_display = "-"

    if percentage is not None:
        percentage_display = f"{_format_metric_number(percentage)}%"
    else:
        percentage_display = "-"

    if result_status:
        res_clean = str(result_status).strip().lower()
        if res_clean == "pass":
            result_display = "PASSED"
            result_color = "#16a34a"
        elif res_clean == "fail":
            result_display = "FAILED"
            result_color = "#dc2626"
        else:
            result_display = str(result_status).upper()
            result_color = "#0f172a"
    elif evaluation_status == "pending":
        result_display = "Awaiting Evaluation"
        result_color = "#d97706"
    else:
        result_display = "N/A"
        result_color = "#64748b"

    subject = f"[AIQM Alert] New Exam Submission: {candidate_name} – {exam_code}"

    text_body = f"""AIQM Examination Portal — Admin Notification

A candidate has submitted an examination session.

Candidate Details:
• Name: {candidate_name}
• Email: {candidate_email}

Examination Details:
• Exam Title: {exam_title}
• Exam Code: {exam_code}
• Submission Time: {submission_time}
• Attempt Number: Attempt #{attempt_number}
• Submission Method: {submission_type}

Result Summary:
• Score: {score_display}
• Percentage: {percentage_display}
• Result: {result_display}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Notice: This is an automated internal notification for AIQM Administrators.
Results and candidate evaluation can be viewed in the Admin Panel.
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 24px; color: #1e293b; }}
  .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
  .header {{ background: #0f172a; padding: 24px; color: #ffffff; }}
  .header h2 {{ margin: 0 0 4px 0; font-size: 20px; font-weight: 700; }}
  .header p {{ margin: 0; font-size: 13px; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase; }}
  .badge {{ display: inline-block; background: #f97316; color: #ffffff; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; margin-top: 8px; }}
  .content {{ padding: 24px; }}
  .section-title {{ font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }}
  .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  .info-table td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
  .info-table td.label {{ color: #64748b; width: 38%; font-weight: 500; }}
  .info-table td.value {{ color: #0f172a; font-weight: 600; }}
  .footer {{ background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <p>Asian Institute of Quality Management</p>
    <h2>New Exam Submission</h2>
    <span class="badge">{submission_type}</span>
  </div>
  <div class="content">
    <div class="section-title">Candidate Details</div>
    <table class="info-table">
      <tr>
        <td class="label">Candidate Name</td>
        <td class="value">{candidate_name}</td>
      </tr>
      <tr>
        <td class="label">Candidate Email</td>
        <td class="value"><a href="mailto:{candidate_email}" style="color: #f97316; text-decoration: none;">{candidate_email}</a></td>
      </tr>
    </table>

    <div class="section-title">Examination Details</div>
    <table class="info-table">
      <tr>
        <td class="label">Examination</td>
        <td class="value">{exam_title}</td>
      </tr>
      <tr>
        <td class="label">Exam Code</td>
        <td class="value" style="font-family: monospace; font-size: 14px;">{exam_code}</td>
      </tr>
      <tr>
        <td class="label">Submission Time</td>
        <td class="value">{submission_time}</td>
      </tr>
      <tr>
        <td class="label">Attempt Number</td>
        <td class="value">Attempt #{attempt_number}</td>
      </tr>
    </table>

    <div class="section-title">Result Summary</div>
    <table class="info-table">
      <tr>
        <td class="label">Score</td>
        <td class="value">{score_display}</td>
      </tr>
      <tr>
        <td class="label">Percentage</td>
        <td class="value">{percentage_display}</td>
      </tr>
      <tr>
        <td class="label">Result</td>
        <td class="value"><span style="color: {result_color}; font-weight: 700;">{result_display}</span></td>
      </tr>
    </table>
  </div>
  <div class="footer">
    This is an automated administrative notification. Results are securely preserved in the AIQM Exam Portal.
  </div>
</div>
</body>
</html>"""

    return subject, text_body, html_body


def _async_send_submission_notification(attempt_data, config):
    """
    Worker function executed in detached background thread.
    Catches all errors internally.
    """
    try:
        recipients = parse_recipients(config.get("recipients_raw"))
        if not recipients:
            logger.info(
                "Admin submission notification skipped: EXAM_SUBMISSION_NOTIFICATION_RECIPIENTS is not configured."
            )
            return

        subject, text_body, html_body = build_submission_notification_content(attempt_data)
        send_smtp_email(
            to_addresses=recipients,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            sender=config.get("sender"),
            config=config,
        )
    except Exception as e:
        logger.error(f"Error in async submission notification thread: {e}", exc_info=True)


def trigger_submission_notification(attempt, submission_type="Manual Submission"):
    """
    Triggers the admin submission notification in a detached background thread.
    Must be called AFTER db.session.commit() has succeeded.
    Guarantees:
      1. Duplicate prevention: Checks and records attempt.id in thread-safe memory cache.
      2. Thread isolation: Only primitive data types are passed to the thread.
      3. Non-blocking: Candidate redirect is instantaneous.
      4. 100% fail-safe: Never raises an exception to the caller.
    """
    try:
        if not attempt or not attempt.id:
            return

        # 1. Duplicate prevention check
        with _notified_lock:
            if attempt.id in _notified_attempt_ids:
                logger.info(
                    f"Submission notification already dispatched for Attempt #{attempt.id}. Skipping duplicate."
                )
                return
            _notified_attempt_ids.add(attempt.id)
            # Bound cache size to prevent memory growth
            if len(_notified_attempt_ids) > 10000:
                _notified_attempt_ids.clear()
                _notified_attempt_ids.add(attempt.id)

        # 2. Extract primitive data safely inside current request/DB context
        exam = attempt.exam
        exam_tz_name = (exam.timezone if exam and exam.timezone else "Asia/Kolkata").strip()
        try:
            target_tz = ZoneInfo(exam_tz_name)
        except Exception:
            target_tz = ZoneInfo("Asia/Kolkata")

        sub_dt = attempt.submitted_at or datetime.now(timezone.utc)
        if sub_dt.tzinfo is None:
            sub_dt = sub_dt.replace(tzinfo=timezone.utc)
        formatted_time = sub_dt.astimezone(target_tz).strftime("%d-%b-%Y %I:%M %p %Z")

        # Compute candidate's attempt number for this exam
        from app.models import StudentAttempt

        prior_attempts_count = StudentAttempt.query.filter_by(
            exam_id=attempt.exam_id,
            student_email=attempt.student_email
        ).count()
        attempt_number = max(1, prior_attempts_count)

        # Read already-calculated result values directly from attempt
        score_val = attempt.total_marks_obtained if attempt.total_marks_obtained is not None else attempt.score
        max_marks_val = sum(q.marks for q in exam.questions) if exam and exam.questions else 0

        attempt_data = {
            "attempt_id": attempt.id,
            "candidate_name": attempt.student_name,
            "candidate_email": attempt.student_email,
            "exam_title": exam.title if exam else "Exam",
            "exam_code": exam.exam_code if exam else "",
            "submission_time": formatted_time,
            "attempt_number": attempt_number,
            "submission_type": submission_type,
            "score": score_val,
            "max_marks": max_marks_val,
            "percentage": attempt.percentage_score,
            "result_status": attempt.result_status,
            "evaluation_status": attempt.evaluation_status,
        }

        mail_config = get_mail_config()

        # 3. Spawn background thread
        thread = threading.Thread(
            target=_async_send_submission_notification,
            args=(attempt_data, mail_config),
            daemon=True,
            name=f"AdminEmail-Attempt-{attempt.id}",
        )
        thread.start()
        logger.info(
            f"Spawned background email notification thread for Attempt #{attempt.id} ({attempt.student_email})."
        )
    except Exception as e:
        # Never fail caller
        logger.error(f"Failed to trigger submission notification for attempt: {e}", exc_info=True)
