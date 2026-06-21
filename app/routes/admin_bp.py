from flask import Blueprint, render_template
from app.utils.auth import admin_required

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")

@admin_bp.before_request
@admin_required
def require_admin():
    pass

SYSTEM_TEMPLATES = {
    "exam_invitation": {
        "key": "exam_invitation",
        "name": "Exam Invitation",
        "category": "Access",
        "type": "System",
        "subject": "AIQM Examination Instructions – {exam_name}",
        "variables": ["candidate_name", "exam_name", "exam_code", "homepage_url", "duration", "question_count"],
        "body": """Dear {candidate_name}, 👋

Greetings from Asian Institute of Quality Management (AIQM)! You are now eligible to appear for the {exam_name} Online Examination. Please find the examination details and login instructions below. ✅
________________________________________
📄 Examination Details:
Mode: Online & Open-Book 🌐📘
Total Questions: {question_count} Multiple-Choice Questions (MCQs)
Marks Per Question: 1 Mark (No Negative Marking) 🟢
Passing Score: 50% 🎯
Duration: {duration} Minutes ⏰
Navigation: You can move between pages before submitting answers ↔️
📌 It is recommended to use a laptop instead of a mobile phone for better exam experience.
⚠️ In case of unstable Wi-Fi or power, please use a laptop with mobile hotspot for backup.
________________________________________
🔐 Instructions:
1️⃣ Visit: {homepage_url}
2️⃣ Enter Exam Code: {exam_code}
3️⃣ Enter your details.
4️⃣ Read instructions and start your examination.
________________________________________
🎓 We wish you all the best for your exam!
________________________________________
📞 For any technical assistance, feel free to reach out:
  • WhatsApp: +91-9320003505
  • Email: dskode@aiqmindia.com
________________________________________
Best Regards,"""
    },
    "result_email": {
        "key": "result_email",
        "name": "Result Email",
        "category": "Results",
        "type": "System",
        "subject": "Examination Results",
        "variables": ["candidate_name", "exam_name", "score", "status"],
        "body": "System controlled result email. Currently driven by application logic."
    },
    "lms_access": {
        "key": "lms_access",
        "name": "LMS Access",
        "category": "Access",
        "type": "System",
        "subject": "Welcome to AIQM’s E-Learning Platform – Your Course Access Details",
        "variables": ["candidate_name", "course_name", "login_email"],
        "body": """Dear {candidate_name},

Greetings from AIQM India! 🌏 Welcome to the UK-accredited {course_name} Course. We are delighted to have you on board and look forward to supporting you in your learning journey.
________________________________________
🔐 Your Login Credentials
🌐 E-Learning Portal: https://elearning.aiqmindia.com/home
👤 Username: {login_email}
🔑 Password: A!qm@123A
________________________________________
📘 How to Access Your Course?
1️⃣ Log in using your username and password at AIQM E-Learning Portal.
2️⃣ Gain 24x7 access to video sessions, which include faculty-led explanations, illustrations, and explainer modules.
3️⃣ Navigate through the course chapters in sequence, as per the provided study material.
4️⃣ If you have any doubts, feel free to email us your queries.
________________________________________
📞 Important Contact Information
For any further communication or support, please reach out to:
📧 Email: dskode@aiqmindia.com
📱 Phone/WhatsApp: +91-93200 03505"""
    },
    "certificate_email": {
        "key": "certificate_email",
        "name": "Certificate Email",
        "category": "Certification",
        "type": "System",
        "subject": "Your {course_name} Certificate is here",
        "variables": ["candidate_name", "course_name"],
        "body": """Dear {candidate_name},

Congratulations on successfully completing the {course_name} course. Please find your certificate of completion attached to this email. We appreciate your hard work and dedication throughout the program and hope that the skills you have acquired will be valuable in your professional journey.

Once again, congratulations on this achievement.

Best regards,"""
    },
    "welcome_email": {
        "key": "welcome_email",
        "name": "Welcome Email",
        "category": "Notification",
        "type": "System",
        "subject": "Welcome to AIQM",
        "variables": ["candidate_name"],
        "body": "Dear {candidate_name},\n\nWelcome to AIQM.\n\nBest regards,"
    }
}

@admin_bp.route("/email")
def email_center():
    templates = list(SYSTEM_TEMPLATES.values())
    return render_template("admin/email/list.html", templates=templates)

@admin_bp.route("/email/<template_key>")
def view_template(template_key):
    template = SYSTEM_TEMPLATES.get(template_key)
    if not template:
        return "Template not found", 404
    return render_template("admin/email/view.html", template=template)

from flask import request
from app.models import Exam

@admin_bp.route("/email/<template_key>/compose", methods=["GET", "POST"])
def compose_template(template_key):
    template = SYSTEM_TEMPLATES.get(template_key)
    if not template or template_key not in ['exam_invitation', 'lms_access', 'certificate_email']:
        return "Template not found or cannot be composed", 404

    if request.method == "POST":
        subject = template["subject"]
        body = template["body"]
        recipient_email = request.form.get("candidate_email", "") or request.form.get("login_email", "")

        if template_key == "exam_invitation":
            candidate_name = request.form.get("candidate_name", "")
            exam_id = request.form.get("exam_id")
            exam = Exam.query.get(exam_id)
            if exam:
                subject = subject.replace("{exam_name}", exam.title)
                body = body.replace("{candidate_name}", candidate_name)
                body = body.replace("{exam_name}", exam.title)
                body = body.replace("{exam_code}", exam.exam_code)
                body = body.replace("{duration}", str(exam.duration_minutes))
                body = body.replace("{question_count}", str(len(exam.questions)))
                body = body.replace("{homepage_url}", "https://exams.aiqmanalytics.com")
        
        elif template_key == "lms_access":
            candidate_name = request.form.get("candidate_name", "")
            login_email = request.form.get("login_email", "")
            course_name = request.form.get("course_name", "")
            subject = subject.replace("{course_name}", course_name)
            body = body.replace("{candidate_name}", candidate_name)
            body = body.replace("{course_name}", course_name)
            body = body.replace("{login_email}", login_email)
            
        elif template_key == "certificate_email":
            candidate_name = request.form.get("candidate_name", "")
            course_name = request.form.get("course_name", "")
            subject = subject.replace("{course_name}", course_name)
            body = body.replace("{candidate_name}", candidate_name)
            body = body.replace("{course_name}", course_name)
            
        return render_template("admin/email/compose_result.html", 
                               template=template, 
                               subject=subject, 
                               body=body, 
                               recipient_email=recipient_email)

    exams = Exam.query.filter_by(is_active=True).all() if template_key == "exam_invitation" else []
    courses = ["Lean Six Sigma Black Belt", "Lean Six Sigma Green Belt", "Total Quality Management"]
    
    return render_template("admin/email/compose_form.html", template=template, exams=exams, courses=courses)
