from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint

class CandidateRegistration(db.Model):
    __tablename__ = 'candidate_registrations'

    id = db.Column(db.Integer, primary_key=True)
    candidate_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('email', 'exam_id', name='uix_candidate_email_exam'),
    )

    def __repr__(self):
        return f"<CandidateRegistration {self.email} for Exam {self.exam_id}>"
