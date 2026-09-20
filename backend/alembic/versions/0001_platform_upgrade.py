"""Baseline schema and production-platform additions."""
from alembic import op
import sqlalchemy as sa
from app.database import Base
import app.models  # noqa: F401

revision="0001_platform_upgrade"
down_revision=None
branch_labels=None
depends_on=None


def _columns(bind,table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind=op.get_bind()
    Base.metadata.create_all(bind)
    tables=set(sa.inspect(bind).get_table_names())
    additions={
        "users":[sa.Column("role",sa.String(20),nullable=False,server_default="VIEWER"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("notification_email",sa.String(200),nullable=True),sa.Column("email_notifications",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP"))],
        "vehicles":[sa.Column("telemetry_source",sa.String(20),nullable=False,server_default="SIMULATION"),sa.Column("last_sensor_at",sa.DateTime(timezone=True),nullable=True)],
        "routes":[sa.Column("provider",sa.String(30),nullable=False,server_default="DEMO"),sa.Column("duration_minutes",sa.Float(),nullable=True),sa.Column("last_routed_at",sa.DateTime(timezone=True),nullable=True)],
        "containers":[sa.Column("medicine_profile_id",sa.String(50),sa.ForeignKey("medicine_profiles.id",name="fk_containers_medicine_profile_id"),nullable=True)],
    }
    for table,columns in additions.items():
        if table not in tables: continue
        existing=_columns(bind,table)
        missing=[column for column in columns if column.name not in existing]
        if missing:
            # SQLite batch migrations use a temporary table. Clean up only a
            # stale Alembic table left by an interrupted previous attempt.
            if bind.dialect.name=="sqlite":
                bind.exec_driver_sql(f'DROP TABLE IF EXISTS "_alembic_tmp_{table}"')
            with op.batch_alter_table(table) as batch:
                for column in missing: batch.add_column(column)


def downgrade():
    pass
