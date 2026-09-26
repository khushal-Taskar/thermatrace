"""High and critical alert delivery through a configured SMTP account."""
import smtplib
import ssl
import threading
from datetime import timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import select

from ..config import settings
from ..models import Alert, NotificationDelivery, User, utcnow


class NotificationService:
    retry_delay = timedelta(minutes=5)
    _dispatch_lock = threading.Lock()

    def status(self):
        return {
            "email_configured": bool(settings.smtp_host),
            "browser_supported": True,
            "channels": ["EMAIL", "BROWSER"],
            "severity_filter": ["HIGH", "CRITICAL"],
            "sender": self._sender() if settings.smtp_host else None,
        }

    def dispatch(self, db):
        with self._dispatch_lock:
            return self._dispatch_locked(db)

    def _dispatch_locked(self, db):
        if not settings.smtp_host:
            return {"sent": 0, "failed": 0, "disabled": True}
        alerts = db.scalars(
            select(Alert).where(
                Alert.active.is_(True),
                Alert.acknowledged.is_(False),
                Alert.severity.in_(["HIGH", "CRITICAL"]),
            )
        ).all()
        users = db.scalars(
            select(User).where(User.active.is_(True), User.email_notifications.is_(True))
        ).all()
        sent = failed = 0
        now = utcnow()
        for alert in alerts:
            for user in users:
                destination = (user.notification_email or user.email).strip().lower()
                delivery = db.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.alert_id == alert.id,
                        NotificationDelivery.user_id == user.id,
                        NotificationDelivery.channel == "EMAIL",
                    )
                )
                if delivery and delivery.status == "SENT":
                    continue
                if delivery and delivery.created_at:
                    last_attempt = delivery.created_at
                    if last_attempt.tzinfo is None:
                        last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                    if now - last_attempt < self.retry_delay:
                        continue
                if delivery:
                    delivery.status = "PENDING"
                    delivery.destination = destination
                    delivery.error = None
                    delivery.created_at = now
                else:
                    delivery = NotificationDelivery(
                        alert_id=alert.id,
                        user_id=user.id,
                        channel="EMAIL",
                        status="PENDING",
                        destination=destination,
                    )
                    db.add(delivery)
                    db.flush()
                try:
                    self._send_alert(destination, alert)
                    delivery.status = "SENT"
                    delivery.sent_at = utcnow()
                    sent += 1
                except Exception as exc:
                    delivery.status = "FAILED"
                    delivery.error = str(exc)[:500]
                    failed += 1
        db.commit()
        return {"sent": sent, "failed": failed, "disabled": False}

    def send_test(self, destination):
        if not settings.smtp_host:
            raise RuntimeError("SMTP email is not configured on the backend")
        message = EmailMessage()
        message["Subject"] = "ThermaTrace alert email test"
        message["From"] = self._sender()
        message["To"] = destination
        message.set_content(
            "ThermaTrace email delivery is working.\n\n"
            "Future HIGH and CRITICAL cold-chain alerts will be sent to this address."
        )
        self._deliver(message)

    def _send_alert(self, destination, alert):
        snapshot = alert.telemetry_snapshot or {}
        message = EmailMessage()
        message["Subject"] = f"[{alert.severity}] ThermaTrace {alert.type} - {alert.vehicle_id}"
        message["From"] = self._sender()
        message["To"] = destination
        facts = []
        for key in ("soc", "battery_temperature", "container_temperature", "humidity", "speed", "delay_minutes"):
            if key in snapshot:
                facts.append(f"{key.replace('_', ' ').title()}: {snapshot[key]}")
        fact_text = "\n".join(facts) if facts else "Open the control center for the recorded telemetry snapshot."
        message.set_content(
            f"Severity: {alert.severity}\n"
            f"Alert: {alert.type.replace('_', ' ')}\n"
            f"Vehicle: {alert.vehicle_id}\n"
            f"Shipment: {alert.shipment_id}\n"
            f"Detected: {alert.timestamp.isoformat()}\n\n"
            f"Reason: {alert.reason}\n\n"
            f"Telemetry facts:\n{fact_text}\n\n"
            f"Recommended action: {alert.recommended_action}\n\n"
            "Open ThermaTrace to review and acknowledge this incident."
        )
        self._deliver(message)

    def _sender(self):
        configured = settings.smtp_from.strip()
        if configured and not configured.endswith("@thermatrace.local"):
            return configured
        return settings.smtp_username.strip() or configured

    def _deliver(self, message):
        use_ssl = settings.smtp_use_ssl or settings.smtp_port == 465
        client_type = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        kwargs = {"host": settings.smtp_host, "port": settings.smtp_port, "timeout": 10}
        if use_ssl:
            kwargs["context"] = ssl.create_default_context()
        with client_type(**kwargs) as client:
            if settings.smtp_starttls and not use_ssl:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
