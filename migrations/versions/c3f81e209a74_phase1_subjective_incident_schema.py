"""Phase 1 - subjective and incident question support (schema only)

Revision ID: c3f81e209a74
Revises: 021af507a333
Create Date: 2026-07-14 21:49:00.000000

Changes
-------
* questions          : +question_type (String/20, NOT NULL, server_default='mcq')
                       +response_schema (JSON, nullable)
                       +rubric_text (Text, nullable)
* student_answers    : +answer_text (Text, nullable)
* evaluations        : NEW TABLE
* student_attempts   : +evaluation_status (String/20, NOT NULL, server_default='not_required')

All new NOT NULL columns carry a server_default so existing rows are
backfilled at the database level without a data migration step.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f81e209a74'
down_revision = '021af507a333'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # questions – add question_type, response_schema, rubric_text         #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'question_type',
            sa.String(length=20),
            nullable=False,
            server_default='mcq',
        ))
        batch_op.add_column(sa.Column(
            'response_schema',
            sa.JSON(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'rubric_text',
            sa.Text(),
            nullable=True,
        ))

    # ------------------------------------------------------------------ #
    # student_answers – add answer_text                                   #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('student_answers', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'answer_text',
            sa.Text(),
            nullable=True,
        ))

    # ------------------------------------------------------------------ #
    # evaluations – create new table                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        'evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_answer_id', sa.Integer(), nullable=False),
        sa.Column('evaluator_id', sa.Integer(), nullable=False),
        sa.Column('marks_awarded', sa.Float(), nullable=True),
        sa.Column('marks_breakdown', sa.JSON(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='pending'),
        sa.Column('evaluated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['student_answer_id'], ['student_answers.id']),
        sa.ForeignKeyConstraint(['evaluator_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_answer_id'),  # enforces 1:1 at DB level
    )

    # ------------------------------------------------------------------ #
    # student_attempts – add evaluation_status                            #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('student_attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'evaluation_status',
            sa.String(length=20),
            nullable=False,
            server_default='not_required',
        ))


def downgrade():
    # ------------------------------------------------------------------ #
    # student_attempts                                                     #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('student_attempts', schema=None) as batch_op:
        batch_op.drop_column('evaluation_status')

    # ------------------------------------------------------------------ #
    # evaluations                                                         #
    # ------------------------------------------------------------------ #
    op.drop_table('evaluations')

    # ------------------------------------------------------------------ #
    # student_answers                                                      #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('student_answers', schema=None) as batch_op:
        batch_op.drop_column('answer_text')

    # ------------------------------------------------------------------ #
    # questions                                                            #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('rubric_text')
        batch_op.drop_column('response_schema')
        batch_op.drop_column('question_type')
