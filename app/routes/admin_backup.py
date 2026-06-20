import os
import json
import zipfile
import io
from datetime import datetime
from flask import Blueprint, render_template, request, flash, send_file, redirect, url_for
from app.extensions import db
from app.models import Exam, Question, QuestionOption, StudentAttempt, StudentAnswer

admin_backup_bp = Blueprint("admin_backup", __name__, url_prefix="/admin/backup")

def serialize_model(instance):
    data = {}
    for column in instance.__table__.columns:
        val = getattr(instance, column.name)
        if isinstance(val, datetime):
            data[column.name] = val.isoformat()
        else:
            data[column.name] = val
    return data

def deserialize_model(model_class, data):
    for column in model_class.__table__.columns:
        if isinstance(column.type, db.DateTime) and data.get(column.name):
            try:
                data[column.name] = datetime.fromisoformat(data[column.name])
            except ValueError:
                data[column.name] = None
    return model_class(**data)

@admin_backup_bp.route("/")
def index():
    return render_template("admin/backup.html")

@admin_backup_bp.route("/download")
def download():
    # Serialize data
    exams = [serialize_model(e) for e in Exam.query.all()]
    questions = [serialize_model(q) for q in Question.query.all()]
    options = [serialize_model(o) for o in QuestionOption.query.all()]
    attempts = [serialize_model(a) for a in StudentAttempt.query.all()]
    answers = [serialize_model(a) for a in StudentAnswer.query.all()]

    # Create ZIP in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('exams.json', json.dumps(exams))
        zf.writestr('questions.json', json.dumps(questions))
        zf.writestr('question_options.json', json.dumps(options))
        zf.writestr('student_attempts.json', json.dumps(attempts))
        zf.writestr('student_answers.json', json.dumps(answers))
    
    memory_file.seek(0)
    
    filename = f"backup_{datetime.now().strftime('%Y_%m_%d_%H_%M')}.zip"
    return send_file(memory_file, download_name=filename, as_attachment=True)

@admin_backup_bp.route("/restore", methods=["POST"])
def restore():
    if 'file' not in request.files:
        flash("No file uploaded.", "danger")
        return redirect(url_for('admin_backup.index'))
        
    file = request.files['file']
    if not file.filename.endswith('.zip'):
        flash("Invalid file type. Please upload a ZIP file.", "danger")
        return redirect(url_for('admin_backup.index'))

    try:
        with zipfile.ZipFile(file, 'r') as zf:
            def load_json(filename):
                if filename in zf.namelist():
                    return json.loads(zf.read(filename))
                return []

            exams_data = load_json('exams.json')
            questions_data = load_json('questions.json')
            options_data = load_json('question_options.json')
            attempts_data = load_json('student_attempts.json')
            answers_data = load_json('student_answers.json')

            for data in exams_data:
                db.session.merge(deserialize_model(Exam, data))
            db.session.flush()

            for data in questions_data:
                db.session.merge(deserialize_model(Question, data))
            db.session.flush()

            for data in options_data:
                db.session.merge(deserialize_model(QuestionOption, data))
            db.session.flush()

            for data in attempts_data:
                db.session.merge(deserialize_model(StudentAttempt, data))
            db.session.flush()

            for data in answers_data:
                db.session.merge(deserialize_model(StudentAnswer, data))
            
            db.session.commit()
            flash("Backup restored successfully.", "success")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Error restoring backup: {str(e)}", "danger")

    return redirect(url_for('admin_backup.index'))
