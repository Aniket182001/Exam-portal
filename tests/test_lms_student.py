import pytest
from app.models import User, Course, CourseSection, Lesson, CourseEnrollment
from werkzeug.security import generate_password_hash


@pytest.fixture
def student_user(db, app):
    """Fixture for a standard authenticated student user."""
    with app.app_context():
        user = User(
            username="student_tester",
            email="student.tester@example.com",
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
    """Flask test client authenticated as a student."""
    with client.session_transaction() as sess:
        sess["user_id"] = student_user.id
    return client


# ── 1. Dashboard Tests ────────────────────────────────────────────────────────

def test_student_dashboard_requires_login(client):
    """Unauthenticated users must be redirected to login."""
    resp = client.get("/lms/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_student_dashboard_displays_only_published_active_courses(student_client, db, app):
    """Dashboard only shows active published courses, hiding drafts and archives."""
    with app.app_context():
        c_pub = Course(title="Published LSS Course", slug="pub-lss", status="published", is_active=True, display_order=1)
        c_draft = Course(title="Draft ISO Course", slug="draft-iso", status="draft", is_active=True, display_order=2)
        c_arch = Course(title="Archived Six Sigma", slug="arch-ss", status="archived", is_active=False, display_order=3)
        db.session.add_all([c_pub, c_draft, c_arch])
        db.session.commit()
        c_pub_id = c_pub.id
        c_draft_id = c_draft.id
        c_arch_id = c_arch.id

    resp = student_client.get("/lms/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Published LSS Course" in html
    assert "Draft ISO Course" not in html
    assert "Archived Six Sigma" not in html
    assert "My Courses" in html

    with app.app_context():
        for cid in [c_pub_id, c_draft_id, c_arch_id]:
            c = db.session.get(Course, cid)
            if c:
                db.session.delete(c)
        db.session.commit()


# ── 2. Course Detail Tests ────────────────────────────────────────────────────

def test_student_course_detail_published(student_client, student_user, db, app):
    """Student can view published course outline with published lessons only."""
    with app.app_context():
        course = Course(title="Quality Management 101", slug="qm-101", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        course_id = course.id

        enr = CourseEnrollment(user_id=student_user.id, course_id=course_id, status="active")
        db.session.add(enr)
        db.session.commit()

        sec1 = CourseSection(course_id=course_id, title="Module 1: Quality Basics", display_order=1)
        db.session.add(sec1)
        db.session.commit()
        sec1_id = sec1.id

        l1 = Lesson(section_id=sec1_id, title="Lesson 1: Intro", display_order=1, status="published", video_provider="vimeo", video_url="https://vimeo.com/76979871")
        l2_draft = Lesson(section_id=sec1_id, title="Lesson 2: Secret Draft", display_order=2, status="draft")
        db.session.add_all([l1, l2_draft])
        db.session.commit()

    resp = student_client.get("/lms/courses/qm-101")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Quality Management 101" in html
    assert "Module 1: Quality Basics" in html
    assert "Lesson 1: Intro" in html
    assert "Lesson 2: Secret Draft" not in html
    assert "Start Learning" in html

    with app.app_context():
        db.session.delete(db.session.get(Course, course_id))
        db.session.commit()


def test_student_course_detail_draft_returns_404(student_client, db, app):
    """Accessing an unpublished course returns 404 for student."""
    with app.app_context():
        course = Course(title="Hidden Draft Course", slug="hidden-draft", status="draft", is_active=True)
        db.session.add(course)
        db.session.commit()
        course_id = course.id

    resp = student_client.get("/lms/courses/hidden-draft")
    assert resp.status_code == 404

    with app.app_context():
        db.session.delete(db.session.get(Course, course_id))
        db.session.commit()


def test_student_course_empty_state_when_no_published_lessons(student_client, student_user, db, app):
    """Course with zero published lessons shows a helpful empty state."""
    with app.app_context():
        course = Course(title="Empty Shell Course", slug="empty-shell", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        course_id = course.id

        enr = CourseEnrollment(user_id=student_user.id, course_id=course_id, status="active")
        db.session.add(enr)
        db.session.commit()

    resp = student_client.get("/lms/courses/empty-shell")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "No Published Lessons Yet" in html
    assert "This course does not have any published lessons yet." in html

    with app.app_context():
        db.session.delete(db.session.get(Course, course_id))
        db.session.commit()


# ── 3. Lesson Player & Hierarchical Navigation Tests ─────────────────────────

def test_lesson_player_and_navigation(student_client, student_user, db, app):
    """
    Test lesson player across sections:
    - Section 1: Lesson 1, Lesson 2
    - Section 2: Lesson 3 (draft - skipped), Lesson 4
    Navigation flow: Lesson 1 -> Lesson 2 -> Lesson 4 (Lesson 3 is skipped).
    """
    with app.app_context():
        course = Course(title="Nav Course", slug="nav-course", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        cid = course.id

        enr = CourseEnrollment(user_id=student_user.id, course_id=cid, status="active")
        db.session.add(enr)
        db.session.commit()

        sec1 = CourseSection(course_id=cid, title="Section 1", display_order=1)
        sec2 = CourseSection(course_id=cid, title="Section 2", display_order=2)
        db.session.add_all([sec1, sec2])
        db.session.commit()

        l1 = Lesson(section_id=sec1.id, title="L1", display_order=1, status="published", video_provider="vimeo", video_url="https://vimeo.com/76979871")
        l2 = Lesson(section_id=sec1.id, title="L2", display_order=2, status="published", video_provider="youtube", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        l3_draft = Lesson(section_id=sec2.id, title="L3 Draft", display_order=1, status="draft", video_provider="youtube", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        l4 = Lesson(section_id=sec2.id, title="L4", display_order=2, status="published", video_provider="loom", video_url="https://www.loom.com/share/dfb99f6920aa447d92f58e45d9fa0f41")
        db.session.add_all([l1, l2, l3_draft, l4])
        db.session.commit()

        l1_id, l2_id, l3_id, l4_id = l1.id, l2.id, l3_draft.id, l4.id

    # 1. Lesson 1 (First lesson: Previous disabled, Next is L2)
    resp = student_client.get(f"/lms/courses/nav-course/lessons/{l1_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "L1" in html
    assert "player.vimeo.com/video/76979871" in html
    assert "Previous Lesson" in html
    assert f"/lms/courses/nav-course/lessons/{l2_id}" in html  # Next points to L2

    # 2. Lesson 2 (Next crosses section boundary to L4, skipping draft L3)
    resp = student_client.get(f"/lms/courses/nav-course/lessons/{l2_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "L2" in html
    assert "www.youtube.com/embed/dQw4w9WgXcQ" in html
    assert f"/lms/courses/nav-course/lessons/{l1_id}" in html  # Previous is L1
    assert f"/lms/courses/nav-course/lessons/{l4_id}" in html  # Next is L4!
    assert f"/lms/courses/nav-course/lessons/{l3_id}" not in html  # Draft not in navigation

    # 3. Direct access to draft L3 returns 404
    resp = student_client.get(f"/lms/courses/nav-course/lessons/{l3_id}")
    assert resp.status_code == 404

    # 4. Shortcut /lessons/<id> for L4 redirects to canonical URL
    resp = student_client.get(f"/lms/lessons/{l4_id}", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "L4" in html
    assert "www.loom.com/embed/dfb99f6920aa447d92f58e45d9fa0f41" in html
    assert "Next Lesson" in html  # Final lesson: Next disabled

    # 5. Shortcut /lessons/<draft_id> returns 404
    resp = student_client.get(f"/lms/lessons/{l3_id}")
    assert resp.status_code == 404

    # 6. Mismatched course slug returns 404
    resp = student_client.get(f"/lms/courses/other-course/lessons/{l1_id}")
    assert resp.status_code == 404

    with app.app_context():
        db.session.delete(db.session.get(Course, cid))
        db.session.commit()


# ── 4. Video Provider Embed Tests ─────────────────────────────────────────────

def test_video_provider_rendering(student_client, student_user, db, app):
    """Verify correct video embed rendering for all supported providers."""
    with app.app_context():
        course = Course(title="Video Showcase", slug="video-showcase", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        cid = course.id

        enr = CourseEnrollment(user_id=student_user.id, course_id=cid, status="active")
        db.session.add(enr)
        db.session.commit()

        sec = CourseSection(course_id=cid, title="Videos", display_order=1)
        db.session.add(sec)
        db.session.commit()

        # Google Drive lesson
        l_drive = Lesson(
            section_id=sec.id,
            title="Drive Video",
            display_order=1,
            status="published",
            video_provider="drive",
            video_url="https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view",
        )
        # Custom HTML5 mp4 lesson
        l_mp4 = Lesson(
            section_id=sec.id,
            title="Custom MP4",
            display_order=2,
            status="published",
            video_provider="custom",
            video_url="https://example.com/media/lecture.mp4",
        )
        # Empty video lesson
        l_empty = Lesson(
            section_id=sec.id,
            title="Reading Lesson",
            display_order=3,
            status="published",
            video_provider=None,
            video_url="",
        )
        # Invalid URL lesson
        l_invalid = Lesson(
            section_id=sec.id,
            title="Broken Video",
            display_order=4,
            status="published",
            video_provider="vimeo",
            video_url="https://not-vimeo.com/bad",
        )
        db.session.add_all([l_drive, l_mp4, l_empty, l_invalid])
        db.session.commit()

        drive_id = l_drive.id
        mp4_id = l_mp4.id
        empty_id = l_empty.id
        invalid_id = l_invalid.id

    # Test Google Drive
    resp = student_client.get(f"/lms/courses/video-showcase/lessons/{drive_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/preview" in html
    assert "This video is hosted on Google Drive" in html

    # Test Custom MP4
    resp = student_client.get(f"/lms/courses/video-showcase/lessons/{mp4_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<video" in html
    assert "https://example.com/media/lecture.mp4" in html

    # Test Empty Video
    resp = student_client.get(f"/lms/courses/video-showcase/lessons/{empty_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "No Video Attached" in html

    # Test Invalid Video
    resp = student_client.get(f"/lms/courses/video-showcase/lessons/{invalid_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Video Unavailable" in html

    with app.app_context():
        db.session.delete(db.session.get(Course, cid))
        db.session.commit()


# ── 5. Security & Student Isolation Tests ─────────────────────────────────────

def test_student_cannot_access_admin_lms(student_client):
    """Student is blocked with 403 on all admin LMS routes."""
    assert student_client.get("/admin/lms/").status_code == 403
    assert student_client.get("/admin/lms/courses/create").status_code == 403
    assert student_client.post("/admin/lms/courses/create", data={"title": "Hacked"}).status_code == 403


def test_video_embed_rejects_xss_injection(student_client, student_user, db, app):
    """Malicious script or raw HTML injection in video_url is prevented."""
    with app.app_context():
        course = Course(title="XSS Test", slug="xss-test", status="published", is_active=True)
        db.session.add(course)
        db.session.commit()
        cid = course.id

        enr = CourseEnrollment(user_id=student_user.id, course_id=cid, status="active")
        db.session.add(enr)
        db.session.commit()

        sec = CourseSection(course_id=cid, title="Security Sec", display_order=1)
        db.session.add(sec)
        db.session.commit()

        malicious_lesson = Lesson(
            section_id=sec.id,
            title="Malicious Lesson",
            display_order=1,
            status="published",
            video_provider="custom",
            video_url="https://bad.com/<script>alert('pwned')</script>",
        )
        db.session.add(malicious_lesson)
        db.session.commit()
        lid = malicious_lesson.id

    resp = student_client.get(f"/lms/courses/xss-test/lessons/{lid}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<script>alert('pwned')</script>" not in html
    assert "Video Unavailable" in html

    with app.app_context():
        db.session.delete(db.session.get(Course, cid))
        db.session.commit()
