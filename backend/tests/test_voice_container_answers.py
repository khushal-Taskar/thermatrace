from app.database import SessionLocal
from app.models import VoiceMessage, VoiceSession


def test_voice_assistant_answers_medicine_and_safe_time_from_live_container(authenticated):
    started = authenticated.post(
        "/api/voice/sessions",
        json={"vehicle_id": "PHARMA-EV-003", "language": "hi"},
    )
    assert started.status_code == 201
    session_id = started.json()["id"]

    medicine = authenticated.post(
        f"/api/voice/sessions/{session_id}/message?fast=true",
        json={"text": "कंटेनर में कौन सी दवा और कौन सा batch है?", "language": "hi"},
    )
    assert medicine.status_code == 200
    text = medicine.json()["assistant"]["text"]
    assert "बैच नंबर" in text
    assert "शिपमेंट" in text

    safe_time = authenticated.post(
        f"/api/voice/sessions/{session_id}/message?fast=true",
        json={"text": "दवा कितनी देर सुरक्षित रहेगी?", "language": "hi"},
    )
    assert safe_time.status_code == 200
    safe_text = safe_time.json()["assistant"]["text"]
    assert "सुरक्षित समय" in safe_text
    assert "सीमा से बाहर" in safe_text
    assert "गुणवत्ता टीम" in safe_text

    with SessionLocal() as db:
        assert db.get(VoiceSession, session_id)
        assert len(list(db.query(VoiceMessage).filter(VoiceMessage.session_id == session_id))) == 5


def test_voice_assistant_answers_marathi_container_condition(authenticated):
    session_id = authenticated.post(
        "/api/voice/sessions",
        json={"vehicle_id": "PHARMA-EV-004", "language": "mr"},
    ).json()["id"]
    response = authenticated.post(
        f"/api/voice/sessions/{session_id}/message?fast=true",
        json={"text": "कंटेनरचे तापमान आणि सुरक्षित वेळ सांगा", "language": "mr"},
    )
    assert response.status_code == 200
    text = response.json()["assistant"]["text"]
    assert "सुरक्षित मर्यादा" in text
    assert "उरलेला सुरक्षित वेळ" in text
    assert "गुणवत्तेची हमी नाही" in text
