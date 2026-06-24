from app.extensions import db
from datetime import datetime, timezone

class Exam(db.Model):
    __tablename__ = 'exams'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    exam_code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False)

    # Passing criteria
    passing_type = db.Column(db.String(20), nullable=False) # 'percentage' or 'marks'
    passing_value = db.Column(db.Float, nullable=False)

    # Negative marking
    negative_marking_enabled = db.Column(db.Boolean, default=False, nullable=False)
    negative_marks = db.Column(db.Float, default=0.0, nullable=False)

    # Exam window
    restrict_to_time_window = db.Column(db.Boolean, server_default='0', default=False, nullable=False)
    start_datetime = db.Column(db.DateTime, nullable=True)
    end_datetime = db.Column(db.DateTime, nullable=True)
    timezone = db.Column(db.String(50), server_default="Asia/Kolkata", default="Asia/Kolkata", nullable=False)

    # Result settings
    show_result_immediately = db.Column(db.Boolean, default=False, nullable=False)

    # Behavior Settings
    instructions = db.Column(db.Text, nullable=True)
    show_question_numbers = db.Column(db.Boolean, server_default='1', default=True, nullable=False)
    allow_question_navigation = db.Column(db.Boolean, server_default='1', default=True, nullable=False)
    show_progress_bar = db.Column(db.Boolean, server_default='1', default=True, nullable=False)
    auto_submit_on_timeout = db.Column(db.Boolean, server_default='1', default=True, nullable=False)
    shuffle_questions = db.Column(db.Boolean, server_default='0', default=False, nullable=False)

    # Candidate Registration
    require_candidate_registration = db.Column(db.Boolean, server_default='0', default=False, nullable=False)

    # Retest Logic
    allow_retest_on_failure = db.Column(db.Boolean, server_default='1', default=True, nullable=False)
    max_attempts = db.Column(db.Integer, server_default='2', default=2, nullable=False)

    # General
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    questions = db.relationship('Question', backref='exam', lazy=True, cascade="all, delete-orphan")
    attempts = db.relationship('StudentAttempt', backref='exam', lazy=True, cascade="all, delete-orphan")
    candidates = db.relationship('CandidateRegistration', backref='exam', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Exam {self.exam_code}>"
