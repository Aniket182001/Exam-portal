from app.extensions import db

class QuestionOption(db.Model):
    __tablename__ = 'question_options'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    option_text = db.Column(db.Text, nullable=False)
    option_order = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<QuestionOption {self.id}>"
