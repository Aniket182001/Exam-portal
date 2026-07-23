"""
Diagnostic Script for Identifying Potential Submission-Loss Affected Attempts.

Checks all submitted StudentAttempt records for missing StudentAnswer entries
on the final question of their exam order.
"""

from app import create_app
from app.extensions import db
from app.models import StudentAttempt, StudentAnswer, Question, Exam

app = create_app()

def run_diagnostics():
    with app.app_context():
        submitted_attempts = StudentAttempt.query.filter_by(status='submitted').all()
        
        print(f"Total Submitted Attempts in Database: {len(submitted_attempts)}\n")
        print("=" * 100)
        print(f"{'Attempt ID':<12} | {'Student Name':<20} | {'Exam Title':<25} | {'Submitted At':<20} | {'Last Q Missing'}")
        print("=" * 100)
        
        affected_attempts = []

        for attempt in submitted_attempts:
            exam = Exam.query.get(attempt.exam_id)
            exam_title = exam.title if exam else "Unknown Exam"
            
            # Determine last question ID for this specific attempt
            last_question_id = None
            if attempt.question_order and isinstance(attempt.question_order, list) and len(attempt.question_order) > 0:
                last_question_id = attempt.question_order[-1]
            else:
                last_q = Question.query.filter_by(exam_id=attempt.exam_id).order_by(
                    Question.display_order.desc(), Question.id.desc()
                ).first()
                if last_q:
                    last_question_id = last_q.id

            if not last_question_id:
                continue

            # Check if an answer exists for the last question
            last_ans = StudentAnswer.query.filter_by(
                attempt_id=attempt.id,
                question_id=last_question_id
            ).first()

            # An answer is missing if no row exists, or if both selected_option_id and answer_text are null/empty
            has_valid_answer = False
            if last_ans:
                if last_ans.selected_option_id is not None:
                    has_valid_answer = True
                elif last_ans.answer_text and last_ans.answer_text.strip():
                    has_valid_answer = True

            if not has_valid_answer:
                affected_attempts.append({
                    "attempt_id": attempt.id,
                    "student_name": attempt.student_name,
                    "student_email": attempt.student_email,
                    "exam_title": exam_title,
                    "submitted_at": str(attempt.submitted_at),
                    "last_question_id": last_question_id,
                    "unanswered_count": attempt.unanswered_count,
                    "score": attempt.score,
                    "percentage_score": attempt.percentage_score,
                })
                print(f"{attempt.id:<12} | {attempt.student_name:<20} | {exam_title[:25]:<25} | {str(attempt.submitted_at)[:19]:<20} | YES (Unanswered Count: {attempt.unanswered_count})")

        print("=" * 100)
        print(f"\nDiagnostic Summary:")
        print(f"Total Affected Attempts Found: {len(affected_attempts)}\n")

        if affected_attempts:
            print("Detailed Report of Flagged Attempts:")
            for item in affected_attempts:
                print(f"  - Attempt #{item['attempt_id']}: Student '{item['student_name']}' ({item['student_email']})")
                print(f"    Exam: {item['exam_title']} | Submitted: {item['submitted_at']}")
                print(f"    Recorded Unanswered Count: {item['unanswered_count']} | Score: {item['score']} ({item['percentage_score']}%)")
                print(f"    Missing Last Question ID: {item['last_question_id']}\n")

if __name__ == "__main__":
    run_diagnostics()
