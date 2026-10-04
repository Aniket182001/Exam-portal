"""
Comprehensive tests for Phase 4: LMS Progress & Enrollment.

Covers:
- CourseEnrollment and LessonProgress models & constraints
- Centralized progress calculation in lms_service (draft exclusion, zero div safety)
- Idempotent lesson completion
- Last accessed lesson tracking
- Continue learning resolution (Cases 1, 2, 3, 4)
- Enrollment-based student access enforcement (404 on unenrolled/withdrawn)
- Student My Courses dashboard display & progress bar
- Admin enrollment management (list, filter, create, toggle status)
- Data integrity deletion safeguards (courses, sections, lessons with records)
"""
import pytest
from datetime import datetime, timezone
from app.models import User, Course, CourseSection, Lesson, CourseEnrollment, LessonProgress
from app.services.lms_service import (
    calculate_course_progress,
    mark_lesson_complete,
    update_last_accessed_lesson,
    get_continue_learning_lesson,
    enroll_student_in_course,
    update_enrollment_status,
)
from werkzeug.security import generate_password_hash


@pytest.fixture
def student_user(db, app):
    """Authenticated student fixture."""
    with app.app_context():
        user = User(
            username="phase4_student",
            email="phase4_student@example.com",
            password_hash=generate_password_hash("StudentSecret123!"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.app_context():
        u = db.session.get(User, user_id)
        yield u
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()


@pytest.fixture
def student_client(client, student_user):
    """Client authenticated as student_user."""
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id
    return client


@pytest.fixture
def other_student(db, app):
    """Second student fixture for access isolation tests."""
    with app.app_context():
        user = User(
            username="other_student",
            email="other_student@example.com",
            password_hash=generate_password_hash("StudentSecret123!"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.app_context():
        u = db.session.get(User, user_id)
        yield u
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()


@pytest.fixture
def sample_course(db, app):
    """Course with 2 sections: Sec1 has 2 published lessons, Sec2 has 1 draft & 1 published lesson."""
    with app.app_context():
        course = Course(title="Six Sigma Black Belt", slug="ssbb-course", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        cid = course.id

        sec1 = CourseSection(course_id=cid, title="Define Phase", display_order=1)
        sec2 = CourseSection(course_id=cid, title="Measure Phase", display_order=2)
        db.session.add_all([sec1, sec2])
        db.session.commit()

        l1 = Lesson(section_id=sec1.id, title="Project Charter", display_order=1, status="published", video_provider="vimeo", video_url="https://vimeo.com/76979871")
        l2 = Lesson(section_id=sec1.id, title="Process Mapping", display_order=2, status="published", video_provider="youtube", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        l3_draft = Lesson(section_id=sec2.id, title="Draft Gauge R&R", display_order=1, status="draft")
        l4 = Lesson(section_id=sec2.id, title="Capability Analysis", display_order=2, status="published", video_provider="loom", video_url="https://www.loom.com/share/dfb99f6920aa447d92f58e45d9fa0f41")
        db.session.add_all([l1, l2, l3_draft, l4])
        db.session.commit()

        l1_id, l2_id, l3_id, l4_id = l1.id, l2.id, l3_draft.id, l4.id

    yield {
        "course_id": cid,
        "l1_id": l1_id,
        "l2_id": l2_id,
        "l3_draft_id": l3_id,
        "l4_id": l4_id,
    }

    with app.app_context():
        c = db.session.get(Course, cid)
        if c:
            db.session.delete(c)
        db.session.commit()


# ── 1. Model & Service: Enrollment CRUD & Constraints ─────────────────────────

def test_enrollment_creation_and_duplicate_prevention(app, db, student_user, sample_course):
    """Enroll student in course; duplicate enrollment should be safely rejected."""
    with app.app_context():
        cid = sample_course["course_id"]
        enr, msg = enroll_student_in_course(student_user.id, cid)
        assert enr is not None
        assert enr.status == "active"
        assert enr.user_id == student_user.id
        assert enr.course_id == cid

        # Duplicate enrollment
        enr2, msg2 = enroll_student_in_course(student_user.id, cid)
        assert enr2 is None
        assert "already enrolled" in msg2


def test_enrollment_status_transitions(app, db, student_user, sample_course):
    """Admin or service can update enrollment status (active, completed, withdrawn)."""
    with app.app_context():
        cid = sample_course["course_id"]
        enr, _ = enroll_student_in_course(student_user.id, cid)
        enr_id = enr.id

        # Withdraw
        ok, msg = update_enrollment_status(enr_id, "withdrawn")
        assert ok is True
        assert db.session.get(CourseEnrollment, enr_id).status == "withdrawn"

        # Reactivate
        ok, msg = update_enrollment_status(enr_id, "active")
        assert ok is True
        assert db.session.get(CourseEnrollment, enr_id).status == "active"

        # Invalid status rejected
        ok, msg = update_enrollment_status(enr_id, "invalid_status")
        assert ok is False


# ── 2. Progress Calculation & Draft Exclusion ─────────────────────────────────

def test_progress_calculation_baseline_and_draft_exclusion(app, db, student_user, sample_course):
    """Progress calculation only counts published lessons (total=3, excluding draft L3)."""
    with app.app_context():
        cid = sample_course["course_id"]
        enr, _ = enroll_student_in_course(student_user.id, cid)

        # Baseline: 0 of 3 completed = 0%
        prog = calculate_course_progress(enr.id)
        assert prog["total_lessons"] == 3
        assert prog["completed_lessons"] == 0
        assert prog["progress_percent"] == 0
        assert prog["is_completed"] is False

        # Mark L1 complete -> 1 of 3 = 33%
        mark_lesson_complete(enr.id, sample_course["l1_id"])
        prog = calculate_course_progress(enr.id)
        assert prog["completed_lessons"] == 1
        assert prog["progress_percent"] == 33
        assert prog["is_completed"] is False

        # Mark draft L3 complete (e.g. from prior time) -> should NOT count toward published progress
        lp_draft = LessonProgress(enrollment_id=enr.id, lesson_id=sample_course["l3_draft_id"], completed=True)
        db.session.add(lp_draft)
        db.session.commit()

        prog = calculate_course_progress(enr.id)
        assert prog["total_lessons"] == 3
        assert prog["completed_lessons"] == 1  # L3 draft ignored!
        assert prog["progress_percent"] == 33


def test_progress_calculation_100_percent_completion(app, db, student_user, sample_course):
    """Completing all published lessons sets enrollment status to completed and sets completed_at."""
    with app.app_context():
        cid = sample_course["course_id"]
        enr, _ = enroll_student_in_course(student_user.id, cid)

        mark_lesson_complete(enr.id, sample_course["l1_id"])
        mark_lesson_complete(enr.id, sample_course["l2_id"])
        success, msg, prog = mark_lesson_complete(enr.id, sample_course["l4_id"])

        assert success is True
        assert prog["completed_lessons"] == 3
        assert prog["total_lessons"] == 3
        assert prog["progress_percent"] == 100
        assert prog["is_completed"] is True

        refreshed_enr = db.session.get(CourseEnrollment, enr.id)
        assert refreshed_enr.status == "completed"
        assert refreshed_enr.completed_at is not None


def test_progress_zero_division_guard(app, db, student_user):
    """Course with zero published lessons returns 0% without division by zero error."""
    with app.app_context():
        empty_c = Course(title="Empty Course", slug="empty-course-test", status="published", is_active=True)
        db.session.add(empty_c)
        db.session.commit()
        cid = empty_c.id

        enr, _ = enroll_student_in_course(student_user.id, cid)
        prog = calculate_course_progress(enr.id)

        assert prog["total_lessons"] == 0
        assert prog["completed_lessons"] == 0
        assert prog["progress_percent"] == 0
        assert prog["is_completed"] is False

        db.session.delete(empty_c)
        db.session.commit()


# ── 3. Idempotent Lesson Completion ───────────────────────────────────────────

def test_idempotent_lesson_completion(app, db, student_user, sample_course):
    """Submitting 'Mark as Complete' repeatedly does not duplicate records or fail."""
    with app.app_context():
        cid = sample_course["course_id"]
        enr, _ = enroll_student_in_course(student_user.id, cid)
        l1_id = sample_course["l1_id"]

        # First completion
        s1, m1, p1 = mark_lesson_complete(enr.id, l1_id)
        assert s1 is True
        assert p1["completed_lessons"] == 1

        # Second completion (idempotent)
        s2, m2, p2 = mark_lesson_complete(enr.id, l1_id)
        assert s2 is True
        assert "already marked as complete" in m2
        assert p2["completed_lessons"] == 1

        # Exactly 1 record in database
        count = LessonProgress.query.filter_by(enrollment_id=enr.id, lesson_id=l1_id).count()
        assert count == 1


# ── 4. Last Accessed & Continue Learning Resolution ───────────────────────────

def test_continue_learning_resolution(app, db, student_user, sample_course):
    """
    Test 4 continue learning cases:
    Case 1: Last accessed incomplete lesson -> resumes there
    Case 2: Last accessed lesson is completed -> resumes next incomplete lesson
    Case 3: No last accessed lesson -> starts at first published lesson
    Case 4: All lessons complete -> returns final published lesson
    """
    with app.app_context():
        cid = sample_course["course_id"]
        enr, _ = enroll_student_in_course(student_user.id, cid)
        l1_id = sample_course["l1_id"]
        l2_id = sample_course["l2_id"]
        l4_id = sample_course["l4_id"]

        # Case 3: Brand new enrollment -> First published lesson (L1)
        res = get_continue_learning_lesson(enr)
        assert res.id == l1_id

        # Case 1: Last accessed L2 (incomplete) -> Resumes L2
        update_last_accessed_lesson(enr.id, l2_id)
        res = get_continue_learning_lesson(enr)
        assert res.id == l2_id

        # Case 2: L2 is completed -> Advances to next incomplete published lesson (L4)
        mark_lesson_complete(enr.id, l2_id)
        res = get_continue_learning_lesson(enr)
        assert res.id == l4_id

        # Case 4: Complete remaining lessons (L1 and L4) -> Returns last published lesson (L4)
        mark_lesson_complete(enr.id, l1_id)
        mark_lesson_complete(enr.id, l4_id)
        res = get_continue_learning_lesson(enr)
        assert res.id == l4_id


# ── 5. Enrollment-based Access Control ────────────────────────────────────────

def test_student_enrollment_access_enforcement(client, student_user, other_student, sample_course, app, db):
    """
    - Enrolled student gets 200 on course detail & lesson.
    - Unenrolled student gets 404 (no leak).
    - Withdrawn student gets 404.
    """
    cid = sample_course["course_id"]
    l1_id = sample_course["l1_id"]

    with app.app_context():
        # Enroll only student_user
        enr, _ = enroll_student_in_course(student_user.id, cid)
        enr_id = enr.id

    # 1. Enrolled student: 200 OK
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id

    resp = client.get("/lms/courses/ssbb-course")
    assert resp.status_code == 200
    assert "Six Sigma Black Belt" in resp.get_data(as_text=True)

    resp = client.get(f"/lms/courses/ssbb-course/lessons/{l1_id}")
    assert resp.status_code == 200

    # 2. Unenrolled student (other_student): 404 NOT FOUND
    with client.session_transaction() as sess:
        sess["user_id"] = other_student.id

    resp = client.get("/lms/courses/ssbb-course")
    assert resp.status_code == 404

    resp = client.get(f"/lms/courses/ssbb-course/lessons/{l1_id}")
    assert resp.status_code == 404

    # 3. Withdrawn student: 404 NOT FOUND
    with app.app_context():
        update_enrollment_status(enr_id, "withdrawn")

    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id

    resp = client.get("/lms/courses/ssbb-course")
    assert resp.status_code == 404

    resp = client.get(f"/lms/courses/ssbb-course/lessons/{l1_id}")
    assert resp.status_code == 404


# ── 6. Student Lesson Player Mark Complete HTTP Route ─────────────────────────

def test_student_mark_lesson_complete_route(student_client, student_user, sample_course, app, db):
    """POST /courses/<slug>/lessons/<id>/complete marks lesson complete and redirects."""
    cid = sample_course["course_id"]
    l1_id = sample_course["l1_id"]

    with app.app_context():
        enroll_student_in_course(student_user.id, cid)

    resp = student_client.post(
        f"/lms/courses/ssbb-course/lessons/{l1_id}/complete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "marked as complete" in html
    assert "Completed" in html


# ── 7. Admin Enrollment Management Interface ──────────────────────────────────

def test_admin_enrollment_management(logged_in_client, student_user, sample_course, app, db):
    """Admin can list enrollments, create an enrollment, and update status."""
    cid = sample_course["course_id"]

    # 1. Admin creates enrollment via POST
    resp = logged_in_client.post(
        "/admin/lms/enrollments/create",
        data={"user_id": student_user.id, "course_id": cid},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Enrolled" in resp.get_data(as_text=True)

    with app.app_context():
        enr = CourseEnrollment.query.filter_by(user_id=student_user.id, course_id=cid).first()
        assert enr is not None
        assert enr.status == "active"
        enr_id = enr.id

    # 2. Admin views enrollments list
    resp = logged_in_client.get("/admin/lms/enrollments")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Student Course Enrollments" in html
    assert student_user.username in html
    assert "Six Sigma Black Belt" in html

    # 3. Admin withdraws enrollment
    resp = logged_in_client.post(
        f"/admin/lms/enrollments/{enr_id}/status",
        data={"status": "withdrawn"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(CourseEnrollment, enr_id).status == "withdrawn"

    # 4. Filter by course
    resp = logged_in_client.get(f"/admin/lms/enrollments?course_id={cid}&status=withdrawn")
    assert resp.status_code == 200
    assert student_user.username in resp.get_data(as_text=True)


# ── 8. Data Integrity Deletion Safeguards ─────────────────────────────────────

def test_data_integrity_deletion_safeguards(logged_in_client, student_user, sample_course, app, db):
    """
    - Deleting course with active enrollments is blocked.
    - Deleting section/lesson with student progress records is blocked.
    """
    cid = sample_course["course_id"]
    l1_id = sample_course["l1_id"]

    with app.app_context():
        enr, _ = enroll_student_in_course(student_user.id, cid)
        mark_lesson_complete(enr.id, l1_id)
        lesson = db.session.get(Lesson, l1_id)
        sec_id = lesson.section_id

    # 1. Attempt to delete course with enrollments -> blocked
    resp = logged_in_client.post(f"/admin/lms/courses/{cid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Cannot delete course" in resp.get_data(as_text=True)

    # 2. Attempt to delete lesson with progress records -> blocked
    resp = logged_in_client.post(f"/admin/lms/lessons/{l1_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Cannot delete lesson" in resp.get_data(as_text=True)

    # 3. Attempt to delete section containing lesson with progress -> blocked
    resp = logged_in_client.post(f"/admin/lms/sections/{sec_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Cannot delete section" in resp.get_data(as_text=True)
