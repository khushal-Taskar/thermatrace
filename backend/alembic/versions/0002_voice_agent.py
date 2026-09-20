"""Add local AI voice conversations and structured notes."""
from alembic import op
import sqlalchemy as sa
from app.database import Base
import app.models  # noqa: F401

revision="0002_voice_agent"
down_revision="0001_platform_upgrade"
branch_labels=None
depends_on=None


def upgrade():
    # create_all is intentional for a portable first migration across SQLite
    # and PostgreSQL; both tables are additive and have no legacy data rewrite.
    bind=op.get_bind()
    Base.metadata.create_all(bind)


def downgrade():
    op.drop_table("voice_messages")
    op.drop_table("voice_sessions")
