from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import Exam, Question, QuestionOption

admin_questions_bp = Blueprint("admin_questions", __name__, url_prefix="/admin")

@admin_questions_bp.route("/exams/<int:exam_id>/questions")
def list_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.display_order.asc()).all()
    return render_template("admin/questions/list.html", exam=exam, questions=questions)

@admin_questions_bp.route("/exams/<int:exam_id>/questions/create", methods=["GET", "POST"])
def create_question(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if request.method == "POST":
        question_text = request.form.get("question_text")
        marks = float(request.form.get("marks", 1.0))
        
        option_texts = request.form.getlist("option_text[]")
        correct_index = request.form.get("correct_option_index")
        
        # Validation
        if not question_text or not question_text.strip():
            flash("Question text is required.", "danger")
            return render_template("admin/questions/form.html", action="Create", exam=exam)
            
        valid_options = [opt for opt in option_texts if opt.strip()]
        if len(valid_options) < 2 or len(valid_options) > 5:
            flash("A question must have between 2 and 5 valid options.", "danger")
            return render_template("admin/questions/form.html", action="Create", exam=exam)
            
        if correct_index is None or not correct_index.isdigit() or int(correct_index) >= len(option_texts):
            flash("Please select a valid correct answer.", "danger")
            return render_template("admin/questions/form.html", action="Create", exam=exam)
            
        correct_idx_int = int(correct_index)
        if not option_texts[correct_idx_int].strip():
            flash("The selected correct answer cannot be an empty option.", "danger")
            return render_template("admin/questions/form.html", action="Create", exam=exam)

        # Get max display order
        max_order_question = Question.query.filter_by(exam_id=exam.id).order_by(Question.display_order.desc()).first()
        next_display_order = (max_order_question.display_order + 1) if max_order_question else 1

        # Create question
        new_question = Question(
            exam_id=exam.id,
            question_text=question_text.strip(),
            marks=marks,
            display_order=next_display_order
        )
        db.session.add(new_question)
        db.session.flush() # get id
        
        # Create options
        created_options = []
        for i, opt_text in enumerate(option_texts):
            if opt_text.strip():
                opt = QuestionOption(
                    question_id=new_question.id,
                    option_text=opt_text.strip(),
                    option_order=i + 1
                )
                db.session.add(opt)
                created_options.append((i, opt))
                
        db.session.flush() # get option ids
        
        # Set correct option id
        for original_idx, opt in created_options:
            if original_idx == correct_idx_int:
                new_question.correct_option_id = opt.id
                break
                
        db.session.commit()
        flash("Question created successfully.", "success")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))

    return render_template("admin/questions/form.html", action="Create", exam=exam)

@admin_questions_bp.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    exam = question.exam
    
    if request.method == "POST":
        question_text = request.form.get("question_text")
        marks = float(request.form.get("marks", 1.0))
        
        option_texts = request.form.getlist("option_text[]")
        correct_index = request.form.get("correct_option_index")
        
        # Validation
        if not question_text or not question_text.strip():
            flash("Question text is required.", "danger")
            return render_template("admin/questions/form.html", action="Edit", exam=exam, question=question)
            
        valid_options = [opt for opt in option_texts if opt.strip()]
        if len(valid_options) < 2 or len(valid_options) > 5:
            flash("A question must have between 2 and 5 valid options.", "danger")
            return render_template("admin/questions/form.html", action="Edit", exam=exam, question=question)
            
        if correct_index is None or not correct_index.isdigit() or int(correct_index) >= len(option_texts):
            flash("Please select a valid correct answer.", "danger")
            return render_template("admin/questions/form.html", action="Edit", exam=exam, question=question)
            
        correct_idx_int = int(correct_index)
        if not option_texts[correct_idx_int].strip():
            flash("The selected correct answer cannot be an empty option.", "danger")
            return render_template("admin/questions/form.html", action="Edit", exam=exam, question=question)

        # Update question details
        question.question_text = question_text.strip()
        question.marks = marks
        
        # Delete existing options
        QuestionOption.query.filter_by(question_id=question.id).delete()
        
        # Reset correct option temporarily to avoid constraint issues if deleting
        question.correct_option_id = None
        db.session.flush()

        # Create new options
        created_options = []
        for i, opt_text in enumerate(option_texts):
            if opt_text.strip():
                opt = QuestionOption(
                    question_id=question.id,
                    option_text=opt_text.strip(),
                    option_order=i + 1
                )
                db.session.add(opt)
                created_options.append((i, opt))
                
        db.session.flush()
        
        # Set correct option id
        for original_idx, opt in created_options:
            if original_idx == correct_idx_int:
                question.correct_option_id = opt.id
                break

        db.session.commit()
        flash("Question updated successfully.", "success")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))

    return render_template("admin/questions/form.html", action="Edit", exam=exam, question=question)

@admin_questions_bp.route("/questions/<int:question_id>/delete", methods=["POST"])
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    exam_id = question.exam_id
    db.session.delete(question)
    db.session.commit()
    flash("Question deleted successfully.", "success")
    return redirect(url_for('admin_questions.list_questions', exam_id=exam_id))
