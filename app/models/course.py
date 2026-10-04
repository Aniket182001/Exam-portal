from datetime import datetime, timezone
from app.extensions import db


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, index=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="draft", nullable=False)  # draft, published, archived
    display_order = db.Column(db.Integer, default=1, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    sections = db.relationship(
        'CourseSection',
        backref='course',
        cascade='all, delete-orphan',
        lazy=True,
        order_by='CourseSection.display_order.asc()'
    )

    @property
    def total_sections(self):
        return len(self.sections)

    @property
    def total_lessons(self):
        return sum(len(s.lessons) for s in self.sections)

    def __repr__(self):
        return f"<Course id={self.id} slug='{self.slug}'>"


class CourseSection(db.Model):
    __tablename__ = 'course_sections'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer,
        db.ForeignKey('courses.id', ondelete='CASCADE'),
        nullable=False
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    lessons = db.relationship(
        'Lesson',
        backref='section',
        cascade='all, delete-orphan',
        lazy=True,
        order_by='Lesson.display_order.asc()'
    )

    def __repr__(self):
        return f"<CourseSection id={self.id} course_id={self.course_id} title='{self.title}'>"


class Lesson(db.Model):
    __tablename__ = 'lessons'

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(
        db.Integer,
        db.ForeignKey('course_sections.id', ondelete='CASCADE'),
        nullable=False
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(20), default="draft", nullable=False)  # draft, published
    video_provider = db.Column(db.String(50), nullable=True)  # vimeo, youtube, drive, etc.
    video_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def __repr__(self):
        return f"<Lesson id={self.id} section_id={self.section_id} title='{self.title}'>"


class CourseEnrollment(db.Model):
    __tablename__ = 'course_enrollments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    course_id = db.Column(
        db.Integer,
        db.ForeignKey('courses.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    status = db.Column(db.String(20), default="active", nullable=False)  # active, completed, withdrawn
    enrolled_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_accessed_lesson_id = db.Column(
        db.Integer,
        db.ForeignKey('lessons.id', ondelete='SET NULL'),
        nullable=True
    )
    last_accessed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_course_enrollment_user_course'),
    )

    # Relationships
    user = db.relationship('User', backref=db.backref('enrollments', cascade='all, delete-orphan', lazy=True))
    course = db.relationship('Course', backref=db.backref('enrollments', cascade='all, delete-orphan', lazy=True))
    last_accessed_lesson = db.relationship('Lesson', foreign_keys=[last_accessed_lesson_id], lazy=True)
    progress_records = db.relationship(
        'LessonProgress',
        backref='enrollment',
        cascade='all, delete-orphan',
        lazy=True
    )

    @property
    def student(self):
        return self.user

    def __repr__(self):
        return f"<CourseEnrollment id={self.id} user_id={self.user_id} course_id={self.course_id} status='{self.status}'>"


class LessonProgress(db.Model):
    __tablename__ = 'lesson_progress'

    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(
        db.Integer,
        db.ForeignKey('course_enrollments.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey('lessons.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_accessed_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint('enrollment_id', 'lesson_id', name='uq_lesson_progress_enrollment_lesson'),
    )

    lesson = db.relationship('Lesson', backref=db.backref('progress_records', cascade='all, delete-orphan', lazy=True))

    def __repr__(self):
        return f"<LessonProgress id={self.id} enrollment_id={self.enrollment_id} lesson_id={self.lesson_id} completed={self.completed}>"

