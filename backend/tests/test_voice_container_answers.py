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


def test_voice_conversation_answers_distinct_live_questions_and_follow_up(authenticated):
    started = authenticated.post(
        "/api/voice/sessions", json={"vehicle_id": "PHARMA-EV-001", "language": "hi"}
    )
    assert started.status_code == 201
    session_id = started.json()["id"]

    def ask(text):
        response = authenticated.post(
            f"/api/voice/sessions/{session_id}/message?fast=true",
            json={"text": text, "language": "hi"},
        )
        assert response.status_code == 200
        return response.json()["assistant"]["text"]

    risk = ask("इस गाड़ी का risk high क्यों है?")
    assert "मुख्य वजह" in risk and "जोखिम" in risk
    battery = ask("बैटरी की रेंज कितनी है?")
    assert "रेंज" in battery and "किमी" in battery and "अंतर" in battery and battery != risk
    follow_up = ask("क्यों?")
    assert "रेंज" in follow_up and "किमी" in follow_up and follow_up != risk
    eta = ask("डिलीवरी कब पहुँचेगी?")
    assert "पहुँचने का अनुमान" in eta and "किमी" in eta
    medicine = ask("कंटेनर में कौन सी दवा है?")
    assert "बैच नंबर" in medicine and medicine != eta
    container_follow_up = ask("और?")
    assert "अनुमानित अगला तापमान" in container_follow_up
    greeting = ask("नमस्ते")
    assert "क्या जानना चाहेंगे" in greeting


def test_voice_question_can_switch_vehicle_context(authenticated):
    session_id = authenticated.post(
        "/api/voice/sessions", json={"vehicle_id": "PHARMA-EV-001", "language": "en"}
    ).json()["id"]
    response = authenticated.post(
        f"/api/voice/sessions/{session_id}/message?fast=true",
        json={"text": "What is the battery status of PHARMA-EV-003?", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["vehicle_id"] == "PHARMA-EV-003"
    assert "PHARMA-EV-003" in response.json()["assistant"]["text"]


def test_voice_fleet_history_and_unknown_question_have_distinct_answers(authenticated, monkeypatch):
    monkeypatch.setattr("app.services.voice_agent.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("Local model unavailable")))
    session_id = authenticated.post(
        "/api/voice/sessions", json={"vehicle_id": "PHARMA-EV-001", "language": "hi"}
    ).json()["id"]

    def ask(text):
        response = authenticated.post(
            f"/api/voice/sessions/{session_id}/message?fast=true",
            json={"text": text, "language": "hi"},
        )
        assert response.status_code == 200
        return response.json()["assistant"]["text"]

    fleet = ask("Fleet में सबसे ज्यादा risk किस shipment का है?")
    assert "सबसे अधिक जोखिम वाला shipment" in fleet
    history = ask("पिछले एक घंटे की बैटरी का औसत बताओ")
    assert "readings" in history and "औसतन" in history
    unknown = ask("क्या तुम क्रिकेट स्कोर बता सकते हो?")
    assert "सवाल थोड़ा स्पष्ट" in unknown
    assert unknown != fleet and unknown != history
