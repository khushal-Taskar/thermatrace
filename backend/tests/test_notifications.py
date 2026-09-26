from datetime import timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models import Alert, NotificationDelivery, User, utcnow
from app.services.notifications import NotificationService


def _alert(severity="HIGH"):
    return Alert(
        vehicle_id="PHARMA-EV-001",
        container_id="CNT-001",
        shipment_id="SHIP-001",
        type="TEMPERATURE_EXCURSION",
        severity=severity,
        reason="Container temperature exceeded its medicine profile.",
        recommended_action="Inspect the container and move it to qualified cold storage.",
        telemetry_snapshot={"container_temperature": 10.4, "soc": 62.0},
        active=True,
        acknowledged=False,
    )


def test_email_dispatch_is_deduplicated_and_failed_delivery_retries(monkeypatch):
    service = NotificationService()
    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(service, "_send_alert", lambda destination, alert: sent.append((destination, alert.id)))

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@thermatrace.local"))
        original = (user.notification_email, user.email_notifications)
        user.notification_email = "alerts@example.com"
        user.email_notifications = True
        alert = _alert()
        db.add(alert)
        db.commit()
        alert_id, user_id = alert.id, user.id

    try:
        with SessionLocal() as db:
            first = service.dispatch(db)
            delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.alert_id == alert_id))
            assert first["sent"] >= 1
            assert delivery.status == "SENT"
            assert delivery.destination == "alerts@example.com"

        sent_before = len(sent)
        with SessionLocal() as db:
            second = service.dispatch(db)
            assert second["sent"] == 0
        assert len(sent) == sent_before

        with SessionLocal() as db:
            retry_alert = _alert("CRITICAL")
            db.add(retry_alert)
            db.commit()
            retry_id = retry_alert.id
        monkeypatch.setattr(service, "_send_alert", lambda *_: (_ for _ in ()).throw(RuntimeError("SMTP unavailable")))
        with SessionLocal() as db:
            failed = service.dispatch(db)
            delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.alert_id == retry_id))
            assert failed["failed"] == 1
            assert delivery.status == "FAILED"
            delivery.created_at = utcnow() - timedelta(minutes=6)
            db.commit()
        monkeypatch.setattr(service, "_send_alert", lambda destination, alert: sent.append((destination, alert.id)))
        with SessionLocal() as db:
            retried = service.dispatch(db)
            delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.alert_id == retry_id))
            assert retried["sent"] == 1
            assert delivery.status == "SENT"
    finally:
        with SessionLocal() as db:
            db.execute(delete(NotificationDelivery).where(NotificationDelivery.alert_id.in_([alert_id, retry_id])))
            db.execute(delete(Alert).where(Alert.id.in_([alert_id, retry_id])))
            user = db.get(User, user_id)
            user.notification_email, user.email_notifications = original
            db.commit()


def test_notification_preferences_validate_email_and_test_endpoint(authenticated, monkeypatch):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@thermatrace.local"))
        original = (user.notification_email, user.email_notifications)
        user_id = user.id
    invalid = authenticated.put(
        "/api/me/notifications",
        json={"notification_email": "not-an-email", "email_notifications": True},
    )
    assert invalid.status_code == 422

    try:
        saved = authenticated.put(
            "/api/me/notifications",
            json={"notification_email": "control@example.com", "email_notifications": True},
        )
        assert saved.status_code == 200
        assert saved.json()["notification_email"] == "control@example.com"

        monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
        destinations = []
        monkeypatch.setattr("app.services.notifications.NotificationService.send_test", lambda self, value: destinations.append(value))
        response = authenticated.post("/api/notifications/test")
        assert response.status_code == 200
        assert response.json()["destination"] == "control@example.com"
        assert destinations == ["control@example.com"]
    finally:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.notification_email, user.email_notifications = original
            db.commit()
