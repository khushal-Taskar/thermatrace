"""End-to-end coverage for every supported deterministic voice capability."""


def _start(authenticated, vehicle_id="PHARMA-EV-001", language="hi"):
    response = authenticated.post(
        "/api/voice/sessions",
        json={"vehicle_id": vehicle_id, "language": language},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _ask(authenticated, session_id, question, language="hi"):
    response = authenticated.post(
        f"/api/voice/sessions/{session_id}/message?fast=true",
        json={"text": question, "language": language},
    )
    assert response.status_code == 200, question
    answer = response.json()["assistant"]["text"]
    assert answer
    assert "सवाल थोड़ा स्पष्ट" not in answer, question
    return answer, response.json()


def test_hindi_voice_read_only_capability_matrix(authenticated):
    session_id = _start(authenticated)
    cases = [
        ("नमस्ते", "क्या जानना चाहेंगे"),
        ("मैं क्या पूछ सकता हूँ?", "Rescue request"),
        ("गाड़ी की स्थिति, speed और motor temperature बताओ", "मोटर तापमान"),
        ("बैटरी SOC, health और temperature बताओ", "बैटरी health"),
        ("बैटरी की range destination के लिए पर्याप्त है?", "अंतर"),
        ("क्या कोई BMS fault है?", "BMS fault code"),
        ("अभी यह बताओ गाड़ी के अंदर कौन सी मेडिसिन अवेलेबल है", "बैच नंबर"),
        ("कंटेनर का temperature और safe range बताओ", "सुरक्षित सीमा"),
        ("कंटेनर की humidity बताओ", "नमी"),
        ("कंटेनर का door, tamper और shock status बताओ", "छेड़छाड़"),
        ("दवाई कितनी देर सुरक्षित रहेगी?", "सुरक्षित समय"),
        ("कंटेनर का predicted temperature और excursion बताओ", "अगला तापमान अनुमान"),
        ("इस गाड़ी का risk high क्यों है और recommended action क्या है?", "मुख्य वजह"),
        ("इस गाड़ी के active alerts बताओ", "active alert"),
        ("Route और deviation कितना है?", "तय रास्ते से दूरी"),
        ("Delivery कब पहुँचेगी और delay कितना है?", "पहुँचने का अनुमान"),
        ("पिछले एक घंटे की बैटरी का average बताओ", "औसतन"),
        ("Fleet में सबसे कम battery किस vehicle की है?", "सबसे कम बैटरी"),
        ("सबसे ज्यादा risk किस shipment का है?", "सबसे अधिक जोखिम वाला shipment"),
        ("कौन सी deliveries delayed हैं?", "डिलीवरी में देरी"),
        ("Fleet में किन गाड़ियों में BMS faults हैं?", "BMS fault"),
    ]
    for question, expected in cases:
        answer, _ = _ask(authenticated, session_id, question)
        assert expected in answer, (question, answer)


def test_hindi_driver_breakdown_and_rescue_action_matrix(authenticated, monkeypatch):
    monkeypatch.setattr("app.api.routes.refine_rescue_routes", lambda *args: None)
    session_id = _start(authenticated, vehicle_id="PHARMA-EV-005")

    name, _ = _ask(authenticated, session_id, "मेरा नाम संतोष कुमार है")
    assert "संतोष कुमार" in name

    stopped, _ = _ask(authenticated, session_id, "मेरी गाड़ी रुक गई है")
    assert "रुकने की सूचना दर्ज" in stopped

    cause, _ = _ask(authenticated, session_id, "क्यों?")
    assert "टेलिमेट्री" in cause

    dispatched, payload = _ask(authenticated, session_id, "Rescue request Dispatch को भेजो")
    assert "Point A and Point B" in dispatched
    assert {item["point"] for item in payload["dispatch_messages"]} == {"A", "B"}
    assert payload["rescue_mission"]["replacement_vehicle_id"].startswith("PHARMA-RESCUE-")

    status, _ = _ask(authenticated, session_id, "Replacement कहाँ है और rescue status बताओ")
    assert "Rescue mission" in status


def test_supported_english_and_marathi_examples(authenticated):
    english = _start(authenticated, vehicle_id="PHARMA-EV-002", language="en")
    answer, _ = _ask(authenticated, english, "What medicine and batch is inside the truck?", "en")
    assert "batch" in answer and "shipment" in answer
    answer, _ = _ask(authenticated, english, "Will this vehicle reach its destination safely?", "en")
    assert "battery margin" in answer and "cold-chain time margin" in answer

    marathi = _start(authenticated, vehicle_id="PHARMA-EV-004", language="mr")
    answer, _ = _ask(authenticated, marathi, "कंटेनरमध्ये कोणते औषध आणि बॅच आहे?", "mr")
    assert "बॅच क्रमांक" in answer
    answer, _ = _ask(authenticated, marathi, "बदली वाहन कुठे आहे?", "mr")
    assert "बदली वाहन" in answer
