from app.extensions import db

class StudentAnswer(db.Model):
    __tablename__ = 'student_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('student_attempts.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    # MCQ: foreign key to the chosen option
    selected_option_id = db.Column(db.Integer, db.ForeignKey('question_options.id'), nullable=True)
    # Subjective / Incident: raw text or JSON string entered by the student
    answer_text = db.Column(db.Text, nullable=True)

    # Relationships
    question = db.relationship('Question', backref=db.backref('student_answers', lazy=True))
    evaluation = db.relationship('Evaluation', backref='student_answer', lazy=True,
                                 uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<StudentAnswer attempt={self.attempt_id} question={self.question_id}>"
