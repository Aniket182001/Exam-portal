import pytest
from app.models import User, Course, CourseSection, Lesson
from app.services.lms_service import validate_video_url, generate_unique_slug
from werkzeug.security import generate_password_hash


@pytest.fixture
def student_user(db, app):
    """Create a student user fixture."""
    with app.app_context():
        user = User(
            username="student_user_p2",
            email="student_p2@example.com",
            password_hash=generate_password_hash("password123"),
            role="student",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user = User.query.filter_by(username="student_user_p2").first()
        yield user
        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def student_client(client, student_user):
    """A test client logged in as a student."""
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id
    return client


# ── 1. Video URL Validation Unit Tests ─────────────────────────────────────────

def test_validate_video_url_vimeo():
    """Vimeo URLs must be valid vimeo links."""
    # Valid
    valid, err, url = validate_video_url("vimeo", "https://vimeo.com/123456789")
    assert valid is True
    assert err is None
    assert url == "https://vimeo.com/123456789"

    valid, err, _ = validate_video_url("vimeo", "https://player.vimeo.com/video/987654321")
    assert valid is True

    # Invalid domain
    valid, err, _ = validate_video_url("vimeo", "https://youtube.com/watch?v=123")
    assert valid is False
    assert "Vimeo" in err

    # Blank URL is permitted (text only)
    valid, err, url = validate_video_url("vimeo", "")
    assert valid is True
    assert url is None


def test_validate_video_url_youtube():
    """YouTube URLs must be valid youtube links."""
    valid, err, url = validate_video_url("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert valid is True

    valid, err, url = validate_video_url("youtube", "https://youtu.be/dQw4w9WgXcQ")
    assert valid is True

    valid, err, _ = validate_video_url("youtube", "https://vimeo.com/123456")
    assert valid is False
    assert "YouTube" in err


def test_validate_video_url_google_drive():
    """Google Drive file links must contain drive.google.com or docs.google.com."""
    valid, err, url = validate_video_url("drive", "https://drive.google.com/file/d/1a2b3c4d5e/view?usp=sharing")
    assert valid is True

    valid, err, _ = validate_video_url("drive", "https://dropbox.com/s/123/file.mp4")
    assert valid is False
    assert "Google Drive" in err


def test_validate_video_url_loom():
    """Loom URLs must contain loom.com."""
    valid, err, url = validate_video_url("loom", "https://www.loom.com/share/abc123xyz")
    assert valid is True

    valid, err, _ = validate_video_url("loom", "https://vimeo.com/123456")
    assert valid is False
    assert "Loom" in err


def test_validate_video_url_custom_and_xss_protection():
    """Custom URLs must be valid HTTP/S and strictly reject raw HTML or script tags."""
    # Valid custom
    valid, err, url = validate_video_url("custom", "https://cdn.example.com/videos/lecture1.mp4")
    assert valid is True
    assert url == "https://cdn.example.com/videos/lecture1.mp4"

    # HTML / Script injection attempt rejected
    valid, err, _ = validate_video_url("custom", '<iframe src="https://evil.com"></iframe>')
    assert valid is False
    assert "HTML tags" in err or "valid URL" in err

    valid, err, _ = validate_video_url("custom", "javascript:alert(1)")
    assert valid is False


# ── 2. Course CRUD & Status Tests ─────────────────────────────────────────────

def test_admin_create_course(logged_in_client, db, app):
    """Admin can create a new course."""
    resp = logged_in_client.post(
        "/admin/lms/courses/create",
        data={
            "title": "Lean Six Sigma Black Belt",
            "slug": "lss-black-belt",
            "description": "Advanced statistical and quality tools.",
            "status": "draft",
            "display_order": "1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Lean Six Sigma Black Belt" in html

    with app.app_context():
        course = Course.query.filter_by(slug="lss-black-belt").first()
        assert course is not None
        assert course.title == "Lean Six Sigma Black Belt"
        assert course.status == "draft"

        # Cleanup
        db.session.delete(course)
        db.session.commit()


def test_admin_slug_collision_resolution(db, app):
    """Creating courses with identical titles assigns distinct unique slugs."""
    with app.app_context():
        slug1 = generate_unique_slug("Quality Management")
        course1 = Course(title="Quality Management", slug=slug1, status="draft")
        db.session.add(course1)
        db.session.commit()

        slug2 = generate_unique_slug("Quality Management")
        assert slug1 == "quality-management"
        assert slug2 == "quality-management-2"

        db.session.delete(course1)
        db.session.commit()


def test_admin_edit_course(logged_in_client, db, app):
    """Admin can edit an existing course."""
    with app.app_context():
        course = Course(title="Initial Title", slug="initial-title", status="draft")
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    resp = logged_in_client.post(
        f"/admin/lms/courses/{course_id}/edit",
        data={
            "title": "Updated Title",
            "slug": "updated-title",
            "description": "Updated description.",
            "status": "published",
            "display_order": "5",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        updated = db.session.get(Course, course_id)
        assert updated.title == "Updated Title"
        assert updated.slug == "updated-title"
        assert updated.status == "published"
        assert updated.display_order == 5

        db.session.delete(updated)
        db.session.commit()


def test_admin_course_lifecycle_status_and_archive(logged_in_client, db, app):
    """Admin can update course status and archive a course."""
    with app.app_context():
        course = Course(title="Lifecycle Test", slug="lifecycle-test", status="draft")
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    # Publish via status route
    resp = logged_in_client.post(
        f"/admin/lms/courses/{course_id}/status",
        data={"status": "published"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Course, course_id).status == "published"
        assert db.session.get(Course, course_id).is_active is True

    # Archive via archive route
    resp = logged_in_client.post(
        f"/admin/lms/courses/{course_id}/archive",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        c = db.session.get(Course, course_id)
        assert c.status == "archived"
        assert c.is_active is False

        db.session.delete(c)
        db.session.commit()


def test_admin_course_reorder(logged_in_client, db, app):
    """Admin can reorder courses in the dashboard."""
    with app.app_context():
        c1 = Course(title="Course A", slug="course-a", display_order=1)
        c2 = Course(title="Course B", slug="course-b", display_order=2)
        db.session.add_all([c1, c2])
        db.session.commit()
        c1_id = c1.id
        c2_id = c2.id

    # Move Course B up
    resp = logged_in_client.post(
        f"/admin/lms/courses/{c2_id}/reorder",
        data={"direction": "up"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        rc2 = db.session.get(Course, c2_id)
        assert rc2.display_order == 1

        rc1 = db.session.get(Course, c1_id)
        if rc1:
            db.session.delete(rc1)
        if rc2:
            db.session.delete(rc2)
        db.session.commit()


# ── 3. Section Management Tests ───────────────────────────────────────────────

def test_admin_section_crud_and_reorder(logged_in_client, db, app):
    """Admin can create, edit, reorder, and delete sections."""
    with app.app_context():
        course = Course(title="Section Test Course", slug="sec-test", status="draft")
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    # 1. Create Section 1
    resp = logged_in_client.post(
        f"/admin/lms/courses/{course_id}/sections/create",
        data={"title": "Section 1 — Introduction", "description": "Intro desc", "display_order": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Section 1 — Introduction" in resp.get_data(as_text=True)

    # 2. Create Section 2
    resp = logged_in_client.post(
        f"/admin/lms/courses/{course_id}/sections/create",
        data={"title": "Section 2 — Advanced", "description": "Adv desc", "display_order": "2"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        sec1 = CourseSection.query.filter_by(title="Section 1 — Introduction").first()
        sec2 = CourseSection.query.filter_by(title="Section 2 — Advanced").first()
        assert sec1.course_id == course_id
        assert sec2.course_id == course_id
        sec1_id, sec2_id = sec1.id, sec2.id

    # 3. Edit Section 1
    resp = logged_in_client.post(
        f"/admin/lms/sections/{sec1_id}/edit",
        data={"title": "Section 1 — Overview", "description": "Updated intro", "display_order": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Section 1 — Overview" in resp.get_data(as_text=True)

    # 4. Reorder Section 2 up
    resp = logged_in_client.post(
        f"/admin/lms/sections/{sec2_id}/reorder",
        data={"direction": "up"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(CourseSection, sec2_id).display_order == 1
        assert db.session.get(CourseSection, sec1_id).display_order == 2

    # 5. Delete Section 1
    resp = logged_in_client.post(
        f"/admin/lms/sections/{sec1_id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(CourseSection, sec1_id) is None
        # Clean up course
        db.session.delete(db.session.get(Course, course_id))
        db.session.commit()


# ── 4. Lesson Management & Video Source Tests ─────────────────────────────────

def test_admin_lesson_crud_reorder_and_video(logged_in_client, db, app):
    """Admin can create, edit, move, reorder, and delete lessons with video sources."""
    with app.app_context():
        course = Course(title="Lesson Test Course", slug="lesson-test", status="draft")
        db.session.add(course)
        db.session.commit()
        section = CourseSection(course_id=course.id, title="Main Section", display_order=1)
        db.session.add(section)
        db.session.commit()
        course_id, section_id = course.id, section.id

    # 1. Create Lesson with Vimeo URL
    resp = logged_in_client.post(
        f"/admin/lms/sections/{section_id}/lessons/create",
        data={
            "title": "Lesson 1: Introduction",
            "description": "Vimeo lecture",
            "status": "published",
            "display_order": "1",
            "video_provider": "vimeo",
            "video_url": "https://vimeo.com/123456789",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Lesson 1: Introduction" in resp.get_data(as_text=True)

    # 2. Create Lesson with YouTube URL
    resp = logged_in_client.post(
        f"/admin/lms/sections/{section_id}/lessons/create",
        data={
            "title": "Lesson 2: Practice",
            "description": "YouTube practice",
            "status": "draft",
            "display_order": "2",
            "video_provider": "youtube",
            "video_url": "https://www.youtube.com/watch?v=abcdef12345",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # 3. Create Lesson with invalid video URL (rejected)
    resp = logged_in_client.post(
        f"/admin/lms/sections/{section_id}/lessons/create",
        data={
            "title": "Invalid Video Lesson",
            "video_provider": "vimeo",
            "video_url": "https://invalid-site.com/video",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Vimeo" in resp.get_data(as_text=True)  # validation error displayed

    with app.app_context():
        l1 = Lesson.query.filter_by(title="Lesson 1: Introduction").first()
        l2 = Lesson.query.filter_by(title="Lesson 2: Practice").first()
        assert l1 is not None
        assert l1.video_provider == "vimeo"
        assert l1.video_url == "https://vimeo.com/123456789"
        assert l2 is not None
        assert l2.video_provider == "youtube"
        l1_id, l2_id = l1.id, l2.id

    # 4. Toggle Lesson Status
    resp = logged_in_client.post(
        f"/admin/lms/lessons/{l2_id}/status",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Lesson, l2_id).status == "published"

    # 5. Reorder Lesson 2 up
    resp = logged_in_client.post(
        f"/admin/lms/lessons/{l2_id}/reorder",
        data={"direction": "up"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Lesson, l2_id).display_order == 1
        assert db.session.get(Lesson, l1_id).display_order == 2

    # 6. Delete Lesson
    resp = logged_in_client.post(
        f"/admin/lms/lessons/{l1_id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Lesson, l1_id) is None
        db.session.delete(db.session.get(Course, course_id))
        db.session.commit()


# ── 5. Security & Student Isolation Tests ─────────────────────────────────────

def test_non_admin_cannot_manage_lms(student_client, db, app):
    """Students cannot access course/section/lesson management routes."""
    with app.app_context():
        course = Course(title="Secure Course", slug="secure-course", status="draft")
        db.session.add(course)
        db.session.commit()
        cid = course.id

    # Cannot view admin dashboard
    assert student_client.get("/admin/lms/").status_code == 403

    # Cannot create course
    assert student_client.post("/admin/lms/courses/create", data={"title": "Hacked"}).status_code == 403

    # Cannot edit course
    assert student_client.post(f"/admin/lms/courses/{cid}/edit", data={"title": "Hacked"}).status_code == 403

    # Cannot delete course
    assert student_client.post(f"/admin/lms/courses/{cid}/delete").status_code == 403

    with app.app_context():
        db.session.delete(db.session.get(Course, cid))
        db.session.commit()


def test_student_catalog_hides_draft_and_archived_courses(student_client, db, app):
    """Draft and archived courses are hidden from the student catalog."""
    with app.app_context():
        c_pub = Course(title="Public Course", slug="pub-course", status="published", is_active=True)
        c_draft = Course(title="Draft Course", slug="draft-course", status="draft", is_active=True)
        c_arch = Course(title="Archived Course", slug="arch-course", status="archived", is_active=False)
        db.session.add_all([c_pub, c_draft, c_arch])
        db.session.commit()

    resp = student_client.get("/lms/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Public Course" in html
    assert "Draft Course" not in html
    assert "Archived Course" not in html

    # Student cannot view detail of draft course
    resp = student_client.get("/lms/courses/draft-course")
    assert resp.status_code == 404

    with app.app_context():
        db.session.delete(Course.query.filter_by(slug="pub-course").first())
        db.session.delete(Course.query.filter_by(slug="draft-course").first())
        db.session.delete(Course.query.filter_by(slug="arch-course").first())
        db.session.commit()
