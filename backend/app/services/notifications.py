"""Alert notification dispatch. Email remains disabled until SMTP variables are configured."""
import smtplib
from email.message import EmailMessage
from sqlalchemy import select
from ..config import settings
from ..models import Alert, NotificationDelivery, User, utcnow


class NotificationService:
    def status(self):
        return {"email_configured":bool(settings.smtp_host),"browser_supported":True,"channels":["EMAIL","BROWSER"]}

    def dispatch(self,db):
        if not settings.smtp_host:
            return {"sent":0,"failed":0,"disabled":True}
        alerts=db.scalars(select(Alert).where(Alert.active==True,Alert.severity.in_(["HIGH","CRITICAL"]))).all()
        users=db.scalars(select(User).where(User.active==True,User.email_notifications==True)).all()
        sent=failed=0
        for alert in alerts:
            for user in users:
                destination=user.notification_email or user.email
                exists=db.scalar(select(NotificationDelivery).where(NotificationDelivery.alert_id==alert.id,NotificationDelivery.user_id==user.id,NotificationDelivery.channel=="EMAIL"))
                if exists:
                    continue
                delivery=NotificationDelivery(alert_id=alert.id,user_id=user.id,channel="EMAIL",status="PENDING",destination=destination)
                db.add(delivery); db.flush()
                try:
                    self._send(destination,alert)
                    delivery.status="SENT";delivery.sent_at=utcnow();sent+=1
                except Exception as exc:
                    delivery.status="FAILED";delivery.error=str(exc)[:500];failed+=1
        db.commit()
        return {"sent":sent,"failed":failed,"disabled":False}

    def _send(self,destination,alert):
        message=EmailMessage()
        message["Subject"]=f"[{alert.severity}] ThermaTrace {alert.type} - {alert.vehicle_id}"
        message["From"]=settings.smtp_from
        message["To"]=destination
        message.set_content(f"Vehicle: {alert.vehicle_id}\nShipment: {alert.shipment_id}\n\n{alert.reason}\n\nRecommended action: {alert.recommended_action}\n\nOpen ThermaTrace to acknowledge this incident.")
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username,settings.smtp_password)
            client.send_message(message)

