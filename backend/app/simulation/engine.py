import math
from datetime import timedelta
from sqlalchemy import select, delete
from ..models import Vehicle, Container, Delivery, Route, MedicineProfile, TelemetryHistory, BatteryTelemetry, VehicleTelemetry, ContainerTelemetry, Alert, RiskEvent, SystemSettings, utcnow
from ..services.cold_chain import cold_chain_metrics, profile_or_default
from ..services.rescue_dispatch import advance_missions


def smooth(current, target, rate=.12):
    return current + (target-current)*rate


def point_on_route(points, progress):
    position = min(.999999, max(0, progress)) * (len(points)-1)
    i=int(position)
    fraction=position-i
    return [points[i][k] + (points[i+1][k]-points[i][k])*fraction for k in [0,1]]


def deviation_km(point, points):
    # Local equirectangular projection, point-to-segment distance in kilometres.
    def project(p):
        return (p[1]*111.32*math.cos(math.radians(point[0])), p[0]*111.32)
    p=project(point)
    distances=[]
    for a,b in zip(points,points[1:]):
        a,b=project(a),project(b)
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
        distances.append(math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy))
    return min(distances)


class Simulator:
    def __init__(self, risk_engine, interval=3):
        self.risk_engine = risk_engine
        self.interval = interval
        self.ticks = 0

    def advance(self, vehicle, container, delivery, route, now, warm_start=False, profile=None):
        i=int(vehicle.id[-3:])-1
        s=dict(vehicle.state or {})
        scenario=vehicle.scenario
        t=self.ticks*.13+i
        progress=s.get("progress", [.12,.32,.46,.27,.65][i])
        # Keep the software demo active after a delivery finishes by dispatching the
        # simulated vehicle on a fresh run. Safety faults remain stopped until reset.
        if progress>=1 and scenario not in ["VEHICLE_FAILURE", "BMS_FAULT"]:
            progress=.02+i*.008
            s["actual_route"]=[]
        speed_target = 42+9*math.sin(t*.7)
        if scenario in ["VEHICLE_FAILURE", "BMS_FAULT"] or progress>=1:
            speed_target=0
        elif scenario=="DELIVERY_DELAY":
            speed_target=18+4*math.sin(t*.45)
        speed=0 if scenario in ["VEHICLE_FAILURE", "BMS_FAULT"] else smooth(s.get("speed", speed_target), speed_target, .2)
        if speed<.5:
            speed=0
        # Real-time distance traveled; no artificial jumps or automatic route resets.
        distance_traveled=speed*self.interval/3600
        progress=min(1, progress+distance_traveled/route.distance_km)
        soc=s.get("soc", vehicle.baseline_soc)
        if scenario=="LOW_BATTERY":
            soc=smooth(soc, 12, .17)
        elif s.get("previous_scenario")=="LOW_BATTERY" and scenario=="NORMAL_DELIVERY":
            soc=vehicle.baseline_soc  # Explicit demo scenario reset, not normal telemetry physics.
        current=smooth(s.get("current", 42), speed*.9+12 + (95 if scenario=="BATTERY_OVERHEATING" else 0), .16)
        voltage=320+soc*.65
        power=voltage*current/1000
        soc=max(0,soc-power*(self.interval/3600)/65*100)
        battery_target=27+abs(current)*.12 + (10 if scenario=="BATTERY_OVERHEATING" else 0)
        battery_temp=smooth(s.get("battery_temp", 31+i), battery_target, .14)
        motor_temp=smooth(s.get("motor_temp", 51+i), 34+speed*.45+(74 if scenario=="MOTOR_OVERHEATING" else 0), .14)
        temp_target=5+.3*math.sin(t*.3)+(7 if scenario=="CONTAINER_TEMPERATURE_EXCURSION" else 0)+(4.5 if scenario=="DOOR_OPEN" else 0)
        previous_temp=s.get("temp", 10.2 if i==2 and warm_start else 5)
        temp=smooth(previous_temp, temp_target, .12)
        humidity=smooth(s.get("humidity", 48), 48+3*math.sin(t*.2)+(40 if scenario=="HIGH_HUMIDITY" else 0), .16)
        deviation=smooth(s.get("deviation", 0), 2.4 if scenario=="ROUTE_DEVIATION" else 0, .16)
        position=point_on_route(route.planned_route, progress)
        position[0]+=deviation/111.32
        measured_deviation=deviation_km(position, route.planned_route)
        delay=s.get("delay", 18 if i==1 and warm_start else 0)
        delay=max(0, delay + self.interval/60 if scenario=="DELIVERY_DELAY" else delay-self.interval/120)
        remaining=max(0, route.distance_km*(1-progress))
        status="FAULT" if scenario in ["VEHICLE_FAILURE","BMS_FAULT"] else "STOPPED" if speed==0 else "RUNNING"
        delivery_status="DELIVERED" if progress>=1 else "FAILED" if scenario=="VEHICLE_FAILURE" else "DELAYED" if delay>10 else "IN_TRANSIT"
        if progress>=1:
            position=route.planned_route[-1]
        estimated_range=soc/100*280*vehicle.soh/100*(1-max(0,battery_temp-35)*.006)
        timestamp=now.isoformat()
        v={"vehicle_id":vehicle.id,"vehicle_name":vehicle.name,"driver_name":vehicle.driver_name,"latitude":round(position[0],6),"longitude":round(position[1],6),"speed":round(speed,1),"rpm":round(speed*65),"motor_temperature":round(motor_temp,1),"vehicle_status":status,"odometer":round(s.get("odometer",12300+i*840)+distance_traveled,2),"ignition_status":progress<1,"accelerator_position":round(speed/80*100,1),"brake_status":speed==0,"estimated_range":round(estimated_range,1),"dtc_code":"P0A80" if scenario=="VEHICLE_FAILURE" else "NONE","timestamp":timestamp}
        b={"soc":round(soc,2),"soh":vehicle.soh,"pack_voltage":round(voltage,1),"pack_current":round(current,1),"battery_temperature":round(battery_temp,1),"cell_max_voltage":round(3.2+soc*.008+(.16 if scenario=="BMS_FAULT" else .012),3),"cell_min_voltage":round(3.2+soc*.008-.012,3),"charging_status":"DISCHARGING" if speed else "NOT_CHARGING","estimated_range":round(estimated_range,1),"power_consumption":round(power,2),"bms_fault":"CELL_IMBALANCE" if scenario=="BMS_FAULT" else "NONE"}
        profile=profile_or_default(container,profile)
        cold_metrics=cold_chain_metrics(container,profile,temp,previous_temp,s,self.interval)
        c={"container_id":container.id,"shipment_id":container.shipment_id,"medicine_name":container.medicine_name,"batch_number":container.batch_number,"temperature":round(temp,2),"humidity":round(humidity,1),"door_status":"OPEN" if scenario=="DOOR_OPEN" else "CLOSED","tamper_status":"DETECTED" if scenario=="TAMPERING" else "CLEAR","shock_level":4.2 if scenario=="SHOCK_EVENT" else round(.3+.1*math.sin(t),2),"vibration_level":round(speed*.007,2),"min_temperature":profile.min_temperature,"max_temperature":profile.max_temperature,**cold_metrics}
        c["container_status"]="CRITICAL" if temp<c["min_temperature"] or temp>c["max_temperature"] or c["tamper_status"]=="DETECTED" else "WARNING" if humidity>65 or c["door_status"]=="OPEN" or c["shock_level"]>2 or c["predictive_status"]!="SAFE" else "SAFE"
        eta_minutes=remaining/max(speed,25)*60
        d={"delivery_id":delivery.id,"vehicle_id":vehicle.id,"container_id":container.id,"source":route.source,"destination":route.destination,"planned_route":route.planned_route,"current_location":position,"distance_remaining":round(remaining,2),"estimated_arrival_time":(now+timedelta(minutes=eta_minutes)).isoformat(),"delivery_progress":round(progress*100,2),"delay_minutes":round(delay,1),"route_deviation_distance":round(measured_deviation,3),"delivery_status":delivery_status,"route_risk_score":round(min(100,measured_deviation*20+delay),1)}
        trace=list(s.get("actual_route", []))
        if not trace or trace[-1]!=position:
            trace.append(position)
        d["actual_route"]=trace[-240:]
        vehicle.state={"progress":progress,"speed":speed,"soc":soc,"current":current,"battery_temp":battery_temp,"motor_temp":motor_temp,"temp":temp,"humidity":humidity,"deviation":deviation,"delay":delay,"odometer":v["odometer"],"actual_route":trace[-240:],"previous_scenario":scenario,"temperature_trend_c_per_minute":cold_metrics["temperature_trend_c_per_minute"],"excursion_duration_minutes":cold_metrics["excursion_duration_minutes"],"reset_at":s.get("reset_at")}
        snapshot={"vehicle":v,"battery":b,"container":c,"delivery":d,"timestamp":timestamp,"scenario":scenario}
        snapshot["risk"]=self.risk_engine.evaluate(snapshot)
        return snapshot

    def persist(self, db, snapshot, now, incidents=True, synthetic=True):
        v,b,c=snapshot["vehicle"],snapshot["battery"],snapshot["container"]
        vehicle_id=v["vehicle_id"]
        # Trace is available live; historical rows store only telemetry, not ever-growing tracks.
        history={**snapshot,"delivery":{k:x for k,x in snapshot["delivery"].items() if k not in ["actual_route","planned_route"]}}
        db.add(TelemetryHistory(vehicle_id=vehicle_id,timestamp=now,snapshot=history,synthetic=synthetic))
        db.add(VehicleTelemetry(vehicle_id=vehicle_id,timestamp=now,latitude=v["latitude"],longitude=v["longitude"],speed=v["speed"],motor_temperature=v["motor_temperature"],payload=v))
        db.add(BatteryTelemetry(vehicle_id=vehicle_id,timestamp=now,soc=b["soc"],soh=b["soh"],battery_temperature=b["battery_temperature"],pack_current=b["pack_current"],payload=b))
        db.add(ContainerTelemetry(container_id=c["container_id"],timestamp=now,temperature=c["temperature"],humidity=c["humidity"],payload=c))
        if not incidents:
            return
        risk=snapshot["risk"]
        db.add(RiskEvent(vehicle_id=vehicle_id,container_id=c["container_id"],timestamp=now,risk_score=risk["risk_score"],risk_level=risk["risk_level"],explanation=risk))
        active=db.scalars(select(Alert).where(Alert.vehicle_id==vehicle_id,Alert.active==True)).all()
        existing={a.type:a for a in active}
        types=set()
        for factor in risk["contributing_factors"]:
            types.add(factor["type"])
            if factor["type"] in existing:
                alert=existing[factor["type"]]
                if alert.severity!=factor["severity"]:
                    alert.acknowledged=False
                    alert.acknowledged_by=None
                    alert.acknowledged_at=None
                alert.last_seen=now
                alert.severity=factor["severity"]
                alert.reason=factor["reason"]
                alert.telemetry_snapshot=history
            else:
                db.add(Alert(vehicle_id=vehicle_id,container_id=c["container_id"],shipment_id=c["shipment_id"],timestamp=now,last_seen=now,type=factor["type"],severity=factor["severity"],reason=factor["reason"],recommended_action=factor["recommended_action"],telemetry_snapshot=history))
        for alert in active:
            if alert.type not in types:
                alert.active=False

    def tick(self, db, force=False):
        if db.get(SystemSettings,1).simulation_paused and not force:
            return
        self.ticks+=1
        now=utcnow()
        for vehicle in db.scalars(select(Vehicle).order_by(Vehicle.id)):
            if vehicle.telemetry_source=="MQTT":
                continue
            delivery=db.scalar(select(Delivery).where(Delivery.vehicle_id==vehicle.id))
            container=db.get(Container,delivery.container_id)
            profile=db.get(MedicineProfile,container.medicine_profile_id) if container.medicine_profile_id else None
            snapshot=self.advance(vehicle,container,delivery,db.get(Route,delivery.route_id),now,warm_start=not vehicle.state,profile=profile)
            self.persist(db,snapshot,now)
        advance_missions(db,self.interval)
        if self.ticks%1200==0:
            cutoff=now-timedelta(days=30)
            for model in [TelemetryHistory,VehicleTelemetry,BatteryTelemetry,ContainerTelemetry,RiskEvent]:
                db.execute(delete(model).where(model.timestamp<cutoff))
        db.commit()

    def bootstrap_history(self, db):
        if db.scalar(select(TelemetryHistory.id).limit(1)):
            return
        # One hour of clearly synthetic pre-roll to make the initial demonstration useful.
        original_interval=self.interval
        # Resolve the fleet graph once. Re-querying every relationship for all 60
        # samples is harmless with local SQLite but creates hundreds of network
        # round-trips on managed PostgreSQL and can exceed cloud health-check timeouts.
        contexts=[]
        for vehicle in db.scalars(select(Vehicle).order_by(Vehicle.id)):
            delivery=db.scalar(select(Delivery).where(Delivery.vehicle_id==vehicle.id))
            container=db.get(Container,delivery.container_id)
            profile=db.get(MedicineProfile,container.medicine_profile_id) if container.medicine_profile_id else None
            contexts.append((vehicle,container,delivery,db.get(Route,delivery.route_id),profile))
        # Historical timestamps are pre-roll labels; dynamics use the configured tick interval.
        for n in range(60):
            self.ticks=n
            now=utcnow()-timedelta(minutes=60-n)
            for vehicle,container,delivery,route,profile in contexts:
                snapshot=self.advance(vehicle,container,delivery,route,now,warm_start=n==0,profile=profile)
                self.persist(db,snapshot,now,incidents=False)
        db.commit()
        self.interval=original_interval
        self.tick(db,force=True)
