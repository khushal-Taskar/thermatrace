from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, JSON, Integer, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(100), default="Operations Admin")
    role: Mapped[str] = mapped_column(String(20), default="VIEWER", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    driver_name: Mapped[str] = mapped_column(String(100))
    baseline_soc: Mapped[float] = mapped_column(Float)
    soh: Mapped[float] = mapped_column(Float)
    scenario: Mapped[str] = mapped_column(String(60), default="NORMAL_DELIVERY")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    telemetry_source: Mapped[str] = mapped_column(String(20), default="SIMULATION")
    last_sensor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source: Mapped[str] = mapped_column(String(150))
    destination: Mapped[str] = mapped_column(String(150))
    planned_route: Mapped[list] = mapped_column(JSON)
    distance_km: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(30), default="DEMO")
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_routed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MedicineProfile(Base):
    __tablename__ = "medicine_profiles"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    min_temperature: Mapped[float] = mapped_column(Float)
    max_temperature: Mapped[float] = mapped_column(Float)
    warning_margin: Mapped[float] = mapped_column(Float, default=0.7)
    max_excursion_minutes: Mapped[float] = mapped_column(Float, default=30)
    prediction_horizon_minutes: Mapped[int] = mapped_column(Integer, default=15)
    handling_notes: Mapped[str] = mapped_column(Text, default="Demonstration profile; verify manufacturer stability instructions.")
    validated: Mapped[bool] = mapped_column(Boolean, default=False)


class Container(Base):
    __tablename__ = "containers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String(40), unique=True)
    medicine_name: Mapped[str] = mapped_column(String(150))
    batch_number: Mapped[str] = mapped_column(String(50))
    min_temperature: Mapped[float] = mapped_column(Float, default=2)
    max_temperature: Mapped[float] = mapped_column(Float, default=8)
    medicine_profile_id: Mapped[str | None] = mapped_column(ForeignKey("medicine_profiles.id"), nullable=True, index=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), unique=True)
    container_id: Mapped[str] = mapped_column(ForeignKey("containers.id"), unique=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VehicleTelemetry(Base):
    __tablename__ = "vehicle_telemetry"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    motor_temperature: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)


class BatteryTelemetry(Base):
    __tablename__ = "battery_telemetry"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    soc: Mapped[float] = mapped_column(Float)
    soh: Mapped[float] = mapped_column(Float)
    battery_temperature: Mapped[float] = mapped_column(Float)
    pack_current: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)


class ContainerTelemetry(Base):
    __tablename__ = "container_telemetry"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[str] = mapped_column(ForeignKey("containers.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)


class TelemetryHistory(Base):
    __tablename__ = "telemetry_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(JSON)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (Index("ix_history_vehicle_time", "vehicle_id", "timestamp"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    container_id: Mapped[str] = mapped_column(ForeignKey("containers.id"))
    shipment_id: Mapped[str] = mapped_column(String(40))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    type: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    recommended_action: Mapped[str] = mapped_column(String(500))
    telemetry_snapshot: Mapped[dict] = mapped_column(JSON)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    container_id: Mapped[str] = mapped_column(ForeignKey("containers.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[dict] = mapped_column(JSON)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    simulation_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[str] = mapped_column(String(100), default="ThermaTrace Logistics")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    destination: Mapped[str] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("alert_id", "user_id", "channel", name="uq_notification_alert_user_channel"),)


class SensorDevice(Base):
    __tablename__ = "sensor_devices"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    topic: Mapped[str] = mapped_column(String(200))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    training_source: Mapped[str] = mapped_column(String(200))
    sample_count: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON)
    feature_schema: Mapped[list] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(20), default="auto")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[dict] = mapped_column(JSON, default=dict)


class VoiceMessage(Base):
    __tablename__ = "voice_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20), default="en")
    source: Mapped[str] = mapped_column(String(30), default="VOICE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RescueMission(Base):
    __tablename__ = "rescue_missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    replacement_vehicle_id: Mapped[str] = mapped_column(String(40))
    shipment_id: Mapped[str] = mapped_column(String(40), index=True)
    source: Mapped[str] = mapped_column(String(150))
    destination: Mapped[str] = mapped_column(String(150))
    breakdown_location: Mapped[list] = mapped_column(JSON)
    pickup_route: Mapped[list] = mapped_column(JSON)
    onward_route: Mapped[list] = mapped_column(JSON)
    route_provider: Mapped[str] = mapped_column(String(30), default="STORED_ROUTE")
    position: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="TO_PICKUP", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    speed: Mapped[float] = mapped_column(Float, default=0)
    transfer_ticks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DispatchMessage(Base):
    __tablename__ = "dispatch_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    point: Mapped[str] = mapped_column(String(1), index=True)
    incident_vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("rescue_missions.id"), nullable=True)
    voice_session_id: Mapped[int | None] = mapped_column(ForeignKey("voice_sessions.id"), nullable=True)
    sender: Mapped[str] = mapped_column(String(60), default="AI_DISPATCH")
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DELIVERED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
