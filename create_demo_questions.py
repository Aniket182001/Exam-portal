import json
from app import create_app
from app.extensions import db
from app.models.exam import Exam
from app.models.question import Question
from app.models.question_option import QuestionOption

app = create_app()

with app.app_context():
    exam = Exam.query.filter_by(exam_code='test').first()
    if not exam:
        print("Exam 'test' not found!")
    else:
        # Check if already created
        if len(exam.questions) > 5:
            print("Questions already exist. Deleting existing to start fresh, or just appending.")
            # Let's just append or if they exist, leave them.
            
        print("Creating MCQ...")
        q_mcq = Question(
            exam_id=exam.id,
            question_text="What is the capital of France?",
            question_type="mcq",
            marks=5
        )
        db.session.add(q_mcq)
        db.session.flush()
        
        opt1 = QuestionOption(question_id=q_mcq.id, option_text="London", option_order=1)
        opt2 = QuestionOption(question_id=q_mcq.id, option_text="Berlin", option_order=2)
        opt3 = QuestionOption(question_id=q_mcq.id, option_text="Paris", option_order=3)
        opt4 = QuestionOption(question_id=q_mcq.id, option_text="Madrid", option_order=4)
        db.session.add_all([opt1, opt2, opt3, opt4])
        db.session.flush()
        
        q_mcq.correct_option_id = opt3.id
        db.session.add(q_mcq)
        
        print("Creating Subjective...")
        q_subj = Question(
            exam_id=exam.id,
            question_text="Describe the significance of the Eiffel Tower in French culture.",
            question_type="subjective",
            marks=10,
            rubric_text="Award 5 marks for historical context, 5 marks for modern cultural impact."
        )
        db.session.add(q_subj)
        
        print("Creating Incident...")
        schema = [
            {"label": "Incident Type", "max_marks": 2},
            {"label": "Root Cause", "max_marks": 5},
            {"label": "Corrective Action", "max_marks": 8}
        ]
        q_inc = Question(
            exam_id=exam.id,
            question_text="Review the following incident report and extract the key details.\n\n'On July 14th, the server crashed due to an out-of-memory error caused by a memory leak in the reporting module. The team restarted the server and patched the module the next day.'",
            question_type="incident",
            marks=15,
            response_schema=json.dumps(schema),
            rubric_text="Check if Root Cause identifies OOM/memory leak, Corrective Action mentions patching the module."
        )
        db.session.add(q_inc)
        
        db.session.commit()
        print("Demo questions added successfully!")
