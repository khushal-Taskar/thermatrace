import pytest
from sqlalchemy import select, func
from app.main import app
from app.database import SessionLocal
from app.models import Vehicle, Container, Delivery, Route, TelemetryHistory, Alert, utcnow
from app.schemas import Scenario
from app.simulation.engine import point_on_route, deviation_km
from app.services.auth import hash_password, verify_password


def test_password_security():
    stored=hash_password("test-password")
    assert verify_password("test-password",stored)
    assert not verify_password("wrong",stored)
    assert stored!=hash_password("test-password")


def test_authentication_required(client):
    assert client.get("/api/overview").status_code==401
    assert client.post("/api/auth/login",json={"email":"admin@thermatrace.local","password":"wrong"}).status_code==401
    assert client.post("/api/auth/login",json={"email":"admin@thermatrace.local","password":"wrong"},headers={"origin":"https://untrusted.example"}).status_code==403


def test_seed_and_schema(authenticated):
    result=authenticated.get("/api/overview").json()
    assert len(result["fleet"])==5
    assert {s["vehicle"]["vehicle_id"] for s in result["fleet"]}=={f"PHARMA-EV-{n:03}" for n in range(1,6)}
    assert result["metrics"]["active_deliveries"]>=4
    assert all(0<=s["risk"]["risk_score"]<=100 for s in result["fleet"])
    assert authenticated.get("/api/health").json()["model"]["training_samples"]==2800
    assert authenticated.get("/api/vehicles/unknown").status_code==404
    assert authenticated.get("/api/history?vehicle_id=unknown").status_code==404


@pytest.mark.parametrize("scenario,expected",[("LOW_BATTERY","LOW_SOC"),("BATTERY_OVERHEATING","BATTERY_OVERHEAT"),("MOTOR_OVERHEATING","MOTOR_OVERHEAT"),("CONTAINER_TEMPERATURE_EXCURSION","TEMPERATURE_EXCURSION"),("HIGH_HUMIDITY","HIGH_HUMIDITY"),("DOOR_OPEN","DOOR_OPEN"),("TAMPERING","TAMPERING"),("SHOCK_EVENT","SHOCK_EVENT"),("ROUTE_DEVIATION","ROUTE_DEVIATION"),("DELIVERY_DELAY","DELIVERY_DELAY"),("VEHICLE_FAILURE","VEHICLE_FAILURE"),("BMS_FAULT","BMS_FAULT")])
def test_scenario_risk_correlations(authenticated,scenario,expected):
    with SessionLocal() as db:
        v=db.get(Vehicle,"PHARMA-EV-001")
        d=db.scalar(select(Delivery).where(Delivery.vehicle_id==v.id))
        c,r=db.get(Container,d.container_id),db.get(Route,d.route_id)
        v.scenario=scenario
        v.state={"delay":18} if scenario=="DELIVERY_DELAY" else {}
        for _ in range(35):
            snapshot=app.state.simulator.advance(v,c,d,r,utcnow())
        assert expected in {f["type"] for f in snapshot["risk"]["contributing_factors"]}
        assert snapshot["risk"]["risk_score"]>=31
        assert snapshot["risk"]["recommended_action"]
        assert snapshot["risk"]["feature_contributions"]
        assert snapshot["battery"]["estimated_range"]<=280
        db.rollback()


def test_normal_delivery_and_smooth_motion(authenticated):
    with SessionLocal() as db:
        v=db.get(Vehicle,"PHARMA-EV-001");v.scenario="NORMAL_DELIVERY";v.state={}
        d=db.scalar(select(Delivery).where(Delivery.vehicle_id==v.id))
        c,r=db.get(Container,d.container_id),db.get(Route,d.route_id)
        first=app.state.simulator.advance(v,c,d,r,utcnow())
        second=app.state.simulator.advance(v,c,d,r,utcnow())
        assert second["battery"]["soc"]<first["battery"]["soc"]
        assert second["delivery"]["delivery_progress"]>first["delivery"]["delivery_progress"]
        assert second["vehicle"]["latitude"]!=first["vehicle"]["latitude"]
        assert abs(second["container"]["temperature"]-first["container"]["temperature"])<.2
        assert not second["risk"]["contributing_factors"]
        assert second["risk"]["risk_level"]=="NORMAL"
        db.rollback()


def test_completed_demo_delivery_restarts_and_delayed_vehicle_keeps_moving(authenticated):
    with SessionLocal() as db:
        v=db.get(Vehicle,"PHARMA-EV-001")
        d=db.scalar(select(Delivery).where(Delivery.vehicle_id==v.id))
        c,r=db.get(Container,d.container_id),db.get(Route,d.route_id)
        v.scenario="NORMAL_DELIVERY"
        v.state={"progress":1,"speed":0,"actual_route":[r.planned_route[-1]]}
        restarted=app.state.simulator.advance(v,c,d,r,utcnow())
        assert restarted["vehicle"]["vehicle_status"]=="RUNNING"
        assert restarted["vehicle"]["speed"]>0
        assert 0<restarted["delivery"]["delivery_progress"]<10
        assert restarted["vehicle"]["latitude"]!=r.planned_route[-1][0]

        v.scenario="DELIVERY_DELAY"
        v.state={"progress":.4,"speed":0,"delay":18}
        delayed=app.state.simulator.advance(v,c,d,r,utcnow())
        assert 0<delayed["vehicle"]["speed"]<30
        assert delayed["vehicle"]["vehicle_status"]=="RUNNING"
        assert delayed["delivery"]["delivery_status"]=="DELAYED"
        db.rollback()


def test_route_geometry():
    points=[[18.5,73.8],[18.6,73.9]]
    assert point_on_route(points,.5)==pytest.approx([18.55,73.85])
    assert deviation_km([18.55,73.85],points)<.001
    assert deviation_km([18.60,73.85],points)>1


def test_scenario_api_and_alert_lifecycle(authenticated):
    payload={"vehicle_id":"PHARMA-EV-001","scenario":"TAMPERING"}
    assert authenticated.post("/api/simulation/scenario",json=payload).status_code==200
    alerts=authenticated.get("/api/alerts").json()
    alert=next(a for a in alerts if a["vehicle_id"]==payload["vehicle_id"] and a["type"]=="TAMPERING" and a["active"])
    assert authenticated.post(f"/api/alerts/{alert['id']}/acknowledge").status_code==200
    authenticated.post("/api/simulation/scenario",json=payload)
    latest=[a for a in authenticated.get("/api/alerts").json() if a["vehicle_id"]==payload["vehicle_id"] and a["type"]=="TAMPERING"]
    assert len(latest)==1 and latest[0]["acknowledged"]
    authenticated.post("/api/simulation/scenario",json={**payload,"scenario":"NORMAL_DELIVERY"})
    recovered=next(a for a in authenticated.get("/api/alerts").json() if a["id"]==alert["id"])
    assert not recovered["active"]
    assert authenticated.post("/api/simulation/scenario",json={**payload,"scenario":"INVALID"}).status_code==422


def test_history_and_exact_report_statistics(authenticated):
    rows=authenticated.get("/api/history?vehicle_id=PHARMA-EV-001&hours=24").json()
    assert len(rows)>=60
    assert rows[0]["timestamp"]<=rows[-1]["timestamp"]
    for kind in ["shipment","vehicle","battery","container","risk","incident"]:
        report=authenticated.get(f"/api/reports/{kind}?vehicle_id=PHARMA-EV-001").json()
        assert report["sample_count"]>=len(rows)
        assert report["statistics"]
    with SessionLocal() as db:
        actual=db.scalar(select(func.avg(TelemetryHistory.snapshot["battery"]["soc"].as_float())).where(TelemetryHistory.vehicle_id=="PHARMA-EV-001"))
    report=authenticated.get("/api/reports/battery?vehicle_id=PHARMA-EV-001").json()
    assert report["statistics"]["soc"]["average"]==round(actual,2)


@pytest.mark.parametrize("question,intent",[("Which shipment is highest risk?","highest_risk"),("Why is Vehicle V03 critical?","vehicle_risk"),("Show temperature incidents.","temperature_incidents"),("Which vehicle has the lowest SOC?","lowest_soc"),("Which deliveries are delayed?","delayed_deliveries"),("Show BMS faults.","bms_faults")])
def test_local_assistant(authenticated,question,intent):
    result=authenticated.post("/api/assistant",json={"question":question}).json()
    assert result["intent"]==intent
    assert result["answer"]
    assert result["timestamp"]


def test_settings_and_pause(authenticated):
    initial=authenticated.get("/api/settings").json()
    assert authenticated.put("/api/settings",json={**initial,"min_temperature":10,"max_temperature":2}).status_code==422
    assert authenticated.put("/api/settings",json={**initial,"simulation_paused":True}).status_code==200
    with SessionLocal() as db:
        before=db.scalar(select(func.count(TelemetryHistory.id)))
        app.state.simulator.tick(db)
        assert db.scalar(select(func.count(TelemetryHistory.id)))==before
    authenticated.put("/api/settings",json=initial)


def test_authenticated_websocket(authenticated):
    ticket=authenticated.post("/api/ws-ticket").json()["ticket"]
    with authenticated.websocket_connect(f"/ws/telemetry?ticket={ticket}",headers={"origin":"http://localhost:3100"}) as ws:
        snapshot=ws.receive_json()
        assert len(snapshot["fleet"])==5
        authenticated.post("/api/simulation/scenario",json={"vehicle_id":"PHARMA-EV-005","scenario":"BMS_FAULT"})
        changed=ws.receive_json()
        assert next(s for s in changed["fleet"] if s["vehicle"]["vehicle_id"]=="PHARMA-EV-005")["battery"]["bms_fault"]=="CELL_IMBALANCE"
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with authenticated.websocket_connect(f"/ws/telemetry?ticket={ticket}"):
            pass


def test_logout_revokes_session(authenticated):
    assert authenticated.post("/api/auth/logout").status_code==200
    assert authenticated.get("/api/auth/me").status_code==401
