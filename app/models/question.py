from app.extensions import db

class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    marks = db.Column(db.Float, default=1.0, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    correct_option_id = db.Column(db.Integer, nullable=True) # nullable initially to avoid circular dependency

    # Phase 1: Subjective / Incident question support
    # 'mcq' | 'subjective' | 'incident'
    question_type = db.Column(db.String(20), nullable=False, server_default='mcq', default='mcq')
    # Used only when question_type == 'incident': defines the structured response schema
    response_schema = db.Column(db.JSON, nullable=True)
    # Free-text rubric visible to evaluators during manual grading
    rubric_text = db.Column(db.Text, nullable=True)

    # Relationships
    options = db.relationship('QuestionOption', backref='question', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Question {self.id} for Exam {self.exam_id}>"
