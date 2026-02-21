"""Initial migration

Revision ID: 001_initial
Revises:
Create Date: 2024-01-27

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Capture sessions table
    op.create_table(
        "capture_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "COMPLETED", "ABANDONED", name="sessionstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
    )

    # Capture messages table
    op.create_table(
        "capture_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("capture_sessions.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("extracted_entities", sa.JSON()),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )

    # Processed files table
    op.create_table(
        "processed_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_path", sa.String(512), unique=True, nullable=False, index=True),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.Column("decisions_extracted", sa.Integer(), default=0),
    )

    # Drills table
    op.create_table(
        "drills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Drill attempts table
    op.create_table(
        "drill_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "drill_id", sa.String(36), sa.ForeignKey("drills.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("feedback", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("drill_attempts")
    op.drop_table("drills")
    op.drop_table("processed_files")
    op.drop_table("capture_messages")
    op.drop_table("capture_sessions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
