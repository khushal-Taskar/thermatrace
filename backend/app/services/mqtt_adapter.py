"""Optional MQTT adapter for validated real sensor packets."""
import copy
import json
import logging
import ssl
from datetime import datetime, timezone
from sqlalchemy import select
from paho.mqtt import client as mqtt
from ..config import settings
from ..database import SessionLocal
from ..models import Container, Delivery, MedicineProfile, SensorDevice, TelemetryHistory, Vehicle, utcnow
from ..schemas import SensorPacket
from .cold_chain import cold_chain_metrics, profile_or_default

logger=logging.getLogger("pharmatrace.mqtt")
ALLOWED={
    "vehicle":{"latitude","longitude","speed","rpm","motor_temperature","vehicle_status","odometer","ignition_status","accelerator_position","brake_status","estimated_range","dtc_code"},
    "battery":{"soc","soh","pack_voltage","pack_current","battery_temperature","cell_max_voltage","cell_min_voltage","charging_status","estimated_range","power_consumption","bms_fault"},
    "container":{"temperature","humidity","door_status","tamper_status","shock_level","vibration_level"},
    "delivery":{"distance_remaining","delivery_progress","delay_minutes","route_deviation_distance","delivery_status","route_risk_score"},
}


def ingest_sensor_packet(db, packet: SensorPacket, risk_engine, simulator):
    device=db.get(SensorDevice,packet.device_id)
    if not device or not device.active or device.vehicle_id!=packet.vehicle_id:
        raise ValueError("Unknown, inactive, or mismatched sensor device")
    vehicle=db.get(Vehicle,packet.vehicle_id)
    latest=db.scalar(select(TelemetryHistory).where(TelemetryHistory.vehicle_id==vehicle.id).order_by(TelemetryHistory.timestamp.desc(),TelemetryHistory.id.desc()).limit(1))
    if not latest:
        raise ValueError("Vehicle has no baseline telemetry")
    snapshot=copy.deepcopy(latest.snapshot)
    for section in ALLOWED:
        updates=getattr(packet,section)
        snapshot[section].update({key:value for key,value in updates.items() if key in ALLOWED[section]})
    now=datetime.fromisoformat(packet.timestamp.replace("Z","+00:00")) if packet.timestamp else utcnow()
    if now.tzinfo is None:
        now=now.replace(tzinfo=timezone.utc)
    delivery=db.scalar(select(Delivery).where(Delivery.vehicle_id==vehicle.id))
    container=db.get(Container,delivery.container_id)
    profile=db.get(MedicineProfile,container.medicine_profile_id) if container.medicine_profile_id else None
    metrics=cold_chain_metrics(container,profile_or_default(container,profile),float(snapshot["container"]["temperature"]),float(latest.snapshot["container"]["temperature"]),vehicle.state or {},max(1,(now-latest.timestamp.replace(tzinfo=timezone.utc)).total_seconds()))
    snapshot["container"].update(metrics)
    snapshot["container"].update({"min_temperature":profile.min_temperature if profile else container.min_temperature,"max_temperature":profile.max_temperature if profile else container.max_temperature})
    snapshot["vehicle"].update({"vehicle_id":vehicle.id,"vehicle_name":vehicle.name,"driver_name":vehicle.driver_name,"timestamp":now.isoformat()})
    snapshot["delivery"]["current_location"]=[snapshot["vehicle"]["latitude"],snapshot["vehicle"]["longitude"]]
    snapshot["timestamp"]=now.isoformat();snapshot["scenario"]="REAL_SENSOR"
    snapshot["risk"]=risk_engine.evaluate(snapshot)
    vehicle.telemetry_source="MQTT";vehicle.last_sensor_at=now
    vehicle.state={**(vehicle.state or {}),"temp":snapshot["container"]["temperature"],"temperature_trend_c_per_minute":metrics["temperature_trend_c_per_minute"],"excursion_duration_minutes":metrics["excursion_duration_minutes"]}
    device.last_seen=now
    simulator.persist(db,snapshot,now,synthetic=False)
    db.commit()
    return snapshot


class MQTTAdapter:
    def __init__(self,risk_engine,simulator,after_ingest=None):
        self.risk_engine=risk_engine;self.simulator=simulator;self.after_ingest=after_ingest
        self.client=None;self.connected=False;self.messages=0;self.errors=0;self.last_error=None

    def start(self):
        if not settings.mqtt_enabled or not settings.mqtt_broker_host:
            return
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="thermatrace-ingest",protocol=mqtt.MQTTv5)
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username,settings.mqtt_password)
        if settings.mqtt_tls:
            self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self.client.on_connect=self._on_connect;self.client.on_disconnect=self._on_disconnect;self.client.on_message=self._on_message
        self.client.connect_async(settings.mqtt_broker_host,settings.mqtt_broker_port,60)
        self.client.loop_start()

    def stop(self):
        if self.client:
            self.client.disconnect();self.client.loop_stop()

    def status(self):
        return {"enabled":settings.mqtt_enabled,"configured":bool(settings.mqtt_broker_host),"connected":self.connected,"topic":settings.mqtt_topic,"messages":self.messages,"errors":self.errors,"last_error":self.last_error}

    def _on_connect(self,client,userdata,flags,reason_code,properties):
        self.connected=not reason_code.is_failure
        if self.connected:
            client.subscribe(settings.mqtt_topic,qos=1)

    def _on_disconnect(self,client,userdata,flags,reason_code,properties):
        self.connected=False

    def _on_message(self,client,userdata,message):
        try:
            packet=SensorPacket.model_validate(json.loads(message.payload.decode("utf-8")))
            with SessionLocal() as db:
                ingest_sensor_packet(db,packet,self.risk_engine,self.simulator)
            self.messages+=1
            if self.after_ingest:
                self.after_ingest()
        except Exception as exc:
            self.errors+=1;self.last_error=str(exc)[:500]
            logger.exception("Rejected MQTT telemetry packet")

