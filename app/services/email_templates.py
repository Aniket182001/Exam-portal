from zoneinfo import ZoneInfo
from datetime import timezone

def generate_result_email(attempt, total_marks):
    """
    Generates the subject and body for the Result Confirmation email.
    """
    def format_mark(val):
        if val is None:
            return "-"
        try:
            val_float = float(val)
            if val_float.is_integer():
                return int(val_float)
            return val_float
        except (ValueError, TypeError):
            return val

    certificate_name = attempt.student_name

    subject = "Congratulations! Your Certification Exam Results – Confirmation Required"

    formatted_total = format_mark(total_marks)
    formatted_obtained = format_mark(attempt.total_marks_obtained)

    body = f"""Dear Candidate,

Greetings from AIQM India! ✨

We are delighted to inform you that you have successfully completed your examination for the {attempt.exam.title}. Congratulations on your achievement! 🎉

━━━━━━━━━━━━━━━━━━━━━━
📊 Program Details
━━━━━━━━━━━━━━━━━━━━━━

• Program Name: {attempt.exam.title}

• Total Marks: {formatted_total}

• Marks Obtained: {formatted_obtained} 🏆

• Submitted At: {attempt.submitted_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(attempt.exam.timezone)).strftime('%B %d, %Y %I:%M %p %Z') if attempt.submitted_at else "N/A"} ⏱️

━━━━━━━━━━━━━━━━━━━━━━
📝 Certificate Name Confirmation
━━━━━━━━━━━━━━━━━━━━━━

Your name will appear on the certificate as:

👉 {certificate_name}

⚠️ Please verify the spelling carefully and confirm.

If any correction is required, kindly REPLY TO ALL within 2 days so we can proceed with certificate issuance.

━━━━━━━━━━━━━━━━━━━━━━
✅ Next Steps
━━━━━━━━━━━━━━━━━━━━━━

1. Your certificate will be issued once we receive your confirmation.

2. You will receive a soft copy via email, and if applicable, a hard copy will be dispatched as per the standard process.

3. Stay connected with us for updates on advanced courses and career-enhancing certifications. 🚀

━━━━━━━━━━━━━━━━━━━━━━
📞 Need Assistance?
━━━━━━━━━━━━━━━━━━━━━━

WhatsApp/Call: +91-9320003505

Email: dskode@aiqmindia.com

We truly appreciate your dedication and commitment to learning.

Wishing you continued success in your professional journey! 🌟"""

    return {
        "subject": subject,
        "body": body
    }
