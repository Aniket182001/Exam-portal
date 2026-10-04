from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.extensions import db
from app.utils.auth import admin_required
from app.models.user import User
from app.models.course import Course, CourseSection, Lesson, CourseEnrollment, LessonProgress, CourseMaterial
from app.services.lms_service import (
    generate_unique_slug,
    validate_video_url,
    reorder_courses,
    reorder_sections,
    reorder_lessons,
    calculate_course_progress,
    enroll_student_in_course,
    update_enrollment_status,
    save_course_material,
    delete_course_material,
    SUPPORTED_VIDEO_PROVIDERS,
    COURSE_STATUSES,
    LESSON_STATUSES,
    ENROLLMENT_STATUSES,
)

admin_lms_bp = Blueprint("admin_lms", __name__, url_prefix="/admin/lms")


@admin_lms_bp.before_request
@admin_required
def require_admin():
    """Ensure all LMS admin routes require admin privileges."""
    pass


# ── Course Management ────────────────────────────────────────────────────────

@admin_lms_bp.route("/")
@admin_lms_bp.route("/dashboard")
@admin_lms_bp.route("/courses")
def dashboard():
    """LMS Administration Dashboard & Course List."""
    status_filter = request.args.get("status", "").strip().lower()
    search = request.args.get("search", "").strip()

    query = Course.query

    if status_filter and status_filter in COURSE_STATUSES:
        query = query.filter_by(status=status_filter)

    if search:
        query = query.filter(
            db.or_(
                Course.title.ilike(f"%{search}%"),
                Course.slug.ilike(f"%{search}%"),
                Course.description.ilike(f"%{search}%")
            )
        )

    courses = query.order_by(
        Course.display_order.asc(),
        Course.created_at.desc()
    ).all()

    total_courses = Course.query.count()
    total_sections = CourseSection.query.count()
    total_lessons = Lesson.query.count()

    return render_template(
        "admin/lms/dashboard.html",
        courses=courses,
        total_courses=total_courses,
        total_sections=total_sections,
        total_lessons=total_lessons,
        status_filter=status_filter,
        search=search,
    )


@admin_lms_bp.route("/courses/create", methods=["GET", "POST"])
def create_course():
    """Create a new course."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        custom_slug = request.form.get("slug", "").strip()
        status = request.form.get("status", "draft").strip().lower()
        display_order_str = request.form.get("display_order", "").strip()

        # Validation
        if not title:
            flash("Course title is required.", "danger")
            return render_template("admin/lms/course_form.html", course=None, mode="create", statuses=COURSE_STATUSES)

        if len(title) > 200:
            flash("Course title cannot exceed 200 characters.", "danger")
            return render_template("admin/lms/course_form.html", course=None, mode="create", statuses=COURSE_STATUSES)

        if status not in COURSE_STATUSES:
            status = "draft"

        # Determine display order
        try:
            display_order = int(display_order_str) if display_order_str else (Course.query.count() + 1)
        except ValueError:
            display_order = Course.query.count() + 1

        # Generate unique slug
        slug = generate_unique_slug(custom_slug if custom_slug else title)

        course = Course(
            title=title,
            slug=slug,
            description=description if description else None,
            status=status,
            display_order=display_order,
            is_active=(status != "archived"),
        )
        db.session.add(course)
        db.session.commit()

        flash(f"Course '{course.title}' created successfully! You can now organize sections and lessons.", "success")
        return redirect(url_for("admin_lms.course_content", course_id=course.id))

    default_order = Course.query.count() + 1
    return render_template("admin/lms/course_form.html", course=None, mode="create", statuses=COURSE_STATUSES, default_order=default_order)


@admin_lms_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def edit_course(course_id):
    """Edit an existing course."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        custom_slug = request.form.get("slug", "").strip()
        status = request.form.get("status", "draft").strip().lower()
        display_order_str = request.form.get("display_order", "").strip()

        if not title:
            flash("Course title is required.", "danger")
            return render_template("admin/lms/course_form.html", course=course, mode="edit", statuses=COURSE_STATUSES)

        if len(title) > 200:
            flash("Course title cannot exceed 200 characters.", "danger")
            return render_template("admin/lms/course_form.html", course=course, mode="edit", statuses=COURSE_STATUSES)

        if status not in COURSE_STATUSES:
            status = "draft"

        try:
            display_order = int(display_order_str) if display_order_str else course.display_order
        except ValueError:
            display_order = course.display_order

        # Generate slug if modified or empty
        if custom_slug and custom_slug != course.slug:
            slug = generate_unique_slug(custom_slug, existing_course_id=course.id)
        else:
            slug = course.slug

        course.title = title
        course.slug = slug
        course.description = description if description else None
        course.status = status
        course.display_order = display_order
        course.is_active = (status != "archived")
        course.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f"Course '{course.title}' updated successfully.", "success")
        return redirect(url_for("admin_lms.course_content", course_id=course.id))

    return render_template("admin/lms/course_form.html", course=course, mode="edit", statuses=COURSE_STATUSES)


@admin_lms_bp.route("/courses/<int:course_id>/status", methods=["POST"])
def update_course_status(course_id):
    """Quickly update course status (Draft / Published / Archived)."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    new_status = request.form.get("status", "").strip().lower()
    if new_status in COURSE_STATUSES:
        course.status = new_status
        course.is_active = (new_status != "archived")
        course.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Course '{course.title}' status changed to {new_status.capitalize()}.", "success")
    else:
        flash("Invalid status specified.", "danger")

    return redirect(request.referrer or url_for("admin_lms.dashboard"))


@admin_lms_bp.route("/courses/<int:course_id>/archive", methods=["POST"])
def archive_course(course_id):
    """Soft-archive a course without deleting records."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    course.status = "archived"
    course.is_active = False
    course.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Course '{course.title}' has been archived.", "info")
    return redirect(url_for("admin_lms.dashboard"))


@admin_lms_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def delete_course(course_id):
    """
    Safely delete a course and cascading sections/lessons.
    Guarded: cannot delete courses that have active enrollments.
    """
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    if course.enrollments:
        flash(f"Cannot delete course '{course.title}' because it has student enrollments or learning records. Please archive the course instead.", "danger")
        return redirect(url_for("admin_lms.dashboard"))

    course_title = course.title

    # Clean up physical files for all materials attached to this course
    for material in list(course.materials):
        delete_course_material(material.id)

    db.session.delete(course)
    db.session.commit()

    flash(f"Course '{course_title}' deleted successfully.", "success")
    return redirect(url_for("admin_lms.dashboard"))


@admin_lms_bp.route("/courses/<int:course_id>/reorder", methods=["POST"])
def reorder_course(course_id):
    """Reorder a course up or down in the course catalog."""
    direction = request.form.get("direction", "").strip().lower()
    if direction in ["up", "down"]:
        reorder_courses(course_id, direction)
    return redirect(url_for("admin_lms.dashboard"))


# ── Course Content Management (Sections & Lessons) ──────────────────────────

@admin_lms_bp.route("/courses/<int:course_id>/content")
def course_content(course_id):
    """Manage course syllabus, sections, and lesson hierarchy."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    # Sections pre-ordered by display_order
    sections = CourseSection.query.filter_by(course_id=course.id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    return render_template(
        "admin/lms/course_content.html",
        course=course,
        sections=sections,
        video_providers=SUPPORTED_VIDEO_PROVIDERS,
    )


# ── Section Management ───────────────────────────────────────────────────────

@admin_lms_bp.route("/courses/<int:course_id>/sections/create", methods=["POST"])
def create_section(course_id):
    """Create a new section under a course."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    order_str = request.form.get("display_order", "").strip()

    if not title:
        flash("Section title is required.", "danger")
        return redirect(url_for("admin_lms.course_content", course_id=course_id))

    try:
        display_order = int(order_str) if order_str else (len(course.sections) + 1)
    except ValueError:
        display_order = len(course.sections) + 1

    section = CourseSection(
        course_id=course.id,
        title=title,
        description=description if description else None,
        display_order=display_order,
    )
    db.session.add(section)
    db.session.commit()

    flash(f"Section '{section.title}' added successfully.", "success")
    return redirect(url_for("admin_lms.course_content", course_id=course_id))


@admin_lms_bp.route("/sections/<int:section_id>/edit", methods=["POST"])
def edit_section(section_id):
    """Edit section details."""
    section = db.session.get(CourseSection, section_id)
    if not section:
        abort(404)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    order_str = request.form.get("display_order", "").strip()

    if not title:
        flash("Section title is required.", "danger")
        return redirect(url_for("admin_lms.course_content", course_id=section.course_id))

    try:
        display_order = int(order_str) if order_str else section.display_order
    except ValueError:
        display_order = section.display_order

    section.title = title
    section.description = description if description else None
    section.display_order = display_order
    section.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    flash(f"Section '{section.title}' updated successfully.", "success")
    return redirect(url_for("admin_lms.course_content", course_id=section.course_id))


@admin_lms_bp.route("/sections/<int:section_id>/reorder", methods=["POST"])
def reorder_section(section_id):
    """Reorder a section up or down within its course."""
    section = db.session.get(CourseSection, section_id)
    if not section:
        abort(404)

    direction = request.form.get("direction", "").strip().lower()
    if direction in ["up", "down"]:
        reorder_sections(section.course_id, section_id, direction)

    return redirect(url_for("admin_lms.course_content", course_id=section.course_id))


@admin_lms_bp.route("/sections/<int:section_id>/delete", methods=["POST"])
def delete_section(section_id):
    """Delete a section and its lessons."""
    section = db.session.get(CourseSection, section_id)
    if not section:
        abort(404)

    course_id = section.course_id
    sec_title = section.title

    # Data integrity check: prevent deleting if lessons have progress history
    has_learning_records = any(l.progress_records for l in section.lessons)
    if has_learning_records:
        flash(f"Cannot delete section '{sec_title}' because its lessons contain student progress history.", "danger")
        return redirect(url_for("admin_lms.course_content", course_id=course_id))

    # Clean up physical material files on disk for lessons in this section
    for lesson in list(section.lessons):
        for material in list(lesson.materials):
            delete_course_material(material.id)

    db.session.delete(section)
    db.session.commit()

    flash(f"Section '{sec_title}' and its lessons were removed.", "success")
    return redirect(url_for("admin_lms.course_content", course_id=course_id))


# ── Lesson Management ────────────────────────────────────────────────────────

@admin_lms_bp.route("/sections/<int:section_id>/lessons/create", methods=["GET", "POST"])
def create_lesson(section_id):
    """Create a new lesson under a section."""
    section = db.session.get(CourseSection, section_id)
    if not section:
        abort(404)

    course = section.course

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "draft").strip().lower()
        order_str = request.form.get("display_order", "").strip()
        video_provider = request.form.get("video_provider", "").strip().lower()
        video_url = request.form.get("video_url", "").strip()

        if not title:
            flash("Lesson title is required.", "danger")
            return render_template(
                "admin/lms/lesson_form.html",
                mode="create",
                section=section,
                course=course,
                lesson=None,
                video_providers=SUPPORTED_VIDEO_PROVIDERS,
                statuses=LESSON_STATUSES,
            )

        if status not in LESSON_STATUSES:
            status = "draft"

        try:
            display_order = int(order_str) if order_str else (len(section.lessons) + 1)
        except ValueError:
            display_order = len(section.lessons) + 1

        # Validate video URL against selected provider
        is_valid, error_msg, cleaned_url = validate_video_url(
            video_provider if video_provider else None,
            video_url if video_url else None
        )
        if not is_valid:
            flash(error_msg, "danger")
            return render_template(
                "admin/lms/lesson_form.html",
                mode="create",
                section=section,
                course=course,
                lesson=None,
                form_data=request.form,
                video_providers=SUPPORTED_VIDEO_PROVIDERS,
                statuses=LESSON_STATUSES,
            )

        lesson = Lesson(
            section_id=section.id,
            title=title,
            description=description if description else None,
            status=status,
            display_order=display_order,
            video_provider=video_provider if video_provider else None,
            video_url=cleaned_url,
        )
        db.session.add(lesson)
        db.session.commit()

        flash(f"Lesson '{lesson.title}' created successfully.", "success")
        return redirect(url_for("admin_lms.course_content", course_id=course.id))

    default_order = len(section.lessons) + 1
    return render_template(
        "admin/lms/lesson_form.html",
        mode="create",
        section=section,
        course=course,
        lesson=None,
        default_order=default_order,
        video_providers=SUPPORTED_VIDEO_PROVIDERS,
        statuses=LESSON_STATUSES,
    )


@admin_lms_bp.route("/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
def edit_lesson(lesson_id):
    """Edit an existing lesson."""
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        abort(404)

    section = lesson.section
    course = section.course

    # Available sections in this course for moving lesson
    available_sections = CourseSection.query.filter_by(course_id=course.id).order_by(
        CourseSection.display_order.asc()
    ).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "draft").strip().lower()
        order_str = request.form.get("display_order", "").strip()
        target_section_id_str = request.form.get("section_id", "").strip()
        video_provider = request.form.get("video_provider", "").strip().lower()
        video_url = request.form.get("video_url", "").strip()

        if not title:
            flash("Lesson title is required.", "danger")
            return render_template(
                "admin/lms/lesson_form.html",
                mode="edit",
                lesson=lesson,
                section=section,
                course=course,
                available_sections=available_sections,
                video_providers=SUPPORTED_VIDEO_PROVIDERS,
                statuses=LESSON_STATUSES,
            )

        if status not in LESSON_STATUSES:
            status = "draft"

        try:
            display_order = int(order_str) if order_str else lesson.display_order
        except ValueError:
            display_order = lesson.display_order

        # Allow moving to another section in the course
        try:
            target_sec_id = int(target_section_id_str) if target_section_id_str else section.id
            target_sec = db.session.get(CourseSection, target_sec_id)
            if target_sec and target_sec.course_id == course.id:
                lesson.section_id = target_sec.id
        except ValueError:
            pass

        # Validate video URL against selected provider
        is_valid, error_msg, cleaned_url = validate_video_url(
            video_provider if video_provider else None,
            video_url if video_url else None
        )
        if not is_valid:
            flash(error_msg, "danger")
            return render_template(
                "admin/lms/lesson_form.html",
                mode="edit",
                lesson=lesson,
                section=section,
                course=course,
                form_data=request.form,
                available_sections=available_sections,
                video_providers=SUPPORTED_VIDEO_PROVIDERS,
                statuses=LESSON_STATUSES,
            )

        lesson.title = title
        lesson.description = description if description else None
        lesson.status = status
        lesson.display_order = display_order
        lesson.video_provider = video_provider if video_provider else None
        lesson.video_url = cleaned_url
        lesson.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f"Lesson '{lesson.title}' updated successfully.", "success")
        return redirect(url_for("admin_lms.course_content", course_id=course.id))

    return render_template(
        "admin/lms/lesson_form.html",
        mode="edit",
        lesson=lesson,
        section=section,
        course=course,
        available_sections=available_sections,
        video_providers=SUPPORTED_VIDEO_PROVIDERS,
        statuses=LESSON_STATUSES,
    )


@admin_lms_bp.route("/lessons/<int:lesson_id>/status", methods=["POST"])
def toggle_lesson_status(lesson_id):
    """Toggle lesson between Draft and Published."""
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        abort(404)

    course_id = lesson.section.course_id
    lesson.status = "published" if lesson.status == "draft" else "draft"
    lesson.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Lesson '{lesson.title}' status changed to {lesson.status.capitalize()}.", "success")
    return redirect(url_for("admin_lms.course_content", course_id=course_id))


@admin_lms_bp.route("/lessons/<int:lesson_id>/reorder", methods=["POST"])
def reorder_lesson(lesson_id):
    """Reorder a lesson up or down within its section."""
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        abort(404)

    direction = request.form.get("direction", "").strip().lower()
    if direction in ["up", "down"]:
        reorder_lessons(lesson.section_id, lesson_id, direction)

    return redirect(url_for("admin_lms.course_content", course_id=lesson.section.course_id))


@admin_lms_bp.route("/lessons/<int:lesson_id>/delete", methods=["POST"])
def delete_lesson(lesson_id):
    """Delete a lesson."""
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        abort(404)

    course_id = lesson.section.course_id
    les_title = lesson.title

    # Data integrity check
    if lesson.progress_records:
        flash(f"Cannot delete lesson '{les_title}' because students have progress records for it. Please set its status to Draft instead.", "danger")
        return redirect(url_for("admin_lms.course_content", course_id=course_id))

    # Clean up physical material files on disk for this lesson
    for material in list(lesson.materials):
        delete_course_material(material.id)

    db.session.delete(lesson)
    db.session.commit()

    flash(f"Lesson '{les_title}' deleted.", "success")
    return redirect(url_for("admin_lms.course_content", course_id=course_id))


# ── Enrollment & Progress Management ─────────────────────────────────────────

@admin_lms_bp.route("/enrollments")
def enrollments_list():
    """Admin view of all student course enrollments and progress."""
    course_id = request.args.get("course_id", type=int)
    status_filter = request.args.get("status", "").strip().lower()
    search_query = request.args.get("q", "").strip()

    query = CourseEnrollment.query.join(User, CourseEnrollment.user_id == User.id).join(Course, CourseEnrollment.course_id == Course.id)

    if course_id:
        query = query.filter(CourseEnrollment.course_id == course_id)
    if status_filter in ENROLLMENT_STATUSES:
        query = query.filter(CourseEnrollment.status == status_filter)
    if search_query:
        query = query.filter(
            (User.username.ilike(f"%{search_query}%")) |
            (User.email.ilike(f"%{search_query}%")) |
            (Course.title.ilike(f"%{search_query}%"))
        )

    enrollments = query.order_by(CourseEnrollment.enrolled_at.desc()).all()

    enrollment_data = []
    for enr in enrollments:
        progress = calculate_course_progress(enr.id)
        enrollment_data.append({
            "enrollment": enr,
            "progress": progress,
        })

    all_courses = Course.query.filter_by(is_active=True).order_by(Course.title.asc()).all()
    all_students = User.query.filter(User.role != "admin").order_by(User.username.asc()).all()

    # Metrics
    total_enrollments = CourseEnrollment.query.count()
    active_enrollments = CourseEnrollment.query.filter_by(status="active").count()
    completed_enrollments = CourseEnrollment.query.filter_by(status="completed").count()

    return render_template(
        "admin/lms/enrollments.html",
        enrollment_data=enrollment_data,
        all_courses=all_courses,
        all_students=all_students,
        current_course_id=course_id,
        current_status=status_filter,
        search_query=search_query,
        total_enrollments=total_enrollments,
        active_enrollments=active_enrollments,
        completed_enrollments=completed_enrollments,
    )


@admin_lms_bp.route("/enrollments/create", methods=["POST"])
def create_enrollment():
    """Enroll a student into a course."""
    user_id = request.form.get("user_id", type=int)
    course_id = request.form.get("course_id", type=int)

    if not user_id or not course_id:
        flash("Please select both a student and a course.", "danger")
        return redirect(url_for("admin_lms.enrollments_list"))

    enrollment, msg = enroll_student_in_course(user_id, course_id)
    if enrollment:
        flash(msg, "success")
    else:
        flash(msg, "warning")

    return redirect(url_for("admin_lms.enrollments_list", course_id=course_id))


@admin_lms_bp.route("/enrollments/<int:enrollment_id>/status", methods=["POST"])
def change_enrollment_status(enrollment_id):
    """Activate, complete, or withdraw an enrollment."""
    new_status = request.form.get("status", "").strip().lower()
    success, msg = update_enrollment_status(enrollment_id, new_status)

    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(url_for("admin_lms.enrollments_list"))


# ── Course Materials Management ──────────────────────────────────────────────

@admin_lms_bp.route("/courses/<int:course_id>/materials")
def course_materials(course_id):
    """View and manage downloadable materials for a course."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    materials = CourseMaterial.query.filter_by(course_id=course.id).order_by(
        CourseMaterial.created_at.desc()
    ).all()

    sections = CourseSection.query.filter_by(course_id=course.id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    return render_template(
        "admin/lms/materials.html",
        course=course,
        materials=materials,
        sections=sections,
    )


@admin_lms_bp.route("/courses/<int:course_id>/materials/upload", methods=["POST"])
def upload_course_material(course_id):
    """Upload a new course or lesson material."""
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)

    display_name = request.form.get("display_name", "").strip()
    lesson_id_str = request.form.get("lesson_id", "").strip()
    file = request.files.get("file")

    lesson_id = None
    if lesson_id_str:
        try:
            cand_id = int(lesson_id_str)
            cand_lesson = db.session.get(Lesson, cand_id)
            if cand_lesson and cand_lesson.section and cand_lesson.section.course_id == course.id:
                lesson_id = cand_id
            else:
                flash("Selected lesson does not belong to this course.", "danger")
                return redirect(url_for("admin_lms.course_materials", course_id=course.id))
        except ValueError:
            pass

    material, msg = save_course_material(course.id, lesson_id, file, display_name)
    if material:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(url_for("admin_lms.course_materials", course_id=course.id))


@admin_lms_bp.route("/materials/<int:material_id>/delete", methods=["POST"])
def delete_material(material_id):
    """Delete a course material and remove its physical file from disk."""
    material = db.session.get(CourseMaterial, material_id)
    if not material:
        abort(404)

    course_id = material.course_id
    display_name = material.display_name

    success, msg = delete_course_material(material.id)
    if success:
        flash(f"Material '{display_name}' was deleted successfully.", "success")
    else:
        flash(msg, "danger")

    return redirect(url_for("admin_lms.course_materials", course_id=course_id))

