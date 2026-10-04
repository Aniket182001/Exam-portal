from flask import Blueprint, render_template, abort, redirect, url_for, g, flash, request, send_file
from app.extensions import db
from app.utils.auth import login_required
from app.models.course import Course, CourseSection, Lesson, CourseEnrollment, LessonProgress, CourseMaterial
from app.services.lms_service import (
    get_student_course_curriculum,
    get_lesson_navigation,
    resolve_video_embed,
    calculate_course_progress,
    mark_lesson_complete,
    update_last_accessed_lesson,
    get_continue_learning_lesson,
    get_material_for_download,
)

lms_bp = Blueprint("lms", __name__, url_prefix="/lms")


@lms_bp.route("/")
@lms_bp.route("/dashboard")
@login_required
def dashboard():
    """LMS Student Landing & My Courses Dashboard."""
    is_admin = getattr(g, "current_user", None) and g.current_user.role == "admin"

    if is_admin:
        # Admins can view all active published courses
        courses = Course.query.filter_by(is_active=True).order_by(
            Course.display_order.asc(),
            Course.created_at.desc()
        ).all()
        enrolled_courses_data = []
        for c in courses:
            curriculum = get_student_course_curriculum(c.id)
            enrolled_courses_data.append({
                "enrollment": None,
                "course": c,
                "progress": {
                    "total_lessons": curriculum["total_published_lessons"],
                    "completed_lessons": 0,
                    "percentage": 0,
                    "is_completed": False,
                    "completed_lesson_ids": set(),
                },
                "continue_lesson": curriculum["first_lesson"],
                "total_sections": len([s for s in curriculum["sections"] if s["lessons"]]),
            })
    else:
        # Students: Only display courses the student is actively enrolled in
        enrollments = CourseEnrollment.query.filter_by(user_id=g.current_user.id).filter(
            CourseEnrollment.status.in_(["active", "completed"])
        ).order_by(CourseEnrollment.enrolled_at.desc()).all()

        enrolled_courses_data = []
        enrolled_course_ids = set()
        for enrollment in enrollments:
            course = enrollment.course
            if not course or not course.is_active or course.status != "published":
                continue

            enrolled_course_ids.add(course.id)
            curriculum = get_student_course_curriculum(course.id)
            progress = calculate_course_progress(enrollment.id)
            continue_lesson = get_continue_learning_lesson(enrollment)

            enrolled_courses_data.append({
                "enrollment": enrollment,
                "course": course,
                "progress": progress,
                "continue_lesson": continue_lesson,
                "total_sections": len([s for s in curriculum["sections"] if s["lessons"]]),
            })

        # Available / Catalog courses (published and active, not already enrolled)
        cat_query = Course.query.filter_by(is_active=True, status="published")
        if enrolled_course_ids:
            cat_query = cat_query.filter(Course.id.notin_(enrolled_course_ids))
        catalog_courses = cat_query.order_by(
            Course.display_order.asc(),
            Course.created_at.desc()
        ).all()

    return render_template(
        "lms/dashboard.html",
        enrolled_courses_data=enrolled_courses_data,
        catalog_courses=catalog_courses if not is_admin else [],
        is_admin=is_admin,
    )


@lms_bp.route("/courses/<slug>")
@login_required
def course_detail(slug):
    """LMS Course syllabus / outline view."""
    is_admin = getattr(g, "current_user", None) and g.current_user.role == "admin"
    query = Course.query.filter_by(slug=slug, is_active=True)
    if not is_admin:
        query = query.filter_by(status="published")
    course = query.first_or_404()

    enrollment = None
    progress = None
    continue_lesson = None

    if not is_admin:
        # Enforce student enrollment
        enrollment = CourseEnrollment.query.filter_by(
            user_id=g.current_user.id,
            course_id=course.id
        ).first()
        if not enrollment or enrollment.status == "withdrawn":
            abort(404)

        progress = calculate_course_progress(enrollment.id)
        continue_lesson = get_continue_learning_lesson(enrollment)
    else:
        # Optional admin enrollment preview
        enrollment = CourseEnrollment.query.filter_by(
            user_id=g.current_user.id,
            course_id=course.id
        ).first()
        if enrollment:
            progress = calculate_course_progress(enrollment.id)
            continue_lesson = get_continue_learning_lesson(enrollment)

    curriculum = get_student_course_curriculum(course.id)
    if not continue_lesson:
        continue_lesson = curriculum["first_lesson"]

    course_materials = CourseMaterial.query.filter_by(
        course_id=course.id,
        lesson_id=None
    ).order_by(CourseMaterial.created_at.asc()).all()

    return render_template(
        "lms/course_detail.html",
        course=course,
        enrollment=enrollment,
        progress=progress,
        continue_lesson=continue_lesson,
        curriculum_sections=curriculum["sections"],
        first_lesson=curriculum["first_lesson"],
        total_lessons=curriculum["total_published_lessons"],
        course_materials=course_materials,
    )


@lms_bp.route("/courses/<slug>/lessons/<int:lesson_id>")
@login_required
def view_lesson(slug, lesson_id):
    """Student Lesson Player page."""
    is_admin = getattr(g, "current_user", None) and g.current_user.role == "admin"

    # Verify course
    c_query = Course.query.filter_by(slug=slug, is_active=True)
    if not is_admin:
        c_query = c_query.filter_by(status="published")
    course = c_query.first_or_404()

    # Verify lesson
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson or not lesson.section or lesson.section.course_id != course.id:
        abort(404)

    # Check publication status
    if not is_admin and lesson.status != "published":
        abort(404)

    enrollment = None
    progress = None
    is_completed = False

    if not is_admin:
        # Enforce student enrollment
        enrollment = CourseEnrollment.query.filter_by(
            user_id=g.current_user.id,
            course_id=course.id
        ).first()
        if not enrollment or enrollment.status == "withdrawn":
            abort(404)

        update_last_accessed_lesson(enrollment.id, lesson.id)
        progress = calculate_course_progress(enrollment.id)
        is_completed = lesson.id in progress["completed_lesson_ids"]
    else:
        enrollment = CourseEnrollment.query.filter_by(
            user_id=g.current_user.id,
            course_id=course.id
        ).first()
        if enrollment:
            update_last_accessed_lesson(enrollment.id, lesson.id)
            progress = calculate_course_progress(enrollment.id)
            is_completed = lesson.id in progress["completed_lesson_ids"]

    embed_info = resolve_video_embed(lesson.video_provider, lesson.video_url)
    nav_info = get_lesson_navigation(course.id, lesson.id)
    curriculum = get_student_course_curriculum(course.id)

    lesson_materials = CourseMaterial.query.filter_by(
        lesson_id=lesson.id
    ).order_by(CourseMaterial.created_at.asc()).all()

    return render_template(
        "lms/lesson.html",
        course=course,
        section=lesson.section,
        lesson=lesson,
        enrollment=enrollment,
        progress=progress,
        is_completed=is_completed,
        embed_info=embed_info,
        nav_info=nav_info,
        curriculum_sections=curriculum["sections"],
        total_lessons=curriculum["total_published_lessons"],
        lesson_materials=lesson_materials,
    )


@lms_bp.route("/courses/<slug>/lessons/<int:lesson_id>/complete", methods=["POST"])
@login_required
def complete_lesson(slug, lesson_id):
    """Mark a lesson complete for an enrolled student."""
    is_admin = getattr(g, "current_user", None) and g.current_user.role == "admin"

    c_query = Course.query.filter_by(slug=slug, is_active=True)
    if not is_admin:
        c_query = c_query.filter_by(status="published")
    course = c_query.first_or_404()

    lesson = db.session.get(Lesson, lesson_id)
    if not lesson or not lesson.section or lesson.section.course_id != course.id:
        abort(404)

    if not is_admin and lesson.status != "published":
        abort(404)

    enrollment = CourseEnrollment.query.filter_by(
        user_id=g.current_user.id,
        course_id=course.id
    ).first()

    if not enrollment or enrollment.status == "withdrawn":
        if not is_admin:
            abort(404)
        else:
            flash("Admins not enrolled in this course do not have progress records tracked.", "info")
            return redirect(url_for("lms.view_lesson", slug=course.slug, lesson_id=lesson.id))

    success, msg, calc = mark_lesson_complete(enrollment.id, lesson.id)
    if success:
        if calc.get("is_completed"):
            flash("Congratulations! You have completed all lessons in this course!", "success")
        else:
            flash(f"Lesson '{lesson.title}' marked as complete.", "success")
    else:
        flash(msg, "warning")

    return redirect(url_for("lms.view_lesson", slug=course.slug, lesson_id=lesson.id))


@lms_bp.route("/lessons/<int:lesson_id>")
@login_required
def redirect_lesson(lesson_id):
    """Shortcut / redirect to the canonical course lesson player route with enrollment check."""
    is_admin = getattr(g, "current_user", None) and g.current_user.role == "admin"
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson or not lesson.section or not lesson.section.course:
        abort(404)

    course = lesson.section.course
    if not is_admin:
        if not course.is_active or course.status != "published" or lesson.status != "published":
            abort(404)

        enrollment = CourseEnrollment.query.filter_by(
            user_id=g.current_user.id,
            course_id=course.id
        ).first()
        if not enrollment or enrollment.status == "withdrawn":
            abort(404)

    return redirect(url_for("lms.view_lesson", slug=course.slug, lesson_id=lesson.id))


@lms_bp.route("/materials/<int:material_id>/download")
@login_required
def download_material(material_id):
    """Secure, enrollment-authorized download of course and lesson materials."""
    material, physical_path, error = get_material_for_download(material_id, g.current_user)

    if error in ["not_found", "forbidden"]:
        abort(404)
    elif error == "invalid_path":
        abort(400)
    elif error == "file_missing":
        flash("The requested material file is currently unavailable on storage.", "danger")
        abort(404)

    return send_file(
        physical_path,
        as_attachment=True,
        download_name=material.original_filename,
        mimetype=material.mime_type
    )
