from app.extensions import db

class StudentAnswer(db.Model):
    __tablename__ = 'student_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('student_attempts.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey('question_options.id'), nullable=True)

    def __repr__(self):
        return f"<StudentAnswer attempt={self.attempt_id} question={self.question_id}>"
