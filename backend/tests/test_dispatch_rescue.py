from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import DispatchMessage, RescueMission, Vehicle, utcnow
from app.services.monitoring import fleet_snapshot
from app.services.rescue_dispatch import advance_missions, create_rescue_mission


def test_voice_dispatch_creates_two_separate_inboxes_and_moving_replacement(authenticated, monkeypatch):
    monkeypatch.setattr("app.api.routes.refine_rescue_routes", lambda *args: None)
    vehicle_id = "PHARMA-EV-002"
    with SessionLocal() as db:
        vehicle = db.get(Vehicle, vehicle_id)
        original_scenario, original_state = vehicle.scenario, dict(vehicle.state)

    try:
        started = authenticated.post("/api/voice/sessions", json={"vehicle_id": vehicle_id, "language": "hi"})
        assert started.status_code == 201
        assert started.json()["messages"][0]["source"] == "GREETING"
        session_id = started.json()["id"]

        stopped = authenticated.post(
            f"/api/voice/sessions/{session_id}/message?fast=true",
            json={"text": "मेरी गाड़ी रुक गई है, क्यों?", "language": "hi"},
        )
        assert stopped.status_code == 200
        assert stopped.json()["audio_pending"] is True
        assert "पुष्टि" in stopped.json()["assistant"]["text"]

        dispatched = authenticated.post(
            f"/api/voice/sessions/{session_id}/message?fast=true",
            json={"text": "Point B को delay का message भेज दो और Point A को replacement भेजने को बोलो", "language": "hi"},
        )
        assert dispatched.status_code == 200
        result = dispatched.json()
        assert {item["point"] for item in result["dispatch_messages"]} == {"A", "B"}
        assert all(item["status"] == "DELIVERED" for item in result["dispatch_messages"])
        mission = result["rescue_mission"]
        assert mission["replacement_vehicle_id"].startswith("PHARMA-RESCUE-")
        assert mission["status"] == "TO_PICKUP"

        overview = authenticated.get("/api/overview").json()
        assert any(item["id"] == mission["id"] for item in overview["rescue_missions"])
        assert len([item for item in overview["dispatch_messages"] if item["mission_id"] == mission["id"]]) == 2

        with SessionLocal() as db:
            replacement = db.get(RescueMission, mission["id"])
            start_position = list(replacement.position)
            advance_missions(db, 3)
            db.commit()
            assert replacement.position != start_position
            assert replacement.progress > 0
            for _ in range(8):
                advance_missions(db, 3600)
            assert replacement.status == "COMPLETED"
            snapshot = next(item for item in fleet_snapshot(db) if item["vehicle"]["vehicle_id"] == vehicle_id)
            same, created = create_rescue_mission(db, snapshot)
            assert same.id == mission["id"] and not created
            vehicle = db.get(Vehicle, vehicle_id)
            vehicle.state = {**vehicle.state, "reset_at": utcnow().isoformat()}
            another, created = create_rescue_mission(db, snapshot)
            assert created and another.id != mission["id"]
            db.commit()

        point_a = authenticated.get("/api/dispatch/messages?point=A").json()
        assert any(item["mission_id"] == mission["id"] for item in point_a)
        message_id = next(item["id"] for item in point_a if item["mission_id"] == mission["id"])
        read = authenticated.post(f"/api/dispatch/messages/{message_id}/read")
        assert read.status_code == 200
        assert read.json()["status"] == "READ"
        assert authenticated.post(f"/api/voice/sessions/{session_id}/end").status_code == 200
    finally:
        with SessionLocal() as db:
            vehicle = db.get(Vehicle, vehicle_id)
            vehicle.scenario, vehicle.state = original_scenario, original_state
            mission_ids = list(db.scalars(select(RescueMission.id).where(RescueMission.incident_vehicle_id == vehicle_id)))
            db.execute(delete(DispatchMessage).where(DispatchMessage.mission_id.in_(mission_ids)))
            db.execute(delete(RescueMission).where(RescueMission.id.in_(mission_ids)))
            db.commit()


def test_viewer_cannot_send_dispatch_or_start_rescue(client):
    login = client.post("/api/auth/login", json={"email": "viewer@thermatrace.local", "password": "ViewerDemo!2026"})
    assert login.status_code == 200
    assert client.post("/api/dispatch/rescue", json={"vehicle_id": "PHARMA-EV-001"}).status_code == 403
    assert client.post("/api/dispatch/messages", json={"point": "A", "vehicle_id": "PHARMA-EV-001", "text": "Test"}).status_code == 403
