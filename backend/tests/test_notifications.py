from datetime import timedelta
import socketserver
from threading import Thread

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
        timestamp=utcnow(),
        reason="Container temperature exceeded its medicine profile.",
        recommended_action="Inspect the container and move it to qualified cold storage.",
        telemetry_snapshot={"container_temperature": 10.4, "soc": 62.0},
        active=True,
        acknowledged=False,
    )


def test_email_dispatch_is_deduplicated_and_failed_delivery_retries(authenticated, monkeypatch):
    service = NotificationService()
    sent = []
    retry_id = None
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
        audit = authenticated.get("/api/notifications/deliveries")
        assert audit.status_code == 200
        assert any(row["destination"] == "alerts@example.com" and row["status"] == "SENT" for row in audit.json())

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
            ids = [value for value in [alert_id, retry_id] if value is not None]
            db.execute(delete(NotificationDelivery).where(NotificationDelivery.alert_id.in_(ids)))
            db.execute(delete(Alert).where(Alert.id.in_(ids)))
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


def test_email_transport_sends_test_and_alert_to_local_smtp_server(monkeypatch):
    messages = []

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 localhost test SMTP\r\n")
            body = bytearray()
            in_data = False
            while line := self.rfile.readline():
                command = line.strip().upper()
                if in_data:
                    if command == b".":
                        messages.append(bytes(body))
                        body.clear()
                        in_data = False
                        self.wfile.write(b"250 queued\r\n")
                    else:
                        body.extend(line)
                elif command.startswith(b"EHLO"):
                    self.wfile.write(b"250-localhost\r\n250 SIZE 1000000\r\n")
                elif command == b"DATA":
                    in_data = True
                    self.wfile.write(b"354 send data\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 OK\r\n")

    class SMTPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with SMTPServer(("127.0.0.1", 0), SMTPHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
        monkeypatch.setattr(settings, "smtp_port", server.server_address[1])
        monkeypatch.setattr(settings, "smtp_starttls", False)
        monkeypatch.setattr(settings, "smtp_use_ssl", False)
        monkeypatch.setattr(settings, "smtp_username", "")
        service = NotificationService()
        service.send_test("control@example.com")
        service._send_alert("control@example.com", _alert())
        server.shutdown()
        thread.join(timeout=2)

    assert len(messages) == 2
    assert b"ThermaTrace alert email test" in messages[0]
    assert b"control@example.com" in messages[0]
    assert b"[HIGH] ThermaTrace TEMPERATURE_EXCURSION" in messages[1]
    assert b"Recommended action" in messages[1]
