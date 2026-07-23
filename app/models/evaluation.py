from app.extensions import db
from datetime import datetime, timezone


class Evaluation(db.Model):
    """Stores manual evaluator feedback and marks for a single StudentAnswer.

    One StudentAnswer may have at most one Evaluation record (1-to-1 via
    student_answer.evaluation backref defined on StudentAnswer).
    """
    __tablename__ = 'evaluations'

    id = db.Column(db.Integer, primary_key=True)

    # The specific student answer being evaluated
    student_answer_id = db.Column(
        db.Integer,
        db.ForeignKey('student_answers.id'),
        nullable=False,
        unique=True,   # enforces 1-to-1 at DB level
    )

    # The admin/evaluator who performed the grading
    evaluator_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
    )

    # Total marks awarded (null = not yet graded)
    marks_awarded = db.Column(db.Float, nullable=True)

    # Per-component breakdown for incident-type questions, e.g.
    # {"identification": 2, "root_cause": 3, "corrective_action": 4}
    marks_breakdown = db.Column(db.JSON, nullable=True)

    # Evaluator notes / feedback visible to student (future feature)
    comment = db.Column(db.Text, nullable=True)

    # 'pending' = awaiting evaluation; 'evaluated' = marks_awarded set
    status = db.Column(
        db.String(20),
        nullable=False,
        server_default='pending',
        default='pending',
    )

    evaluated_at = db.Column(db.DateTime, nullable=True)

    # Relationship back to the evaluator user
    evaluator = db.relationship('User', backref='evaluations', lazy=True)

    def __repr__(self):
        return (
            f"<Evaluation id={self.id} answer={self.student_answer_id} "
            f"status={self.status}>"
        )
