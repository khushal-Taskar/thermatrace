from app.database import SessionLocal
from app.models import VoiceMessage, VoiceSession
from app.services.voice_agent import _grounding, synthesize_answer


def test_voice_session_text_turn_and_structured_notes(authenticated,monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.generate_answer",
        lambda db,session,text,language:(
            "PHARMA-EV-003 has a cold-chain warning based on current telemetry.",
            "PHARMA-EV-003",
            {"timestamp":"2026-09-20T10:00:00+00:00"},
        ),
    )
    monkeypatch.setattr("app.api.routes.synthesize_answer",lambda text,language:(None,language,None))
    created=authenticated.post("/api/voice/sessions",json={"vehicle_id":"PHARMA-EV-003","language":"en"})
    assert created.status_code==201
    session_id=created.json()["id"]
    turn=authenticated.post(f"/api/voice/sessions/{session_id}/message",json={"text":"Will vehicle 3 reach the destination?","language":"en"})
    assert turn.status_code==200
    payload=turn.json()
    assert payload["vehicle_id"]=="PHARMA-EV-003"
    assert payload["audio_fallback"]=="BROWSER_SPEECH"
    assert "cold-chain warning" in payload["assistant"]["text"]
    completed=authenticated.post(f"/api/voice/sessions/{session_id}/end")
    assert completed.status_code==200
    note=completed.json()
    assert note["status"]=="COMPLETED"
    assert note["notes"]["raw_audio_retained"] is False
    assert note["notes"]["key_facts"]
    detail=authenticated.get(f"/api/voice/sessions/{session_id}").json()
    assert [message["role"] for message in detail["messages"]]==["ASSISTANT","USER","ASSISTANT"]
    with SessionLocal() as db:
        assert db.get(VoiceSession,session_id).ended_at is not None
        assert len(list(db.query(VoiceMessage).filter_by(session_id=session_id)))==3


def test_voice_audio_accepts_browser_codec_content_type(authenticated,monkeypatch):
    monkeypatch.setattr("app.api.routes.transcribe_audio",lambda payload,suffix,language:("What is the battery status?","en"))
    monkeypatch.setattr(
        "app.api.routes.generate_answer",
        lambda db,session,text,language:("Battery telemetry is available.",session.vehicle_id,{"timestamp":"2026-09-20T10:00:00+00:00"}),
    )
    monkeypatch.setattr("app.api.routes.synthesize_answer",lambda text,language:(None,language,None))
    created=authenticated.post("/api/voice/sessions",json={"vehicle_id":"PHARMA-EV-001","language":"en"})
    session_id=created.json()["id"]
    turn=authenticated.post(
        f"/api/voice/sessions/{session_id}/turn",
        files={"audio":("turn.webm",b"browser-recording","audio/webm;codecs=opus")},
        data={"language":"en"},
    )
    assert turn.status_code==200
    assert turn.json()["operator"]["text"]=="What is the battery status?"


def test_voice_grounding_has_reachability(authenticated):
    with SessionLocal() as db:
        evidence,vehicle_id=_grounding(db,"PHARMA-EV-001","Can it reach the destination?")
    assert vehicle_id=="PHARMA-EV-001"
    reach=evidence["selected_vehicle"]["reachability"]
    assert reach["assessment"] in {"LIKELY_TO_REACH","MAY_REACH_WITH_RISK","INTERVENTION_REQUIRED"}
    assert "range_margin_km" in reach and "cold_chain_time_margin_minutes" in reach


def test_viewer_can_read_but_cannot_start_voice_session(client):
    login=client.post("/api/auth/login",json={"email":"viewer@thermatrace.local","password":"ViewerDemo!2026"})
    assert login.status_code==200
    assert client.get("/api/voice/sessions").status_code==200
    assert client.post("/api/voice/sessions",json={"vehicle_id":"PHARMA-EV-001","language":"auto"}).status_code==403


def test_marathi_turn_uses_audited_template_and_neural_voice(authenticated,monkeypatch):
    monkeypatch.setattr("app.api.routes.synthesize_answer",lambda text,language:("bXAz",language,"audio/mpeg"))
    created=authenticated.post("/api/voice/sessions",json={"vehicle_id":"PHARMA-EV-004","language":"mr"})
    assert created.status_code==201
    assert created.json()["language"]=="mr"
    turn=authenticated.post(
        f"/api/voice/sessions/{created.json()['id']}/message",
        json={"text":"बॅटरी आणि कंटेनरची स्थिती सांगा.","language":"mr"},
    )
    assert turn.status_code==200
    answer=turn.json()["assistant"]["text"]
    assert "बॅटरीची चार्ज पातळी" in answer
    assert "वाहन सुरक्षितपणे थांबवा" in answer
    assert "Stop safely" not in answer
    assert turn.json()["spoken_language"]=="mr"
    assert turn.json()["audio_base64"]=="bXAz"
    assert turn.json()["audio_mime"]=="audio/mpeg"
    assert turn.json()["audio_fallback"] is None
    assert authenticated.post(f"/api/voice/sessions/{created.json()['id']}/end").status_code==200


def test_marathi_synthesis_uses_configured_neural_voice(monkeypatch):
    class FakeCommunicate:
        def __init__(self,text,voice,rate):
            assert "वाहनाची स्थिती" in text
            assert voice=="mr-IN-AarohiNeural"
            assert rate=="-8%"

        def stream_sync(self):
            yield {"type":"WordBoundary","text":"वाहनाची"}
            yield {"type":"audio","data":b"marathi-mp3"}

    monkeypatch.setattr("edge_tts.Communicate",FakeCommunicate)
    audio,language,mime=synthesize_answer("वाहनाची स्थिती सांगा.","mr")
    assert audio=="bWFyYXRoaS1tcDM="
    assert language=="mr"
    assert mime=="audio/mpeg"
