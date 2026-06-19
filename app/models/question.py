from app.extensions import db

class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    marks = db.Column(db.Float, default=1.0, nullable=False)
    correct_option_id = db.Column(db.Integer, nullable=True) # nullable initially to avoid circular dependency

    # Relationships
    options = db.relationship('QuestionOption', backref='question', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Question {self.id} for Exam {self.exam_id}>"
