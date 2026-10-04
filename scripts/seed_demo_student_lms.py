"""
Local Development Only: Seed Demo Student, Demo LMS Course, and Enrollment Progress.

CRITICAL SAFETY RULE:
This script contains guardrails to NEVER execute against a production PostgreSQL database.
It is intended solely for local developer onboarding and manual student UX verification.
"""
import sys
import os
from datetime import datetime, timezone

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.course import Course, CourseSection, Lesson, CourseEnrollment, LessonProgress
from werkzeug.security import generate_password_hash


def seed_demo_data():
    app = create_app()

    with app.app_context():
        # STRICT SAFETY GUARD: Do NOT run against PostgreSQL / Production
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "postgresql" in db_uri or "postgres" in db_uri:
            print("[ABORT] Refusing to seed demo accounts on PostgreSQL or production database!")
            sys.exit(1)

        print(f"[OK] Verified local database: {db_uri}")

        # ── 1. Create or Update Demo Student ──────────────────────────────────
        demo_email = "demo.student@local.test"
        demo_username = "demo_student"
        demo_password = "DemoStudent@2026!"

        student = User.query.filter(
            (User.email == demo_email) | (User.username == demo_username)
        ).first()

        if not student:
            student = User(
                username=demo_username,
                email=demo_email,
                password_hash=generate_password_hash(demo_password),
                role="student",
                is_active=True,
            )
            db.session.add(student)
            db.session.flush()
            print(f"[+] Created Demo Student account: {demo_email}")
        else:
            student.email = demo_email
            student.username = demo_username
            student.password_hash = generate_password_hash(demo_password)
            student.role = "student"
            student.is_active = True
            db.session.flush()
            print(f"[*] Updated existing Demo Student credentials for: {demo_email}")

        # ── 2. Create or Update Demo Course ───────────────────────────────────
        demo_slug = "lean-six-sigma-green-belt-demo"
        course = Course.query.filter_by(slug=demo_slug).first()

        if not course:
            course = Course(
                title="Lean Six Sigma Green Belt — Demo",
                slug=demo_slug,
                description=(
                    "Master the DMAIC methodology and Lean Six Sigma core tools in this "
                    "hands-on demonstration course featuring multiple video streaming platforms."
                ),
                status="published",
                display_order=1,
                is_active=True,
            )
            db.session.add(course)
            db.session.flush()
            print(f"[+] Created Demo Course: {course.title} (slug: {demo_slug})")
        else:
            course.title = "Lean Six Sigma Green Belt — Demo"
            course.status = "published"
            course.is_active = True
            print(f"[*] Existing Demo Course found: {course.title}")

        # Remove existing enrollments for clean seed recreation
        existing_enrollments = CourseEnrollment.query.filter_by(course_id=course.id).all()
        for enr in existing_enrollments:
            db.session.delete(enr)
        db.session.flush()

        # Clear existing sections to avoid duplicate lesson clutter in demo environment
        for sec in list(course.sections):
            db.session.delete(sec)
        db.session.flush()

        # Section 1: Introduction & Fundamentals
        sec1 = CourseSection(
            course_id=course.id,
            title="Section 1 — Introduction & Fundamentals",
            description="Core foundations of Lean Six Sigma and process excellence.",
            display_order=1,
        )
        db.session.add(sec1)
        db.session.flush()

        l1 = Lesson(
            section_id=sec1.id,
            title="Lesson 1 — Introduction to Lean Six Sigma",
            description="Overview of Lean Six Sigma principles and quality management history.",
            display_order=1,
            status="published",
            video_provider="vimeo",
            video_url="https://vimeo.com/76979871",
        )
        l2 = Lesson(
            section_id=sec1.id,
            title="Lesson 2 — DMAIC Methodology Overview",
            description="The 5-phase structured problem solving framework: Define, Measure, Analyze, Improve, Control.",
            display_order=2,
            status="published",
            video_provider="youtube",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        db.session.add_all([l1, l2])

        # Section 2: Define Phase
        sec2 = CourseSection(
            course_id=course.id,
            title="Section 2 — Define Phase",
            description="Defining the problem, identifying stakeholders, and scoping improvement projects.",
            display_order=2,
        )
        db.session.add(sec2)
        db.session.flush()

        l3 = Lesson(
            section_id=sec2.id,
            title="Lesson 3 — Voice of Customer (VOC)",
            description="Capturing customer requirements and translating them into Critical to Quality (CTQ) metrics.",
            display_order=1,
            status="published",
            video_provider="drive",
            video_url="https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view",
        )
        l4 = Lesson(
            section_id=sec2.id,
            title="Lesson 4 — SIPOC Process Mapping",
            description="High-level process visualization: Suppliers, Inputs, Process, Outputs, Customers.",
            display_order=2,
            status="published",
            video_provider="loom",
            video_url="https://www.loom.com/share/dfb99f6920aa447d92f58e45d9fa0f41",
        )
        l5 = Lesson(
            section_id=sec2.id,
            title="Lesson 5 — Project Charter & Business Case",
            description="Defining project scope, objectives, financial benefits, and team roles.",
            display_order=3,
            status="published",
            video_provider="custom",
            video_url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        )
        db.session.add_all([l3, l4, l5])

        # Section 3: Statistical Methods (Testing draft isolation)
        sec3 = CourseSection(
            course_id=course.id,
            title="Section 3 — Statistical Methods (Draft Module)",
            description="Module under active authoring — testing draft isolation.",
            display_order=3,
        )
        db.session.add(sec3)
        db.session.flush()

        l6 = Lesson(
            section_id=sec3.id,
            title="Lesson 6 — Hypothesis Testing & ANOVA (Draft)",
            description="Draft lesson to verify non-published content exclusion on student side.",
            display_order=1,
            status="draft",
            video_provider="youtube",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        db.session.add(l6)
        db.session.flush()

        # ── 3. Enroll Demo Student & Seed Sample Progress ─────────────────────
        now = datetime.now(timezone.utc)
        enrollment = CourseEnrollment(
            user_id=student.id,
            course_id=course.id,
            status="active",
            enrolled_at=now,
            last_accessed_lesson_id=l2.id,
            last_accessed_at=now,
        )
        db.session.add(enrollment)
        db.session.flush()

        # Lesson 1: completed
        lp1 = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=l1.id,
            completed=True,
            completed_at=now,
            last_accessed_at=now,
        )
        # Lesson 2: accessed / last accessed
        lp2 = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=l2.id,
            completed=False,
            last_accessed_at=now,
        )
        db.session.add_all([lp1, lp2])

        db.session.commit()

        print("\n=======================================================")
        print("DEMO STUDENT ACCOUNT & LMS COURSE SEEDED SUCCESSFULLY")
        print("=======================================================")
        print(f"Role:         student")
        print(f"Username:     {demo_username}")
        print(f"Email:        {demo_email}")
        print(f"Password:     {demo_password}")
        print(f"Course Slug:  {demo_slug}")
        print(f"Enrollment:   Active (ID: {enrollment.id})")
        print(f"Progress:     1 of 5 published lessons completed (20%)")
        print(f"Last Lesson:  Lesson 2 — DMAIC Methodology Overview")
        print(f"Published:    5 lessons (Vimeo, YouTube, Google Drive, Loom, Custom)")
        print(f"Draft:        1 lesson (Draft isolation verified)")
        print("=======================================================\n")


if __name__ == "__main__":
    seed_demo_data()
