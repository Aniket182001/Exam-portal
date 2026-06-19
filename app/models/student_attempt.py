from app.extensions import db
from datetime import datetime, timezone

class StudentAttempt(db.Model):
    __tablename__ = 'student_attempts'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)

    # Student details
    student_name = db.Column(db.String(100), nullable=False)
    student_email = db.Column(db.String(120), nullable=False)

    # Recovery
    attempt_token = db.Column(db.String(100), unique=True, nullable=False)

    # Timing
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at = db.Column(db.DateTime, nullable=True)

    # Results
    score = db.Column(db.Float, default=0.0, nullable=False)

    # Status: in_progress, submitted, expired
    status = db.Column(db.String(20), default="in_progress", nullable=False)

    # Relationships
    answers = db.relationship('StudentAnswer', backref='attempt', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<StudentAttempt {self.attempt_token}>"
