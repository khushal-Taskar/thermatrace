"""Persist rescue journeys and two dispatch inboxes."""
from alembic import op
import sqlalchemy as sa

revision = "0003_rescue_dispatch"
down_revision = "0002_voice_agent"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rescue_missions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_vehicle_id", sa.String(40), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("replacement_vehicle_id", sa.String(40), nullable=False),
        sa.Column("shipment_id", sa.String(40), nullable=False),
        sa.Column("source", sa.String(150), nullable=False),
        sa.Column("destination", sa.String(150), nullable=False),
        sa.Column("breakdown_location", sa.JSON(), nullable=False),
        sa.Column("pickup_route", sa.JSON(), nullable=False),
        sa.Column("onward_route", sa.JSON(), nullable=False),
        sa.Column("route_provider", sa.String(30), nullable=False),
        sa.Column("position", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("transfer_ticks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transferred_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_rescue_missions_incident_vehicle_id", "rescue_missions", ["incident_vehicle_id"])
    op.create_index("ix_rescue_missions_shipment_id", "rescue_missions", ["shipment_id"])
    op.create_index("ix_rescue_missions_status", "rescue_missions", ["status"])
    op.create_table(
        "dispatch_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("point", sa.String(1), nullable=False),
        sa.Column("incident_vehicle_id", sa.String(40), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("rescue_missions.id")),
        sa.Column("voice_session_id", sa.Integer(), sa.ForeignKey("voice_sessions.id")),
        sa.Column("sender", sa.String(60), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_dispatch_messages_point", "dispatch_messages", ["point"])
    op.create_index("ix_dispatch_messages_incident_vehicle_id", "dispatch_messages", ["incident_vehicle_id"])


def downgrade():
    op.drop_table("dispatch_messages")
    op.drop_table("rescue_missions")
