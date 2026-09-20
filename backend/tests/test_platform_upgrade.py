import numpy as np
import pandas as pd
import pytest
from app.ai.engine import FEATURES
from app.ai.training import train_validated_bundle, validate_labelled_frame
from app.database import SessionLocal
from app.models import Route, SensorDevice, Vehicle
from app.services.cold_chain import cold_chain_metrics
from app.services.routing import osrm_route
from app.schemas import SensorPacket


def login(client,email,password):
    result=client.post("/api/auth/login",json={"email":email,"password":password})
    assert result.status_code==200
    return result.json()


def test_profiles_predictions_and_history(authenticated):
    profiles=authenticated.get("/api/medicine-profiles").json()
    assert len(profiles)==5
    assert all(profile["max_excursion_minutes"]>0 for profile in profiles)
    fleet=authenticated.get("/api/overview").json()["fleet"]
    for snapshot in fleet:
        cold=snapshot["container"]
        assert cold["profile_name"]
        assert cold["excursion_duration_minutes"]>=0
        assert 0<=cold["remaining_safe_time_minutes"]<=720
        assert cold["predictive_status"] in {"SAFE","WATCH","ALERT"}
    history=authenticated.get("/api/history?vehicle_id=PHARMA-EV-003&hours=24").json()
    assert {"excursion_duration_minutes","remaining_safe_time_minutes","predicted_temperature"} <= history[-1].keys()


def test_cold_chain_forecast_and_excursion_accumulation():
    container=type("Container",(),{"min_temperature":2,"max_temperature":8})()
    profile=type("Profile",(),{"id":"TEST","name":"Test biologic","min_temperature":2,"max_temperature":8,"warning_margin":.5,"max_excursion_minutes":20,"prediction_horizon_minutes":10,"handling_notes":"test","validated":True})()
    forecast=cold_chain_metrics(container,profile,7.7,7.5,{"temperature_trend_c_per_minute":.1},60)
    assert forecast["predicted_excursion"]
    assert forecast["predictive_status"]=="ALERT"
    excursion=cold_chain_metrics(container,profile,9,8.9,{"excursion_duration_minutes":4},60)
    assert excursion["excursion_duration_minutes"]==5
    assert excursion["remaining_safe_time_minutes"]==15


def test_direct_pdf_and_assistant_report_actions(authenticated):
    pdf=authenticated.get("/api/reports/risk/pdf?hours=24")
    assert pdf.status_code==200
    assert pdf.headers["content-type"]=="application/pdf"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content)>3000
    historical=authenticated.post("/api/assistant",json={"question":"Show the temperature trend for the last 24 hours"}).json()
    assert historical["intent"]=="historical_analytics"
    assert historical["actions"][0]["type"]=="DOWNLOAD_PDF"
    action=authenticated.post("/api/assistant",json={"question":"Download a risk report"}).json()
    assert action["intent"]=="report_action"


def test_role_permissions(client):
    viewer=login(client,"viewer@thermatrace.local","ViewerDemo!2026")
    assert viewer["role"]=="VIEWER"
    assert client.get("/api/overview").status_code==200
    assert client.post("/api/simulation/scenario",json={"vehicle_id":"PHARMA-EV-001","scenario":"NORMAL_DELIVERY"}).status_code==403
    assert client.get("/api/users").status_code==403
    operator=login(client,"operator@thermatrace.local","OperatorDemo!2026")
    assert operator["role"]=="OPERATOR"
    assert client.post("/api/simulation/reset").status_code==403
    login(client,"admin@thermatrace.local","PharmaDemo!2026")


def test_sensor_adapter_marks_data_as_real(authenticated):
    with SessionLocal() as db:
        existing=db.get(SensorDevice,"qa-device")
        if existing: db.delete(existing);db.commit()
    registered=authenticated.post("/api/integrations/mqtt/devices",json={"device_id":"qa-device","vehicle_id":"PHARMA-EV-002","topic":"thermatrace/vehicles/qa-device/telemetry"})
    assert registered.status_code==201
    packet={"device_id":"qa-device","vehicle_id":"PHARMA-EV-002","vehicle":{"speed":31.5},"battery":{"soc":54.2},"container":{"temperature":7.7}}
    ingested=authenticated.post("/api/integrations/mqtt/test-ingest",json=packet)
    assert ingested.status_code==200
    assert ingested.json()["scenario"]=="REAL_SENSOR"
    history=authenticated.get("/api/history?vehicle_id=PHARMA-EV-002&hours=1").json()
    assert history[-1]["synthetic"] is False


def test_osrm_adapter_parses_geojson(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"code":"Ok","routes":[{"distance":12340,"duration":1800,"geometry":{"coordinates":[[73.8,18.5],[73.9,18.6]]}}]}
    monkeypatch.setattr("app.services.routing.httpx.get",lambda *args,**kwargs:Response())
    result=osrm_route([[18.5,73.8],[18.6,73.9]],"https://router.example")
    assert result["provider"]=="OSRM"
    assert result["distance_km"]==12.34
    assert result["planned_route"]==[[18.5,73.8],[18.6,73.9]]


def test_labelled_model_validation_pipeline(tmp_path):
    rng=np.random.default_rng(42); rows=140
    frame=pd.DataFrame({feature:rng.normal(20,4,rows) for feature in FEATURES})
    frame["soc"]=np.linspace(95,5,rows)
    frame["risk_target"]=np.concatenate([np.linspace(5,28,70),np.linspace(65,95,70)])
    clean=validate_labelled_frame(frame)
    csv=tmp_path/"labelled.csv";artifact=tmp_path/"model.joblib";clean.to_csv(csv,index=False)
    metadata=train_validated_bundle(csv,artifact,"qa-labelled-v1")
    assert artifact.exists()
    assert metadata["labelled_data_status"]=="VALIDATED_HOLDOUT"
    assert set(metadata["validation_metrics"]) >= {"mae","r2","high_risk_recall"}


def test_labelled_model_rejects_incomplete_data():
    with pytest.raises(ValueError,match="Missing labelled-data columns"):
        validate_labelled_frame(pd.DataFrame({"soc":[1,2],"risk_target":[1,2]}))
