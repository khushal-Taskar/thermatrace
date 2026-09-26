from datetime import timedelta, timezone
import math
from sqlalchemy import select, func
from ..models import Vehicle, Delivery, Route, Container, TelemetryHistory, Alert, SystemSettings, RescueMission, DispatchMessage, utcnow
from .rescue_dispatch import serialize_mission, serialize_message


def serialize_alert(alert):
    return {column.name: (getattr(alert,column.name).replace(tzinfo=timezone.utc).isoformat() if hasattr(getattr(alert,column.name),"isoformat") else getattr(alert,column.name)) for column in Alert.__table__.columns}


def fleet_snapshot(db):
    fleet=[]
    for vehicle in db.scalars(select(Vehicle).order_by(Vehicle.id)):
        record=db.scalar(select(TelemetryHistory).where(TelemetryHistory.vehicle_id==vehicle.id).order_by(TelemetryHistory.timestamp.desc(),TelemetryHistory.id.desc()).limit(1))
        if not record:
            continue
        snapshot=dict(record.snapshot)
        delivery=db.scalar(select(Delivery).where(Delivery.vehicle_id==vehicle.id))
        route=db.get(Route,delivery.route_id)
        container=db.get(Container,delivery.container_id)
        snapshot["delivery"]={**snapshot["delivery"],"planned_route":route.planned_route,"actual_route":vehicle.state.get("actual_route",[]),"route_provider":route.provider,"route_duration_minutes":route.duration_minutes}
        snapshot["container"]={**snapshot["container"],"min_temperature":container.min_temperature,"max_temperature":container.max_temperature}
        snapshot["scenario"]=vehicle.scenario
        fleet.append(snapshot)
    return fleet


def overview(db):
    fleet=fleet_snapshot(db)
    alerts=db.scalars(select(Alert).order_by(Alert.timestamp.desc(),Alert.id.desc()).limit(200)).all()
    unacknowledged=[a for a in alerts if a.active and not a.acknowledged]
    active=[s for s in fleet if s["delivery"]["delivery_status"] in ["IN_TRANSIT","DELAYED"]]
    missions=db.scalars(select(RescueMission).order_by(RescueMission.id.desc()).limit(20)).all()
    messages=db.scalars(select(DispatchMessage).order_by(DispatchMessage.id.desc()).limit(100)).all()
    return {"fleet":fleet,"alerts":[serialize_alert(a) for a in alerts],"rescue_missions":[serialize_mission(item) for item in missions],"dispatch_messages":[serialize_message(item) for item in reversed(messages)],"timestamp":utcnow().isoformat(),"simulation_paused":db.get(SystemSettings,1).simulation_paused,"metrics":{"active_vehicles":sum(s["vehicle"]["vehicle_status"]=="RUNNING" for s in fleet),"active_deliveries":len(active),"critical_alerts":sum(a.severity=="CRITICAL" for a in unacknowledged),"average_soc":round(sum(s["battery"]["soc"] for s in fleet)/max(1,len(fleet)),1),"safe_containers":sum(s["container"]["min_temperature"]<=s["container"]["temperature"]<=s["container"]["max_temperature"] for s in fleet),"total_containers":len(fleet),"high_risk_shipments":sum(s["risk"]["risk_score"]>60 for s in fleet),"on_time_percentage":round(sum(s["delivery"]["delay_minutes"]<=10 and s["delivery"]["delivery_status"]!="FAILED" for s in fleet)/max(1,len(fleet))*100),"total_vehicles":len(fleet),"unacknowledged_alerts":len(unacknowledged)}}


def history(db, vehicle_id=None, hours=1):
    query=select(TelemetryHistory).where(TelemetryHistory.timestamp>=utcnow()-timedelta(hours=hours))
    if vehicle_id:
        query=query.where(TelemetryHistory.vehicle_id==vehicle_id)
    count=db.scalar(select(func.count()).select_from(query.subquery()))
    stride=max(1,math.ceil(count/599))
    ranked=query.with_only_columns(TelemetryHistory.id,func.row_number().over(order_by=(TelemetryHistory.timestamp,TelemetryHistory.id)).label("position")).subquery()
    chosen=select(ranked.c.id).where((ranked.c.position%stride==0)|(ranked.c.position==1)|(ranked.c.position==count))
    rows=db.scalars(select(TelemetryHistory).where(TelemetryHistory.id.in_(chosen)).order_by(TelemetryHistory.timestamp,TelemetryHistory.id)).all()
    result=[]
    for row in rows:
        s=row.snapshot
        result.append({"timestamp":row.timestamp.isoformat()+"Z" if row.timestamp.tzinfo is None else row.timestamp.isoformat(),"vehicle_id":row.vehicle_id,"synthetic":row.synthetic,**{k:s["battery"][k] for k in ["soc","soh","battery_temperature","pack_current"]},**{k:s["vehicle"][k] for k in ["speed","motor_temperature"]},**{k:s["container"].get(k,0) for k in ["temperature","humidity","excursion_duration_minutes","remaining_safe_time_minutes","predicted_temperature"]},"risk_score":s["risk"]["risk_score"],"delay_minutes":s["delivery"]["delay_minutes"]})
    return result


def report(db, kind, vehicle_id=None, hours=24):
    fleet=fleet_snapshot(db)
    if vehicle_id:
        fleet=[s for s in fleet if s["vehicle"]["vehicle_id"]==vehicle_id]
    fields={"shipment":["temperature","humidity","excursion_duration_minutes","remaining_safe_time_minutes","delay_minutes","risk_score"],"vehicle":["speed","motor_temperature","risk_score"],"battery":["soc","soh","battery_temperature","pack_current"],"container":["temperature","humidity","excursion_duration_minutes","remaining_safe_time_minutes","predicted_temperature"],"risk":["risk_score"],"incident":["risk_score","delay_minutes"]}[kind]
    locations={"soc":"battery","soh":"battery","battery_temperature":"battery","pack_current":"battery","speed":"vehicle","motor_temperature":"vehicle","temperature":"container","humidity":"container","excursion_duration_minutes":"container","remaining_safe_time_minutes":"container","predicted_temperature":"container","risk_score":"risk","delay_minutes":"delivery"}
    aggregate_columns=[func.count(TelemetryHistory.id).label("samples")]
    for key in fields:
        value=TelemetryHistory.snapshot[locations[key]][key].as_float()
        aggregate_columns.extend([func.min(value).label(key+"_min"),func.max(value).label(key+"_max"),func.avg(value).label(key+"_avg")])
    query=select(*aggregate_columns).where(TelemetryHistory.timestamp>=utcnow()-timedelta(hours=hours))
    if vehicle_id:
        query=query.where(TelemetryHistory.vehicle_id==vehicle_id)
    aggregates=db.execute(query).mappings().one()
    stats={key:{"minimum":round(aggregates[key+"_min"],2),"maximum":round(aggregates[key+"_max"],2),"average":round(aggregates[key+"_avg"],2)} for key in fields} if aggregates["samples"] else {}
    alerts_query=select(Alert).where(Alert.timestamp>=utcnow()-timedelta(hours=hours))
    if vehicle_id:
        alerts_query=alerts_query.where(Alert.vehicle_id==vehicle_id)
    alerts=db.scalars(alerts_query.order_by(Alert.timestamp.desc())).all()
    return {"title":f"{kind.title()} Report","generated_at":utcnow().isoformat(),"period_hours":hours,"vehicle_id":vehicle_id or "ALL","sample_count":aggregates["samples"],"statistics":stats,"fleet":fleet,"incidents":[serialize_alert(a) for a in alerts],"data_source":"Software simulation including synthetic demo pre-roll; not a regulatory compliance certificate."}
