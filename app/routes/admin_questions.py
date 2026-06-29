from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from app.extensions import db
from app.models import Exam, Question, QuestionOption
import os
import json
import uuid
import io
import openpyxl
from werkzeug.utils import secure_filename
from app.services.import_parsers import get_parser
# New modular import engine (runs in parallel; does not replace existing flow yet)
from app.services.import_engine import ImportEngine
from app.utils.auth import admin_required

admin_questions_bp = Blueprint("admin_questions", __name__, url_prefix="/admin")

@admin_questions_bp.before_request
@admin_required
def require_admin():
    pass

@admin_questions_bp.route("/exams/<int:exam_id>/questions")
def list_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.display_order.asc()).all()
    return render_template("admin/questions/list.html", exam=exam, questions=questions)

@admin_questions_bp.route("/exams/<int:exam_id>/questions/export")
def export_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.display_order.asc()).all()
    
    if not questions:
        flash("This exam has no questions to export.", "warning")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
        
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Questions"
        
        headers = [
            "Question", "Option 1", "Option 2", "Option 3", 
            "Option 4", "Option 5", "Option 6", "Correct Answer", "Marks"
        ]
        ws.append(headers)
        
        from openpyxl.styles import Font
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=1, column=col_idx).font = Font(bold=True)
            
        for q in questions:
            row_data = [q.question_text]
            
            opts = sorted(q.options, key=lambda x: x.option_order)
            correct_letter = ""
            
            # Append options 1 to 6
            for i in range(6):
                if i < len(opts):
                    row_data.append(opts[i].option_text)
                    if opts[i].id == q.correct_option_id:
                        correct_letter = chr(ord('A') + i)
                else:
                    row_data.append("")
                    
            row_data.append(correct_letter)
            row_data.append(q.marks)
            
            ws.append(row_data)
            
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        filename = f"{exam.title}.xlsx"
        # Sanitize filename
        filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()
        filename = filename + ".xlsx" if not filename.endswith(".xlsx") else filename
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        import logging
        logging.error(f"Failed to export questions for exam {exam_id}: {e}")
        flash("Failed to generate export file. Please check server logs.", "danger")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))

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
        if len(valid_options) < 2 or len(valid_options) > 6:
            flash("A question must have between 2 and 6 valid options.", "danger")
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
        if len(valid_options) < 2 or len(valid_options) > 6:
            flash("A question must have between 2 and 6 valid options.", "danger")
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

@admin_questions_bp.route("/exams/<int:exam_id>/questions/delete_selected", methods=["POST"])
def delete_selected_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    question_ids = request.form.getlist("question_ids")
    
    if not question_ids:
        flash("Please select at least one question to delete.", "warning")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
        
    try:
        # Cascade delete is typically handled by SQLAlchemy relationships, 
        # but to be safe and use bulk delete we can delete options first if needed.
        # Since models use cascade="all, delete-orphan", we can query and delete the questions.
        Question.query.filter(
            Question.exam_id == exam.id,
            Question.id.in_(question_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        flash(f"Successfully deleted {len(question_ids)} selected questions.", "success")
    except Exception as e:
        db.session.rollback()
        import logging
        logging.error(f"Failed to delete questions for exam {exam_id}: {e}")
        flash("An error occurred while deleting the selected questions. Please check the logs.", "danger")
        
    return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))

@admin_questions_bp.route("/exams/<int:exam_id>/questions/duplicate_selected", methods=["POST"])
def duplicate_selected_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    question_ids = request.form.getlist("question_ids")
    
    if not question_ids:
        flash("Please select at least one question to duplicate.", "warning")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
        
    try:
        # Load all questions for the exam ordered by display_order
        all_questions = Question.query.filter_by(exam_id=exam.id).order_by(Question.display_order.asc()).all()
        
        # Identify the selected questions in their current display order
        selected_questions = [q for q in all_questions if str(q.id) in question_ids]
        
        if not selected_questions:
            flash("No valid questions selected.", "warning")
            return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
            
        # Find the index of the LAST selected question in the all_questions list
        last_selected_q = selected_questions[-1]
        insert_index = all_questions.index(last_selected_q) + 1
        
        new_questions = []
        # Duplicate questions
        for q in selected_questions:
            new_q = Question(
                exam_id=exam.id,
                question_text=q.question_text,
                marks=q.marks,
                display_order=0 # Will be updated below
            )
            db.session.add(new_q)
            db.session.flush() # Flush to get the new question ID
            
            # Map old option ID to new option ID for correct_option_id
            option_id_map = {}
            for opt in q.options:
                new_opt = QuestionOption(
                    question_id=new_q.id,
                    option_text=opt.option_text,
                    option_order=opt.option_order
                )
                db.session.add(new_opt)
                db.session.flush() # Flush to get new option ID
                option_id_map[opt.id] = new_opt.id
                
            if q.correct_option_id in option_id_map:
                new_q.correct_option_id = option_id_map[q.correct_option_id]
                
            new_questions.append(new_q)
            
        # Insert duplicated questions immediately after the last selected question
        all_questions = all_questions[:insert_index] + new_questions + all_questions[insert_index:]
        
        # Renumber all questions continuously
        for idx, q in enumerate(all_questions):
            q.display_order = idx + 1
            
        db.session.commit()
        flash(f"Successfully duplicated {len(selected_questions)} questions.", "success")
    except Exception as e:
        db.session.rollback()
        import logging
        logging.error(f"Failed to duplicate questions for exam {exam_id}: {e}")
        flash("An error occurred while duplicating the selected questions. Please check the logs.", "danger")
        
    return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))

@admin_questions_bp.route("/exams/<int:exam_id>/questions/import", methods=["GET", "POST"])
def upload_import(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if request.method == "POST":
        if 'file' not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash("No selected file.", "danger")
            return redirect(request.url)
            
        if file:
            filename = secure_filename(file.filename)
            temp_dir = os.path.join("instance", "uploads", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            filepath = os.path.join(temp_dir, filename)
            file.save(filepath)
            
            try:
                parser = get_parser(filename)
                parsed_questions = parser.parse(filepath)
                
                # -------------------------------------------------------
                # Run new ImportEngine in parallel (non-breaking)
                # The engine result is stored alongside the legacy data so
                # we can verify detection + extraction without touching any
                # existing preview or confirm route.
                # -------------------------------------------------------
                try:
                    engine_result = ImportEngine.process(
                        filepath=filepath,
                        filename=filename,
                        mime_type=file.mimetype if hasattr(file, 'mimetype') else None,
                    )
                    engine_metadata = {
                        "doc_type":            engine_result.doc_type.value,
                        "detection_confidence": engine_result.detection_confidence,
                        "extractor_name":       engine_result.extractor_name,
                        "question_count":       engine_result.question_count,
                        "valid_count":          len(engine_result.valid_questions),
                        "warnings":             engine_result.warnings,
                        "errors":               engine_result.errors,
                        "detection_signals":    engine_result.detection_signals,
                        "ocr_recommended":      engine_result.detection_signals.get("ocr_recommended", False),
                        "ocr_available":        engine_result.detection_signals.get("ocr_available", False),
                        "ocr_enabled":          engine_result.detection_signals.get("ocr_enabled", False),
                        "ai_enabled":           engine_result.detection_signals.get("ai_enabled", False),
                        "ai_provider":          engine_result.detection_signals.get("ai_provider", "gemini"),
                        "ai_document_type":     engine_result.metadata.get("ai_document_type"),
                        "ai_reasoning":         engine_result.metadata.get("ai_reasoning"),
                        "engine_config":        ImportEngine.get_config_summary(),
                    }
                except Exception as engine_exc:
                    engine_metadata = {"error": str(engine_exc)}
                
                # Save legacy questions + engine metadata to JSON
                import_uuid = str(uuid.uuid4())
                json_path = os.path.join(temp_dir, f"import_preview_{import_uuid}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "questions":       parsed_questions,
                        "engine_questions": engine_result.to_dict_list() if 'engine_result' in locals() else [],
                        "engine_metadata": engine_metadata,
                    }, f)
                    
                # Clean up the original uploaded file
                os.remove(filepath)
                
                return redirect(url_for('admin_questions.preview_import', exam_id=exam.id, import_id=import_uuid))
                
            except Exception as e:
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f"Error parsing file: {str(e)}", "danger")
                return redirect(request.url)
                
    return render_template("admin/questions/import_upload.html", exam=exam)

@admin_questions_bp.route("/exams/<int:exam_id>/questions/import/preview/<import_id>")
def preview_import(exam_id, import_id):
    exam = Exam.query.get_or_404(exam_id)
    temp_dir = os.path.join("instance", "uploads", "temp")
    json_path = os.path.join(temp_dir, f"import_preview_{import_id}.json")
    
    if not os.path.exists(json_path):
        flash("Import session expired or invalid. Please upload the file again.", "warning")
        return redirect(url_for('admin_questions.upload_import', exam_id=exam.id))
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Support both legacy (plain list) and new (dict with questions key) formats
        parsed_questions = data.get("questions", data) if isinstance(data, dict) else data
        engine_questions = data.get("engine_questions", []) if isinstance(data, dict) else []
        engine_metadata  = data.get("engine_metadata") if isinstance(data, dict) else None
        
    return render_template(
        "admin/questions/import_preview.html",
        exam=exam,
        questions=parsed_questions,
        engine_questions=engine_questions,
        import_id=import_id,
        engine_metadata=engine_metadata,
    )

@admin_questions_bp.route("/exams/<int:exam_id>/questions/import/confirm", methods=["POST"])
def confirm_import(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    import_id = request.form.get('import_id')
    
    if not import_id:
        flash("Invalid import session.", "danger")
        return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
        
    temp_dir = os.path.join("instance", "uploads", "temp")
    json_path = os.path.join(temp_dir, f"import_preview_{import_id}.json")
    
    if not os.path.exists(json_path):
        flash("Import session expired or invalid. Please upload the file again.", "warning")
        return redirect(url_for('admin_questions.upload_import', exam_id=exam.id))
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Check if frontend submitted AI workspace edits
    edits_json = request.form.get("edits_json")
    if edits_json:
        try:
            from app.services.import_engine.models import ExtractedQuestion, ExtractionResult
            from app.services.import_engine.validator import ValidatorLayer
            
            edits = json.loads(edits_json)
            engine_questions = data.get("engine_questions", [])
            objects_to_validate = []
            
            for eq in engine_questions:
                q_id = eq.get("id")
                
                # Check if edited or skipped
                if q_id in edits:
                    edit = edits[q_id]
                    if edit.get("status") == "skipped":
                        continue
                        
                    eq["question"] = edit.get("question_text", eq.get("question", ""))
                    eq["options"] = edit.get("options", eq.get("options", []))
                    
                    correct_idx = edit.get("correct_option_index")
                    if correct_idx is not None and str(correct_idx).strip():
                        eq["correct_option_index"] = int(correct_idx)
                    else:
                        eq["correct_option_index"] = None
                        
                    marks = edit.get("marks")
                    if marks is not None and str(marks).strip():
                        eq["marks"] = float(marks)

                # Reconstruct ExtractedQuestion for validation
                obj = ExtractedQuestion(
                    question_text=eq.get("question", ""),
                    options=eq.get("options", []),
                    correct_option_index=eq.get("correct_option_index"),
                    marks=eq.get("marks", 1.0)
                )
                objects_to_validate.append(obj)
                
            # Re-run validation
            result = ExtractionResult(questions=objects_to_validate)
            ValidatorLayer().validate(result)
            
            parsed_questions = []
            invalid_count = 0
            for obj in result.questions:
                if obj.is_valid:
                    parsed_questions.append({
                        "question": obj.question_text,
                        "options": obj.options,
                        "correct_option_index": obj.correct_option_index or 0,
                        "marks": obj.marks
                    })
                else:
                    invalid_count += 1
            
            if invalid_count > 0:
                flash(f"{invalid_count} questions were excluded from import due to lingering validation errors.", "warning")
                
        except Exception as e:
            flash(f"Failed to process AI review edits: {str(e)}", "danger")
            return redirect(url_for('admin_questions.upload_import', exam_id=exam.id))
    else:
        # Support both legacy (plain list) and new (dict with questions key) formats
        parsed_questions = data.get("questions", data) if isinstance(data, dict) else data
        
    # Get max display order
    max_order_question = Question.query.filter_by(exam_id=exam.id).order_by(Question.display_order.desc()).first()
    next_display_order = (max_order_question.display_order + 1) if max_order_question else 1
    
    count = 0
    for q_data in parsed_questions:
        new_question = Question(
            exam_id=exam.id,
            question_text=q_data['question'],
            marks=q_data['marks'],
            display_order=next_display_order
        )
        db.session.add(new_question)
        db.session.flush() # get id
        
        next_display_order += 1
        
        # Create options
        created_options = []
        for i, opt_text in enumerate(q_data['options']):
            opt = QuestionOption(
                question_id=new_question.id,
                option_text=opt_text,
                option_order=i + 1
            )
            db.session.add(opt)
            created_options.append((i, opt))
            
        db.session.flush()
        
        # Set correct option id
        correct_idx = q_data.get('correct_option_index', 0)
        for original_idx, opt in created_options:
            if original_idx == correct_idx:
                new_question.correct_option_id = opt.id
                break
                
        count += 1
        
    db.session.commit()
    
    # Clean up temp file
    if os.path.exists(json_path):
        os.remove(json_path)
        
    if count == 0:
        flash("0 questions were imported. Please review any validation errors or skipped items.", "danger")
    else:
        flash(f"Successfully imported {count} questions.", "success")
        
    return redirect(url_for('admin_questions.list_questions', exam_id=exam.id))
