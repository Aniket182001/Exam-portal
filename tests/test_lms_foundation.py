import pytest
from app.models import User, Course, CourseSection, Lesson
from werkzeug.security import generate_password_hash


@pytest.fixture
def student_user(db, app):
    """Create a student user fixture."""
    with app.app_context():
        user = User(
            username="test_student",
            email="student@example.com",
            password_hash=generate_password_hash("studentpass"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user = User.query.filter_by(username="test_student").first()
        yield user
        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def student_client(client, student_user):
    """A test client logged in as a student."""
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id
    return client


# ── 1. Model Tests ────────────────────────────────────────────────────────────

def test_course_section_lesson_models(db, app):
    """Verify Course, CourseSection, Lesson creation, relations and cascades."""
    with app.app_context():
        course = Course(
            title="Lean Six Sigma Yellow Belt",
            slug="lss-yellow-belt",
            description="Introduction to Lean Six Sigma methodologies.",
            status="published",
            display_order=1,
            is_active=True,
        )
        db.session.add(course)
        db.session.commit()

        section1 = CourseSection(
            course_id=course.id,
            title="Module 1: Fundamentals",
            description="Basic principles of Lean.",
            display_order=1,
        )
        db.session.add(section1)
        db.session.commit()

        lesson1 = Lesson(
            section_id=section1.id,
            title="Lesson 1.1: What is Six Sigma?",
            description="Core concepts and DMAIC overview.",
            display_order=1,
            status="published",
            video_provider="vimeo",
            video_url="https://vimeo.com/123456789",
        )
        lesson2 = Lesson(
            section_id=section1.id,
            title="Lesson 1.2: Waste Identification",
            description="The 8 types of waste (DOWNTIME).",
            display_order=2,
            status="published",
            video_provider="youtube",
            video_url="https://youtube.com/watch?v=abcdef",
        )
        db.session.add_all([lesson1, lesson2])
        db.session.commit()

        # Query and verify
        saved_course = Course.query.filter_by(slug="lss-yellow-belt").first()
        assert saved_course is not None
        assert saved_course.total_sections == 1
        assert saved_course.total_lessons == 2
        assert len(saved_course.sections[0].lessons) == 2
        assert saved_course.sections[0].lessons[0].video_provider == "vimeo"

        # Cascade deletion
        db.session.delete(saved_course)
        db.session.commit()

        assert CourseSection.query.filter_by(id=section1.id).first() is None
        assert Lesson.query.filter_by(id=lesson1.id).first() is None
        assert Lesson.query.filter_by(id=lesson2.id).first() is None


# ── 2. Route & Access Control Tests ──────────────────────────────────────────

def test_unauthenticated_access_redirects_to_login(client):
    """Anonymous users must be redirected to /login for protected portal and LMS routes."""
    # Portal selection requires login
    resp = client.get("/portal")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # Student LMS requires login
    resp = client.get("/lms/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # Admin LMS requires login
    resp = client.get("/admin/lms/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_student_portal_and_lms_access(student_client):
    """Authenticated students can access /portal and /lms, but cannot access /admin/lms."""
    # Portal selection
    resp = student_client.get("/portal")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "AIQM Portal" in html
    assert "Where would you like to go?" in html
    assert "Exam Portal" in html
    assert "LMS" in html

    # Student LMS dashboard
    resp = student_client.get("/lms/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "My Courses" in html
    assert "No Courses Available Yet" in html

    # Admin LMS is forbidden for students
    resp = student_client.get("/admin/lms/")
    assert resp.status_code == 403


def test_admin_lms_access(logged_in_client):
    """Authenticated admins can access /portal and /admin/lms."""
    # Portal selection with admin actions
    resp = logged_in_client.get("/portal")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Exam Administration" in html
    assert "LMS Administration" in html

    # Admin LMS dashboard
    resp = logged_in_client.get("/admin/lms/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "LMS Administration" in html
    assert "Total Courses" in html
    assert "Curriculum Sections" in html
    assert "Total Lessons" in html
    assert "Exam Admin" in html
    assert "LMS Admin" in html


# ── 3. Navigation & Switcher Tests ───────────────────────────────────────────

def test_admin_switcher_on_exam_and_lms_pages(logged_in_client):
    """Both admin exam and admin LMS pages display the segmented switcher."""
    # Exam Admin page
    resp = logged_in_client.get("/admin/exams/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Exam Admin" in html
    assert "LMS Admin" in html

    # LMS Admin page
    resp = logged_in_client.get("/admin/lms/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Exam Admin" in html
    assert "LMS Admin" in html


def test_header_navigation_links(client, logged_in_client):
    """Main navbar contains Exam Portal and LMS links."""
    # Anonymous public home
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Exam Portal" in html
    assert "LMS" in html

    # Logged in admin
    resp = logged_in_client.get("/portal")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Exam Portal" in html
    assert "LMS" in html
    assert "Portal Hub" in html


def test_course_detail_route(logged_in_client, db, app):
    """Viewing a course by slug shows outline."""
    with app.app_context():
        course = Course(
            title="Total Quality Management",
            slug="tqm-cert",
            description="Comprehensive TQM course.",
            status="published",
            is_active=True,
        )
        db.session.add(course)
        db.session.commit()

        section = CourseSection(
            course_id=course.id,
            title="Introduction to TQM",
            display_order=1,
        )
        db.session.add(section)
        db.session.commit()

        lesson = Lesson(
            section_id=section.id,
            title="Deming Principles",
            video_provider="vimeo",
            video_url="https://vimeo.com/98765",
            status="published",
        )
        db.session.add(lesson)
        db.session.commit()

        resp = logged_in_client.get("/lms/courses/tqm-cert")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Total Quality Management" in html
        assert "Introduction to TQM" in html
        assert "Deming Principles" in html
        assert "vimeo" in html

        # Cleanup
        db.session.delete(course)
        db.session.commit()
