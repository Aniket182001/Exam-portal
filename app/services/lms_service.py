import re
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from app.extensions import db
from app.models.user import User
from app.models.course import Course, CourseSection, Lesson, CourseEnrollment, LessonProgress

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_PROVIDERS = [
    ("vimeo", "Vimeo"),
    ("youtube", "YouTube"),
    ("drive", "Google Drive"),
    ("loom", "Loom"),
    ("custom", "Other / Custom"),
]

COURSE_STATUSES = ["draft", "published", "archived"]
LESSON_STATUSES = ["draft", "published"]
ENROLLMENT_STATUSES = ["active", "completed", "withdrawn"]


def generate_unique_slug(title: str, existing_course_id: int | None = None) -> str:
    """
    Generates a deterministic URL-safe slug from a course title and ensures uniqueness.
    Appends numeric suffixes (-2, -3, ...) if a collision occurs with another course.
    """
    if not title:
        base_slug = "course"
    else:
        # Convert to lowercase, replace non-alphanumeric characters with hyphens
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.strip().lower()).strip('-')
        base_slug = slug if slug else "course"

    candidate = base_slug
    counter = 1

    while True:
        query = Course.query.filter_by(slug=candidate)
        if existing_course_id is not None:
            query = query.filter(Course.id != existing_course_id)
        existing = query.first()
        if not existing:
            return candidate
        counter += 1
        candidate = f"{base_slug}-{counter}"


def validate_video_url(provider: str | None, url: str | None) -> tuple[bool, str | None, str | None]:
    """
    Validates a video URL according to its designated provider.
    Returns: (is_valid: bool, error_message: str | None, cleaned_url: str | None)

    Rules:
    - Empty URL is valid (for text-only or drafted lessons).
    - Prevents raw HTML, <script>, <iframe> injection.
    - Provider-specific structural checks for Vimeo, YouTube, Google Drive, Loom, and Custom.
    """
    if not url or not url.strip():
        # Empty video URL is allowed (reading material, placeholder, etc.)
        return True, None, None

    cleaned_url = url.strip()

    # Security check: strictly reject HTML or script tags
    if any(token in cleaned_url.lower() for token in ["<", ">", "script", "javascript:", "onload=", "onerror="]):
        return False, "Invalid video URL: HTML tags, scripts, and iframe snippets are not permitted.", None

    parsed = urlparse(cleaned_url)
    if not parsed.scheme or parsed.scheme.lower() not in ["http", "https"] or not parsed.netloc:
        return False, "Please enter a valid URL starting with http:// or https://", None

    domain = parsed.netloc.lower()

    if not provider:
        # If no provider given, auto-detect from domain
        if "vimeo.com" in domain:
            provider = "vimeo"
        elif "youtube.com" in domain or "youtu.be" in domain:
            provider = "youtube"
        elif "drive.google.com" in domain or "docs.google.com" in domain:
            provider = "drive"
        elif "loom.com" in domain:
            provider = "loom"
        else:
            provider = "custom"

    provider = provider.lower().strip()

    if provider == "vimeo":
        if "vimeo.com" not in domain:
            return False, "URL must be a valid Vimeo video link (e.g., https://vimeo.com/123456789).", None
        # Basic check for digits or unlisted path
        if not re.search(r'vimeo\.com/(?:channels/[^/]+/|video/|event/)?(\d+)', cleaned_url) and not re.search(r'vimeo\.com/(\d+)/([a-zA-Z0-9]+)', cleaned_url):
            return False, "Please enter a recognized Vimeo video URL (e.g., https://vimeo.com/123456789).", None

    elif provider == "youtube":
        if "youtube.com" not in domain and "youtu.be" not in domain:
            return False, "URL must be a valid YouTube video link (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...).", None

    elif provider == "drive":
        if "drive.google.com" not in domain and "docs.google.com" not in domain:
            return False, "URL must be a valid Google Drive file link (e.g., https://drive.google.com/file/d/.../view).", None

    elif provider == "loom":
        if "loom.com" not in domain:
            return False, "URL must be a valid Loom video link (e.g., https://www.loom.com/share/...).", None

    elif provider == "custom":
        # Custom already validated for http/https without HTML
        pass

    else:
        return False, f"Unsupported video provider '{provider}'.", None

    return True, None, cleaned_url


def reorder_sections(course_id: int, section_id: int, direction: str) -> bool:
    """
    Deterministically reorders a section within a course ('up' or 'down').
    Normalizes display_order sequence to 1..N and swaps adjacent items.
    """
    sections = CourseSection.query.filter_by(course_id=course_id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    # Re-normalize to guarantee strict sequential display_order
    for idx, sec in enumerate(sections, start=1):
        sec.display_order = idx

    current_idx = None
    for idx, sec in enumerate(sections):
        if sec.id == section_id:
            current_idx = idx
            break

    if current_idx is None:
        return False

    if direction == "up" and current_idx > 0:
        prev_idx = current_idx - 1
        sections[current_idx].display_order, sections[prev_idx].display_order = (
            sections[prev_idx].display_order,
            sections[current_idx].display_order,
        )
        db.session.commit()
        return True
    elif direction == "down" and current_idx < len(sections) - 1:
        next_idx = current_idx + 1
        sections[current_idx].display_order, sections[next_idx].display_order = (
            sections[next_idx].display_order,
            sections[current_idx].display_order,
        )
        db.session.commit()
        return True

    return False


def reorder_lessons(section_id: int, lesson_id: int, direction: str) -> bool:
    """
    Deterministically reorders a lesson within a section ('up' or 'down').
    Normalizes display_order sequence to 1..N and swaps adjacent items.
    """
    lessons = Lesson.query.filter_by(section_id=section_id).order_by(
        Lesson.display_order.asc(),
        Lesson.id.asc()
    ).all()

    # Re-normalize
    for idx, les in enumerate(lessons, start=1):
        les.display_order = idx

    current_idx = None
    for idx, les in enumerate(lessons):
        if les.id == lesson_id:
            current_idx = idx
            break

    if current_idx is None:
        return False

    if direction == "up" and current_idx > 0:
        prev_idx = current_idx - 1
        lessons[current_idx].display_order, lessons[prev_idx].display_order = (
            lessons[prev_idx].display_order,
            lessons[current_idx].display_order,
        )
        db.session.commit()
        return True
    elif direction == "down" and current_idx < len(lessons) - 1:
        next_idx = current_idx + 1
        lessons[current_idx].display_order, lessons[next_idx].display_order = (
            lessons[next_idx].display_order,
            lessons[current_idx].display_order,
        )
        db.session.commit()
        return True

    return False


def reorder_courses(course_id: int, direction: str) -> bool:
    """
    Deterministically reorders courses across the course list ('up' or 'down').
    """
    courses = Course.query.order_by(
        Course.display_order.asc(),
        Course.id.asc()
    ).all()

    for idx, c in enumerate(courses, start=1):
        c.display_order = idx

    current_idx = None
    for idx, c in enumerate(courses):
        if c.id == course_id:
            current_idx = idx
            break

    if current_idx is None:
        return False

    if direction == "up" and current_idx > 0:
        prev_idx = current_idx - 1
        courses[current_idx].display_order, courses[prev_idx].display_order = (
            courses[prev_idx].display_order,
            courses[current_idx].display_order,
        )
        db.session.commit()
        return True
    elif direction == "down" and current_idx < len(courses) - 1:
        next_idx = current_idx + 1
        courses[current_idx].display_order, courses[next_idx].display_order = (
            courses[next_idx].display_order,
            courses[current_idx].display_order,
        )
        db.session.commit()
        return True

    return False


def resolve_video_embed(provider: str | None, video_url: str | None) -> dict:
    """
    Normalizes a validated video source into a safe embed payload for student rendering.
    Supports: Vimeo, YouTube, Google Drive, Loom, and Custom.

    Returns a dict:
    {
        "status": "success" | "empty" | "error",
        "type": "iframe" | "html5_video" | "empty" | "error",
        "provider": str | None,
        "embed_url": str | None,
        "warning": str | None,
        "error_message": str | None,
        "original_url": str | None,
    }
    """
    if not video_url or not str(video_url).strip():
        return {
            "status": "empty",
            "type": "empty",
            "provider": provider,
            "embed_url": None,
            "warning": None,
            "error_message": "No video has been added to this lesson yet.",
            "original_url": None,
        }

    raw_url = str(video_url).strip()

    # Pre-validate safety: reject any script/html injection attempt
    is_valid, err_msg, cleaned_url = validate_video_url(provider, raw_url)
    if not is_valid or not cleaned_url:
        return {
            "status": "error",
            "type": "error",
            "provider": provider,
            "embed_url": None,
            "warning": None,
            "error_message": "Video unavailable. We couldn't load this lesson video. Please try again later.",
            "original_url": None,
        }

    prov = (provider or "").lower().strip()
    if not prov:
        parsed_domain = urlparse(cleaned_url).netloc.lower()
        if "vimeo.com" in parsed_domain:
            prov = "vimeo"
        elif "youtube.com" in parsed_domain or "youtu.be" in parsed_domain:
            prov = "youtube"
        elif "drive.google.com" in parsed_domain or "docs.google.com" in parsed_domain:
            prov = "drive"
        elif "loom.com" in parsed_domain:
            prov = "loom"
        else:
            prov = "custom"

    try:
        if prov == "youtube":
            # Extract 11-char YouTube video ID
            yt_match = re.search(r'(?:v=|/embed/|youtu\.be/|/v/|/shorts/)([a-zA-Z0-9_-]{11})', cleaned_url)
            if yt_match:
                vid_id = yt_match.group(1)
                embed_url = f"https://www.youtube.com/embed/{vid_id}?rel=0&modestbranding=1"
                return {
                    "status": "success",
                    "type": "iframe",
                    "provider": "youtube",
                    "embed_url": embed_url,
                    "warning": None,
                    "error_message": None,
                    "original_url": cleaned_url,
                }

        elif prov == "vimeo":
            # Extract digits and optional unlisted hash
            # Matches: vimeo.com/123456789 or vimeo.com/123456789/abcdef or player.vimeo.com/video/123456789?h=abcdef
            vid_match = re.search(r'(?:vimeo\.com/(?:video/|channels/[^/]+/)?|player\.vimeo\.com/video/)(\d+)', cleaned_url)
            hash_match = re.search(r'(?:vimeo\.com/\d+/([a-zA-Z0-9]+)|[?&]h=([a-zA-Z0-9]+))', cleaned_url)

            if vid_match:
                vid_id = vid_match.group(1)
                hash_id = None
                if hash_match:
                    hash_id = hash_match.group(1) or hash_match.group(2)

                if hash_id:
                    embed_url = f"https://player.vimeo.com/video/{vid_id}?h={hash_id}&title=0&byline=0&portrait=0"
                else:
                    embed_url = f"https://player.vimeo.com/video/{vid_id}?title=0&byline=0&portrait=0"
                return {
                    "status": "success",
                    "type": "iframe",
                    "provider": "vimeo",
                    "embed_url": embed_url,
                    "warning": None,
                    "error_message": None,
                    "original_url": cleaned_url,
                }

        elif prov in ("drive", "google_drive"):
            # Extract Google Drive file ID
            drive_match = re.search(r'(?:file/d/|open\?id=|id=)([a-zA-Z0-9_-]+)', cleaned_url)
            if drive_match:
                file_id = drive_match.group(1)
                embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
                warning_msg = (
                    "This video is hosted on Google Drive. The file owner must allow access "
                    "('Anyone with the link can view') for this video to play."
                )
                return {
                    "status": "success",
                    "type": "iframe",
                    "provider": "drive",
                    "embed_url": embed_url,
                    "warning": warning_msg,
                    "error_message": None,
                    "original_url": cleaned_url,
                }

        elif prov == "loom":
            loom_match = re.search(r'loom\.com/(?:share|embed)/([a-zA-Z0-9_-]+)', cleaned_url)
            if loom_match:
                loom_id = loom_match.group(1)
                embed_url = f"https://www.loom.com/embed/{loom_id}?hide_owner=true&hide_share=true&hide_title=true&hideEmbedTopBar=true"
                return {
                    "status": "success",
                    "type": "iframe",
                    "provider": "loom",
                    "embed_url": embed_url,
                    "warning": None,
                    "error_message": None,
                    "original_url": cleaned_url,
                }

        elif prov == "custom":
            parsed = urlparse(cleaned_url)
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in [".mp4", ".webm", ".ogg"]):
                return {
                    "status": "success",
                    "type": "html5_video",
                    "provider": "custom",
                    "embed_url": cleaned_url,
                    "warning": None,
                    "error_message": None,
                    "original_url": cleaned_url,
                }
            else:
                return {
                    "status": "success",
                    "type": "iframe",
                    "provider": "custom",
                    "embed_url": cleaned_url,
                    "warning": None,
                    "error_message": None,
                    "original_url": cleaned_url,
                }

    except Exception as e:
        logger.error(f"Error resolving video embed for {cleaned_url}: {e}")

    return {
        "status": "error",
        "type": "error",
        "provider": provider,
        "embed_url": None,
        "warning": None,
        "error_message": "Video unavailable. We couldn't load this lesson video. Please try again later.",
        "original_url": None,
    }


def get_student_course_curriculum(course_id: int) -> dict:
    """
    Returns the student-visible curriculum for a course:
    - Only published lessons.
    - Sections ordered by CourseSection.display_order.asc(), CourseSection.id.asc().
    - Lessons ordered by Lesson.display_order.asc(), Lesson.id.asc().
    """
    sections = CourseSection.query.filter_by(course_id=course_id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    curriculum_sections = []
    first_lesson = None
    total_published_lessons = 0

    for sec in sections:
        pub_lessons = Lesson.query.filter_by(
            section_id=sec.id,
            status="published"
        ).order_by(
            Lesson.display_order.asc(),
            Lesson.id.asc()
        ).all()

        if pub_lessons:
            if first_lesson is None:
                first_lesson = pub_lessons[0]

            total_published_lessons += len(pub_lessons)

            curriculum_sections.append({
                "section": sec,
                "lessons": pub_lessons,
            })

    return {
        "sections": curriculum_sections,
        "total_published_lessons": total_published_lessons,
        "first_lesson": first_lesson,
    }


def get_lesson_navigation(course_id: int, current_lesson_id: int) -> dict:
    """
    Computes hierarchical previous and next published lessons across all sections in the course.
    Follows:
      Section 1 (Lesson 1 -> Lesson 2) -> Section 2 (Lesson 3 -> Lesson 4).
    Draft and archived lessons are excluded.
    """
    sections = CourseSection.query.filter_by(course_id=course_id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    ordered_lessons = []
    for sec in sections:
        lessons = Lesson.query.filter_by(
            section_id=sec.id,
            status="published"
        ).order_by(
            Lesson.display_order.asc(),
            Lesson.id.asc()
        ).all()
        ordered_lessons.extend(lessons)

    current_idx = None
    for idx, les in enumerate(ordered_lessons):
        if les.id == current_lesson_id:
            current_idx = idx
            break

    if current_idx is None:
        return {
            "prev_lesson": None,
            "next_lesson": None,
            "current_index": None,
            "total_lessons": len(ordered_lessons),
        }

    prev_lesson = ordered_lessons[current_idx - 1] if current_idx > 0 else None
    next_lesson = ordered_lessons[current_idx + 1] if current_idx < len(ordered_lessons) - 1 else None

    return {
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "current_index": current_idx + 1,
        "total_lessons": len(ordered_lessons),
    }


def calculate_course_progress(enrollment_id: int) -> dict:
    """
    Calculates progress for a student enrollment:
    - Only published lessons in the course are counted.
    - Draft lessons (or completed lessons later switched to draft) are strictly excluded.
    - Returns a dict with total_lessons, completed_lessons, percentage, is_completed, completed_lesson_ids.
    - Safe against zero published lessons (percentage = 0, no division by zero).
    """
    enrollment = db.session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        return {
            "total_lessons": 0,
            "completed_lessons": 0,
            "percentage": 0,
            "is_completed": False,
            "completed_lesson_ids": set(),
        }

    # Find all published lessons in the course
    published_lessons = Lesson.query.join(CourseSection).filter(
        CourseSection.course_id == enrollment.course_id,
        Lesson.status == "published"
    ).all()

    total_published = len(published_lessons)
    published_lesson_ids = {l.id for l in published_lessons}

    if not published_lesson_ids:
        return {
            "total_lessons": 0,
            "completed_lessons": 0,
            "percentage": 0,
            "progress_percent": 0,
            "is_completed": False,
            "completed_lesson_ids": set(),
        }

    # Only count completed records that correspond to currently published lessons
    completed_records = LessonProgress.query.filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.completed.is_(True),
        LessonProgress.lesson_id.in_(published_lesson_ids)
    ).all()

    completed_count = len(completed_records)
    percentage = min(100, round((completed_count / total_published) * 100))
    is_completed = (total_published > 0 and completed_count == total_published)

    return {
        "total_lessons": total_published,
        "completed_lessons": completed_count,
        "percentage": percentage,
        "progress_percent": percentage,
        "is_completed": is_completed,
        "completed_lesson_ids": {r.lesson_id for r in completed_records},
    }


def mark_lesson_complete(enrollment_id: int, lesson_id: int) -> tuple[bool, str, dict]:
    """
    Marks a lesson complete idempotently:
    - Validates lesson belongs to enrollment course and is published.
    - Creates or updates LessonProgress record.
    - Updates completion timestamp and last_accessed_at.
    - If course is now 100% complete, updates enrollment status='completed' and sets completed_at.
    """
    enrollment = db.session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        return False, "Enrollment not found.", {}

    lesson = db.session.get(Lesson, lesson_id)
    if not lesson or not lesson.section or lesson.section.course_id != enrollment.course_id:
        return False, "Lesson does not belong to enrolled course.", {}

    if lesson.status != "published":
        return False, "Cannot complete unpublished lesson.", {}

    # Find or create progress record
    progress_rec = LessonProgress.query.filter_by(
        enrollment_id=enrollment.id,
        lesson_id=lesson.id
    ).first()

    now = datetime.now(timezone.utc)
    already_done = bool(progress_rec and progress_rec.completed)

    if not progress_rec:
        progress_rec = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            completed=True,
            completed_at=now,
            last_accessed_at=now,
        )
        db.session.add(progress_rec)
    else:
        progress_rec.completed = True
        if not progress_rec.completed_at:
            progress_rec.completed_at = now
        progress_rec.last_accessed_at = now

    enrollment.last_accessed_lesson_id = lesson.id
    enrollment.last_accessed_at = now

    db.session.commit()

    # Calculate new progress & auto-complete enrollment if 100%
    calc = calculate_course_progress(enrollment.id)
    if calc["is_completed"] and enrollment.status != "completed":
        enrollment.status = "completed"
        if not enrollment.completed_at:
            enrollment.completed_at = now
        db.session.commit()

    msg = "Lesson already marked as complete." if already_done else "Lesson completed."
    return True, msg, calc


def update_last_accessed_lesson(enrollment_id: int, lesson_id: int) -> bool:
    """
    Updates enrollment's last_accessed_lesson_id and last_accessed_at when student opens a valid published lesson.
    """
    enrollment = db.session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        return False

    lesson = db.session.get(Lesson, lesson_id)
    if not lesson or not lesson.section or lesson.section.course_id != enrollment.course_id or lesson.status != "published":
        return False

    now = datetime.now(timezone.utc)
    enrollment.last_accessed_lesson_id = lesson.id
    enrollment.last_accessed_at = now

    # Also update or touch lesson_progress record's last_accessed_at
    prog = LessonProgress.query.filter_by(enrollment_id=enrollment.id, lesson_id=lesson.id).first()
    if prog:
        prog.last_accessed_at = now
    else:
        prog = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            completed=False,
            last_accessed_at=now,
        )
        db.session.add(prog)

    db.session.commit()
    return True


def get_continue_learning_lesson(enrollment: CourseEnrollment) -> Lesson | None:
    """
    Determines the next lesson for 'Continue Learning':
    Case 1: Student has last accessed lesson that is published and not completed -> resume there.
    Case 2: Last accessed lesson is completed -> find the next incomplete published lesson in course order.
    Case 3: No last accessed lesson -> start at first published lesson.
    Case 4: All published lessons are completed -> return the final published lesson (for review).
    """
    sections = CourseSection.query.filter_by(course_id=enrollment.course_id).order_by(
        CourseSection.display_order.asc(),
        CourseSection.id.asc()
    ).all()

    ordered_published = []
    for sec in sections:
        lessons = Lesson.query.filter_by(
            section_id=sec.id,
            status="published"
        ).order_by(
            Lesson.display_order.asc(),
            Lesson.id.asc()
        ).all()
        ordered_published.extend(lessons)

    if not ordered_published:
        return None

    published_ids = {l.id for l in ordered_published}
    completed_records = LessonProgress.query.filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.completed.is_(True),
        LessonProgress.lesson_id.in_(published_ids)
    ).all()
    completed_ids = {r.lesson_id for r in completed_records}

    # Case 1: Check last_accessed_lesson_id
    if enrollment.last_accessed_lesson_id and enrollment.last_accessed_lesson_id in published_ids:
        if enrollment.last_accessed_lesson_id not in completed_ids:
            return db.session.get(Lesson, enrollment.last_accessed_lesson_id)

        # Case 2: Last accessed is completed -> find next incomplete lesson starting after it
        last_idx = None
        for idx, l in enumerate(ordered_published):
            if l.id == enrollment.last_accessed_lesson_id:
                last_idx = idx
                break

        if last_idx is not None:
            # Search forwards
            for l in ordered_published[last_idx + 1:]:
                if l.id not in completed_ids:
                    return l

            # If none found forwards, wrap around to find any incomplete lesson from beginning
            for l in ordered_published[:last_idx]:
                if l.id not in completed_ids:
                    return l

    # Case 3: No last accessed lesson (or not found) -> find first incomplete lesson
    for l in ordered_published:
        if l.id not in completed_ids:
            return l

    # Case 4: All published lessons completed -> return final lesson
    return ordered_published[-1]


def enroll_student_in_course(user_id: int, course_id: int) -> tuple[CourseEnrollment | None, str]:
    """
    Enrolls a student in a course or reactivates a withdrawn enrollment.
    Prevents duplicate active enrollments.
    """
    user = db.session.get(User, user_id)
    if not user:
        return None, "User not found."

    course = db.session.get(Course, course_id)
    if not course:
        return None, "Course not found."

    existing = CourseEnrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
    if existing:
        if existing.status in ["active", "completed"]:
            return None, f"Student '{user.username}' is already enrolled in '{course.title}' ({existing.status})."
        else:
            # Reactivate withdrawn enrollment
            existing.status = "active"
            existing.enrolled_at = datetime.now(timezone.utc)
            db.session.commit()
            return existing, f"Enrollment for '{user.username}' in '{course.title}' has been reactivated."

    enrollment = CourseEnrollment(
        user_id=user_id,
        course_id=course_id,
        status="active",
        enrolled_at=datetime.now(timezone.utc)
    )
    db.session.add(enrollment)
    db.session.commit()
    return enrollment, f"Student '{user.username}' enrolled in '{course.title}' successfully."


def update_enrollment_status(enrollment_id: int, new_status: str) -> tuple[bool, str]:
    """
    Updates an enrollment status ('active', 'completed', 'withdrawn').
    """
    if new_status not in ["active", "completed", "withdrawn"]:
        return False, "Invalid enrollment status."

    enrollment = db.session.get(CourseEnrollment, enrollment_id)
    if not enrollment:
        return False, "Enrollment not found."

    enrollment.status = new_status
    if new_status == "completed" and not enrollment.completed_at:
        enrollment.completed_at = datetime.now(timezone.utc)

    db.session.commit()
    return True, f"Enrollment status updated to '{new_status}'."


