"""
Comprehensive tests for Phase 5: LMS Course Materials & Downloads.

Covers:
- CourseMaterial model and properties (file_extension, formatted_size, formatted_file_size)
- File validation (allowed vs prohibited extensions, file size limits)
- Path traversal protection and secure filename storage
- Admin material management routes (view, upload, delete)
- Safe physical file cleanup on material, lesson, section, and course deletion
- Secure student downloads with authorization checks (enrolled vs unenrolled, withdrawn, draft lesson)
- Admin download access
"""
import io
import os
import pytest
from app.models import User, Course, CourseSection, Lesson, CourseEnrollment, CourseMaterial, LessonProgress
from app.services.lms_service import (
    save_course_material,
    delete_course_material,
    get_material_for_download,
    validate_material_file,
    get_material_upload_dir,
)
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash


@pytest.fixture
def test_upload_dir(tmp_path, monkeypatch, app):
    """Isolate material uploads to a temporary directory for tests."""
    upload_dir = str(tmp_path / "materials")
    os.makedirs(upload_dir, exist_ok=True)
    monkeypatch.setitem(app.config, "LMS_MATERIAL_UPLOAD_DIR", upload_dir)
    return upload_dir


import uuid


@pytest.fixture
def sample_course(db, app):
    """Create a sample published course with section and lessons."""
    uid = uuid.uuid4().hex[:8]
    slug = f"materials-test-course-{uid}"
    with app.app_context():
        course = Course(
            title=f"Materials Test Course {uid}",
            slug=slug,
            description="Testing downloadable materials",
            status="published",
            is_active=True,
            display_order=1,
        )
        db.session.add(course)
        db.session.flush()

        section = CourseSection(
            course_id=course.id,
            title="Section 1: Basics",
            display_order=1,
        )
        db.session.add(section)
        db.session.flush()

        lesson1 = Lesson(
            section_id=section.id,
            title="Lesson 1: Intro",
            status="published",
            display_order=1,
        )
        lesson_draft = Lesson(
            section_id=section.id,
            title="Lesson 2: Draft Lesson",
            status="draft",
            display_order=2,
        )
        db.session.add_all([lesson1, lesson_draft])
        db.session.commit()

        c_id = course.id
        s_id = section.id
        l1_id = lesson1.id
        ld_id = lesson_draft.id

    with app.app_context():
        yield {
            "course_id": c_id,
            "section_id": s_id,
            "lesson_id": l1_id,
            "draft_lesson_id": ld_id,
            "slug": slug,
        }
        db.session.query(CourseMaterial).filter_by(course_id=c_id).delete()
        db.session.query(CourseEnrollment).filter_by(course_id=c_id).delete()
        sec_ids = [s.id for s in db.session.query(CourseSection).filter_by(course_id=c_id).all()]
        if sec_ids:
            les_ids = [l.id for l in db.session.query(Lesson).filter(Lesson.section_id.in_(sec_ids)).all()]
            if les_ids:
                db.session.query(LessonProgress).filter(LessonProgress.lesson_id.in_(les_ids)).delete(synchronize_session=False)
                db.session.query(Lesson).filter(Lesson.id.in_(les_ids)).delete(synchronize_session=False)
            db.session.query(CourseSection).filter(CourseSection.id.in_(sec_ids)).delete(synchronize_session=False)
        db.session.query(Course).filter_by(id=c_id).delete()
        db.session.commit()


@pytest.fixture
def student_user(db, app):
    """Authenticated student user."""
    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            username=f"mat_student_{uid}",
            email=f"mat_student_{uid}@example.com",
            password_hash=generate_password_hash("Pass123!"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        u_id = user.id

    with app.app_context():
        yield db.session.get(User, u_id)
        u_del = db.session.get(User, u_id)
        if u_del:
            db.session.delete(u_del)
            db.session.commit()


@pytest.fixture
def student_client(client, student_user):
    """Client authenticated as student_user."""
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id
    return client


@pytest.fixture
def unenrolled_student(db, app):
    """Another student not enrolled in the course."""
    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            username=f"unenrolled_student_{uid}",
            email=f"unenrolled_{uid}@example.com",
            password_hash=generate_password_hash("Pass123!"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        u_id = user.id

    with app.app_context():
        yield db.session.get(User, u_id)
        u_del = db.session.get(User, u_id)
        if u_del:
            db.session.delete(u_del)
            db.session.commit()


@pytest.fixture
def unenrolled_client(client, unenrolled_student):
    """Client authenticated as unenrolled student."""
    with client.session_transaction() as sess:
        sess["user_id"] = unenrolled_student.id
    return client


# ── Model & Properties Tests ─────────────────────────────────────────────────

def test_course_material_properties(db, app, sample_course):
    """Test CourseMaterial properties: file_extension and formatted_size."""
    with app.app_context():
        material_kb = CourseMaterial(
            course_id=sample_course["course_id"],
            display_name="Guide PDF",
            original_filename="guide.pdf",
            stored_filename="guide_123.pdf",
            file_path="guide_123.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        material_mb = CourseMaterial(
            course_id=sample_course["course_id"],
            display_name="Big Archive",
            original_filename="archive.tar.zip",
            stored_filename="archive_456.zip",
            file_path="archive_456.zip",
            file_size=5 * 1024 * 1024,
            mime_type="application/zip",
        )
        db.session.add_all([material_kb, material_mb])
        db.session.commit()

        assert material_kb.file_extension == "pdf"
        assert material_kb.formatted_size == "2.0 KB"
        assert material_kb.formatted_file_size == "2.0 KB"

        assert material_mb.file_extension == "zip"
        assert material_mb.formatted_size == "5.0 MB"


# ── File Validation Tests ────────────────────────────────────────────────────

def test_validate_material_file_valid():
    """Valid files within size limits and allowed extensions pass validation."""
    content = b"PDF dummy content"
    file = FileStorage(
        stream=io.BytesIO(content),
        filename="curriculum.pdf",
        content_type="application/pdf",
    )
    is_valid, err, orig_name, mime, size = validate_material_file(file)
    assert is_valid is True
    assert err == ""
    assert orig_name == "curriculum.pdf"
    assert size == len(content)


def test_validate_material_file_empty_name(app, db, sample_course):
    """Empty display name in save_course_material fails validation."""
    with app.app_context():
        file = FileStorage(stream=io.BytesIO(b"data"), filename="test.pdf")
        material, msg = save_course_material(
            sample_course["course_id"],
            None,
            file,
            "   "
        )
        assert material is None
        assert "display name is required" in msg.lower()


def test_validate_material_file_no_file():
    """Missing file or empty filename fails validation."""
    is_valid, err, _, _, _ = validate_material_file(None)
    assert is_valid is False
    assert "No file selected" in err

    empty_file = FileStorage(stream=io.BytesIO(b""), filename="")
    is_valid2, err2, _, _, _ = validate_material_file(empty_file)
    assert is_valid2 is False
    assert "No file selected" in err2


def test_validate_material_file_disallowed_extension():
    """Executable or script extensions must be rejected."""
    bad_extensions = ["script.sh", "malware.exe", "test.py", "index.html", "bad.bat", "exploit.php"]
    for fname in bad_extensions:
        file = FileStorage(stream=io.BytesIO(b"bad content"), filename=fname)
        is_valid, err, _, _, _ = validate_material_file(file)
        assert is_valid is False
        assert "not permitted" in err or "Unsupported file type" in err


def test_validate_material_file_oversized():
    """Files exceeding maximum allowed size must be rejected."""
    oversized = io.BytesIO(b"x" * 200)
    file = FileStorage(stream=oversized, filename="large.pdf")
    is_valid, err, _, _, _ = validate_material_file(file, max_size_bytes=100)
    assert is_valid is False
    assert "exceeds maximum allowed limit" in err


# ── Service Layer Upload & Deletion Tests ────────────────────────────────────

def test_save_course_material_path_safety(app, db, sample_course, test_upload_dir):
    """Malicious filenames with path traversal characters must be sanitized safely."""
    with app.app_context():
        malicious_filename = "../../../etc/passwd.pdf"
        file = FileStorage(
            stream=io.BytesIO(b"Safe content"),
            filename=malicious_filename,
            content_type="application/pdf",
        )
        material, msg = save_course_material(
            sample_course["course_id"],
            None,
            file,
            "Safe Document"
        )
        assert material is not None
        assert "passwd.pdf" in material.original_filename
        assert ".." not in material.stored_filename

        # Ensure file exists inside test_upload_dir and NOT outside
        full_path = os.path.join(test_upload_dir, material.stored_filename)
        assert os.path.exists(full_path)
        assert os.path.abspath(full_path).startswith(os.path.abspath(test_upload_dir))


def test_delete_course_material_cleanup(app, db, sample_course, test_upload_dir):
    """Deleting a course material removes both the physical file and the DB record."""
    with app.app_context():
        file = FileStorage(
            stream=io.BytesIO(b"Sample file content to delete"),
            filename="to_delete.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        material, _ = save_course_material(
            sample_course["course_id"],
            None,
            file,
            "Delete Me"
        )
        mat_id = material.id
        stored_file = material.stored_filename
        full_path = os.path.join(test_upload_dir, stored_file)
        assert os.path.exists(full_path)

        success, msg = delete_course_material(mat_id)
        assert success is True
        assert not os.path.exists(full_path)
        assert db.session.get(CourseMaterial, mat_id) is None


# ── Admin Routes Tests ───────────────────────────────────────────────────────

def test_admin_materials_view(logged_in_client, sample_course):
    """Admin can view the course materials management page."""
    resp = logged_in_client.get(f"/admin/lms/courses/{sample_course['course_id']}/materials")
    assert resp.status_code == 200
    assert b"Course Materials" in resp.data
    assert b"Upload Material" in resp.data


def test_admin_upload_course_material(logged_in_client, app, db, sample_course, test_upload_dir):
    """Admin can upload a new course-wide material."""
    data = {
        "display_name": "Project Template",
        "lesson_id": "",
        "file": (io.BytesIO(b"Dummy Excel Data"), "template.xlsx"),
    }
    resp = logged_in_client.post(
        f"/admin/lms/courses/{sample_course['course_id']}/materials/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Material uploaded successfully" in resp.data
    assert b"Project Template" in resp.data

    with app.app_context():
        m = CourseMaterial.query.filter_by(display_name="Project Template").first()
        assert m is not None
        assert m.course_id == sample_course["course_id"]
        assert m.lesson_id is None
        assert os.path.exists(os.path.join(test_upload_dir, m.stored_filename))


def test_admin_upload_lesson_material(logged_in_client, app, db, sample_course, test_upload_dir):
    """Admin can upload a material attached to a specific lesson."""
    data = {
        "display_name": "Lesson 1 Handout",
        "lesson_id": str(sample_course["lesson_id"]),
        "file": (io.BytesIO(b"PDF Handout Data"), "handout.pdf"),
    }
    resp = logged_in_client.post(
        f"/admin/lms/courses/{sample_course['course_id']}/materials/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Lesson 1 Handout" in resp.data

    with app.app_context():
        m = CourseMaterial.query.filter_by(display_name="Lesson 1 Handout").first()
        assert m is not None
        assert m.lesson_id == sample_course["lesson_id"]


def test_admin_delete_material_route(logged_in_client, app, db, sample_course, test_upload_dir):
    """Admin can delete a material via POST route and physical file is removed."""
    with app.app_context():
        file = FileStorage(
            stream=io.BytesIO(b"Data"),
            filename="delete_test.pdf",
            content_type="application/pdf",
        )
        material, _ = save_course_material(
            sample_course["course_id"],
            None,
            file,
            "Admin Delete Test"
        )
        mat_id = material.id
        stored_file = material.stored_filename

    resp = logged_in_client.post(
        f"/admin/lms/materials/{mat_id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"was deleted successfully" in resp.data
    assert not os.path.exists(os.path.join(test_upload_dir, stored_file))


def test_cascade_cleanup_on_lesson_delete(logged_in_client, app, db, sample_course, test_upload_dir):
    """Deleting a lesson removes associated material physical files from disk."""
    with app.app_context():
        file = FileStorage(
            stream=io.BytesIO(b"Handout to clean up"),
            filename="lesson_file.pdf",
            content_type="application/pdf",
        )
        material, _ = save_course_material(
            sample_course["course_id"],
            sample_course["lesson_id"],
            file,
            "Lesson File Cleanup"
        )
        stored_path = os.path.join(test_upload_dir, material.stored_filename)
        assert os.path.exists(stored_path)

    # Delete the lesson via admin route
    resp = logged_in_client.post(
        f"/admin/lms/lessons/{sample_course['lesson_id']}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert not os.path.exists(stored_path)


def test_cascade_cleanup_on_section_delete(logged_in_client, app, db, sample_course, test_upload_dir):
    """Deleting a section removes physical files of materials attached to its lessons."""
    with app.app_context():
        file = FileStorage(
            stream=io.BytesIO(b"Section Handout to clean up"),
            filename="sec_file.pdf",
            content_type="application/pdf",
        )
        material, _ = save_course_material(
            sample_course["course_id"],
            sample_course["lesson_id"],
            file,
            "Section Lesson File"
        )
        stored_path = os.path.join(test_upload_dir, material.stored_filename)
        assert os.path.exists(stored_path)

    # Delete the section via admin route
    resp = logged_in_client.post(
        f"/admin/lms/sections/{sample_course['section_id']}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert not os.path.exists(stored_path)


def test_cascade_cleanup_on_course_delete(logged_in_client, app, db, sample_course, test_upload_dir):
    """Deleting a course removes physical files for both course-level and lesson-level materials."""
    with app.app_context():
        # Course-level material
        mat_course, _ = save_course_material(
            sample_course["course_id"],
            None,
            FileStorage(io.BytesIO(b"Course wide data"), "course_all.pdf", "application/pdf"),
            "Course Wide Resource"
        )
        # Lesson-level material
        mat_lesson, _ = save_course_material(
            sample_course["course_id"],
            sample_course["lesson_id"],
            FileStorage(io.BytesIO(b"Lesson specific data"), "lesson_only.pdf", "application/pdf"),
            "Lesson Resource"
        )
        path_c = os.path.join(test_upload_dir, mat_course.stored_filename)
        path_l = os.path.join(test_upload_dir, mat_lesson.stored_filename)
        assert os.path.exists(path_c)
        assert os.path.exists(path_l)

    # Delete course via admin route
    resp = logged_in_client.post(
        f"/admin/lms/courses/{sample_course['course_id']}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert not os.path.exists(path_c)
    assert not os.path.exists(path_l)


def test_orm_cascade_deletes_physical_files(app, db, sample_course, test_upload_dir):
    """
    Direct SQLAlchemy ORM deletion of a course or lesson triggers after_delete
    event listener and cleans up physical files from disk.
    """
    with app.app_context():
        course = db.session.get(Course, sample_course["course_id"])
        mat, _ = save_course_material(
            course.id,
            None,
            FileStorage(io.BytesIO(b"ORM cascade test data"), "orm_test.pdf", "application/pdf"),
            "ORM Material"
        )
        file_path = os.path.join(test_upload_dir, mat.stored_filename)
        assert os.path.exists(file_path)

        # Delete course directly through ORM session (bypassing admin route)
        db.session.delete(course)
        db.session.commit()

        # Physical file MUST be deleted by the after_delete hook
        assert not os.path.exists(file_path)


def test_failed_db_commit_preserves_physical_file(app, db, sample_course, test_upload_dir, monkeypatch):
    """
    If db.session.commit() fails during delete_course_material, the transaction
    rolls back and the physical file is NOT deleted unexpectedly.
    """
    with app.app_context():
        mat, _ = save_course_material(
            sample_course["course_id"],
            None,
            FileStorage(io.BytesIO(b"Preserved file"), "keep.pdf", "application/pdf"),
            "Preserve Test"
        )
        file_path = os.path.join(test_upload_dir, mat.stored_filename)
        assert os.path.exists(file_path)

        # Simulate database commit failure
        def mock_commit():
            raise Exception("Simulated DB lock failure")

        monkeypatch.setattr(db.session, "commit", mock_commit)

        success, msg = delete_course_material(mat.id)
        assert success is False
        assert "Database error" in msg

        # File must STILL exist on disk because commit failed
        assert os.path.exists(file_path)

        monkeypatch.undo()


# ── Student Access & Download Security Tests ─────────────────────────────────

def test_student_material_visibility_and_download(
    student_client, app, db, sample_course, student_user, test_upload_dir
):
    """Enrolled student can see materials on course and lesson pages and download them."""
    with app.app_context():
        # Enroll student in course
        enrollment = CourseEnrollment(
            user_id=student_user.id,
            course_id=sample_course["course_id"],
            status="active",
        )
        db.session.add(enrollment)

        # Create course-level material
        c_mat, _ = save_course_material(
            sample_course["course_id"],
            None,
            FileStorage(io.BytesIO(b"Course wide PDF"), "course_guide.pdf", "application/pdf"),
            "Course Guide"
        )
        # Create lesson-level material
        l_mat, _ = save_course_material(
            sample_course["course_id"],
            sample_course["lesson_id"],
            FileStorage(io.BytesIO(b"Lesson 1 notes"), "lesson_notes.txt", "text/plain"),
            "Lesson Notes"
        )
        c_mat_id = c_mat.id
        l_mat_id = l_mat.id

    # 1. Check Course Detail page
    resp_detail = student_client.get(f"/lms/courses/{sample_course['slug']}")
    assert resp_detail.status_code == 200
    assert b"Course Guide" in resp_detail.data

    # 2. Check Lesson View page
    resp_lesson = student_client.get(
        f"/lms/courses/{sample_course['slug']}/lessons/{sample_course['lesson_id']}"
    )
    assert resp_lesson.status_code == 200
    assert b"Lesson Notes" in resp_lesson.data

    # 3. Download course material
    resp_dl = student_client.get(f"/lms/materials/{c_mat_id}/download")
    assert resp_dl.status_code == 200
    assert resp_dl.data == b"Course wide PDF"
    assert "attachment; filename=course_guide.pdf" in resp_dl.headers.get("Content-Disposition", "")

    # 4. Download lesson material
    resp_l_dl = student_client.get(f"/lms/materials/{l_mat_id}/download")
    assert resp_l_dl.status_code == 200
    assert resp_l_dl.data == b"Lesson 1 notes"


def test_unenrolled_student_cannot_download(unenrolled_client, app, db, sample_course, test_upload_dir):
    """Unenrolled student downloading material receives 404 (IDOR prevention)."""
    with app.app_context():
        mat, _ = save_course_material(
            sample_course["course_id"],
            None,
            FileStorage(io.BytesIO(b"Secret content"), "secret.pdf", "application/pdf"),
            "Secret PDF"
        )
        mat_id = mat.id

    resp = unenrolled_client.get(f"/lms/materials/{mat_id}/download")
    assert resp.status_code == 404


def test_withdrawn_student_cannot_download(student_client, app, db, sample_course, student_user, test_upload_dir):
    """Student with withdrawn enrollment cannot download material (404)."""
    with app.app_context():
        enrollment = CourseEnrollment(
            user_id=student_user.id,
            course_id=sample_course["course_id"],
            status="withdrawn",
        )
        db.session.add(enrollment)
        mat, _ = save_course_material(
            sample_course["course_id"],
            None,
            FileStorage(io.BytesIO(b"Data"), "guide.pdf", "application/pdf"),
            "Guide PDF"
        )
        mat_id = mat.id

    resp = student_client.get(f"/lms/materials/{mat_id}/download")
    assert resp.status_code == 404


def test_draft_lesson_material_cannot_be_downloaded_by_student(
    student_client, app, db, sample_course, student_user, test_upload_dir
):
    """Student cannot download materials attached to a draft lesson."""
    with app.app_context():
        enrollment = CourseEnrollment(
            user_id=student_user.id,
            course_id=sample_course["course_id"],
            status="active",
        )
        db.session.add(enrollment)
        mat, _ = save_course_material(
            sample_course["course_id"],
            sample_course["draft_lesson_id"],
            FileStorage(io.BytesIO(b"Draft material"), "draft.pdf", "application/pdf"),
            "Draft Material"
        )
        mat_id = mat.id

    resp = student_client.get(f"/lms/materials/{mat_id}/download")
    assert resp.status_code == 404


def test_admin_can_download_any_material(logged_in_client, app, db, sample_course, test_upload_dir):
    """Admin can download materials even without course enrollment."""
    with app.app_context():
        mat, _ = save_course_material(
            sample_course["course_id"],
            sample_course["draft_lesson_id"],
            FileStorage(io.BytesIO(b"Admin Accessible Content"), "draft_guide.pdf", "application/pdf"),
            "Admin Guide"
        )
        mat_id = mat.id

    resp = logged_in_client.get(f"/lms/materials/{mat_id}/download")
    assert resp.status_code == 200
    assert resp.data == b"Admin Accessible Content"
