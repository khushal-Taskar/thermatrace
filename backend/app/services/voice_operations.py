"""Fast, deterministic driver intents grounded in live transport records."""
import re
from sqlalchemy import select

from ..models import RescueMission, Vehicle
from .rescue_dispatch import create_rescue_mission, send_point_message, serialize_message, serialize_mission
from .voice_queries import answer_live_query


def _contains(text, terms):
    return any(term in text for term in terms)


def _driver_name(question):
    patterns = [
        r"(?:मेरा नाम|माझे नाव|my name is)\s+([\w\u0900-\u097f ]{2,40})",
        r"(?:मैं|मी)\s+([\w\u0900-\u097f ]{2,40})\s+(?:बोल रहा|बोलते)",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.I)
        if match:
            return re.split(r"\s+(?:है|आहे|and|और|आणि)\b|[।.!]", match.group(1), maxsplit=1, flags=re.I)[0].strip()[:40]
    return None


def _cause(snapshot, language):
    battery = snapshot["battery"]
    vehicle = snapshot["vehicle"]
    if battery["bms_fault"] != "NONE":
        return "BMS fault recorded" if language == "en" else "बीएमएस में खराबी दर्ज है"
    if battery["battery_temperature"] >= 45:
        return (f"battery temperature is high at {battery['battery_temperature']:.1f}°C" if language == "en"
                else f"बैटरी का तापमान {battery['battery_temperature']:.1f} डिग्री है, जो अधिक है")
    if vehicle["motor_temperature"] >= 85:
        return (f"motor temperature is high at {vehicle['motor_temperature']:.1f}°C" if language == "en"
                else f"मोटर का तापमान {vehicle['motor_temperature']:.1f} डिग्री है, जो अधिक है")
    return "current telemetry does not establish the cause" if language == "en" else "मौजूदा टेलिमेट्री से कारण की पुष्टि नहीं होती"


def _container_turn(question, language, snapshot):
    q = question.lower()
    container = snapshot["container"]
    mentions_container = _contains(q, ["container", "कंटेनर", "medicine", "drug", "दवा", "दवाई", "मेडिसिन", "औषध", "shipment", "शिपमेंट", "batch", "बॅच", "cold chain", "कोल्ड चेन"])
    asks_condition = _contains(q, ["temperature", "तापमान", "humidity", "नमी", "आर्द्रता", "excursion", "door", "दरवाज", "दार", "tamper", "छेड़", "छेड", "shock", "safe time", "सुरक्षित समय", "सुरक्षित वेळ", "predict", "पूर्वानुमान"])
    asks_vehicle = _contains(q, ["battery", "बैटरी", "बॅटरी", "motor", "मोटर", "मोटरची"])
    if asks_vehicle or not (mentions_container or asks_condition):
        return None
    temperature = container["temperature"]
    minimum, maximum = container["min_temperature"], container["max_temperature"]
    safe = minimum <= temperature <= maximum and container["container_status"] == "SAFE"
    remaining = container["remaining_safe_time_minutes"]
    excursion = container["excursion_duration_minutes"]
    predicted = container["predicted_temperature"]
    medicine, batch = container["medicine_name"], container["batch_number"]
    if _contains(q, ["humidity", "नमी", "आर्द्रता"]):
        if language == "mr":
            return f"{container['container_id']} मधील आर्द्रता {container['humidity']:.1f} टक्के आहे. कंटेनर स्थिती {container['container_status']} आहे."
        if language == "hi":
            return f"{container['container_id']} में नमी {container['humidity']:.1f} प्रतिशत है। कंटेनर की स्थिति {container['container_status']} है।"
        return f"{container['container_id']} humidity is {container['humidity']:.1f}%; container status is {container['container_status']}."
    if _contains(q, ["door", "दरवाज", "दार", "tamper", "छेड़", "छेड", "shock", "झटका"]):
        if language == "mr":
            return f"{container['container_id']}: दार {container['door_status']}, छेडछाड {container['tamper_status']}, आणि धक्का {container['shock_level']:.1f} जी. सील आणि पॅकेजिंग तपासा."
        if language == "hi":
            return f"{container['container_id']}: दरवाज़ा {container['door_status']}, छेड़छाड़ {container['tamper_status']}, और झटका {container['shock_level']:.1f} जी है। सील और पैकेजिंग जाँचें।"
        return f"{container['container_id']}: door {container['door_status']}, tamper {container['tamper_status']}, shock {container['shock_level']:.1f} g. Inspect the seal and packaging if an event was detected."
    asks_safe_time = _contains(q, ["safe time", "सुरक्षित समय", "सुरक्षित वेळ", "how long", "कितनी देर", "किती वेळ"])
    asks_temperature = _contains(q, ["temperature", "तापमान"])
    if asks_safe_time and not asks_temperature:
        if language == "mr":
            return f"{medicine} साठी अंदाजे उरलेला सुरक्षित वेळ {remaining:.0f} मिनिटे आहे. मर्यादेबाहेरचा कालावधी {excursion:.1f} मिनिटे आहे. हा अंदाज गुणवत्ता मंजुरी नाही."
        if language == "hi":
            return f"{medicine} के लिए अनुमानित सुरक्षित समय {remaining:.0f} मिनट बचा है। तापमान सीमा से बाहर रहने का समय {excursion:.1f} मिनट है। अंतिम निर्णय गुणवत्ता टीम करेगी।"
        return f"Estimated remaining safe time for {medicine} is {remaining:.0f} minutes; excursion duration is {excursion:.1f} minutes. Quality release requires product-specific review."
    if _contains(q, ["which medicine", "what medicine", "which drug", "what drug", "कौन सी दवा", "कौनसी दवा", "कौन-सी दवा", "कौन सी दवाई", "कौनसी दवाई", "कौन सी मेडिसिन", "कौनसी मेडिसिन", "कौन-सी मेडिसिन", "कोणते औषध", "batch", "बॅच"]):
        if language == "mr":
            return f"{container['container_id']} मध्ये {medicine} आहे. बॅच क्रमांक {batch}; शिपमेंट {container['shipment_id']} आहे."
        if language == "hi":
            return f"{container['container_id']} में {medicine} है। बैच नंबर {batch} और शिपमेंट {container['shipment_id']} है।"
        return f"{container['container_id']} carries {medicine}, batch {batch}, shipment {container['shipment_id']}."
    if language == "mr":
        return (f"{container['container_id']} मध्ये {medicine}, बॅच {batch}, आहे. सध्याचे तापमान {temperature:.1f} अंश सेल्सियस; "
                f"सुरक्षित मर्यादा {minimum:.1f} ते {maximum:.1f} अंश आहे. स्थिती {'सुरक्षित' if safe else 'तपासणी आवश्यक'} आहे. "
                f"मर्यादेबाहेरचा कालावधी {excursion:.1f} मिनिटे, अंदाजे उरलेला सुरक्षित वेळ {remaining:.0f} मिनिटे, "
                f"आणि अंदाजित तापमान {predicted:.1f} अंश आहे. हा अंदाज औषधाच्या गुणवत्तेची हमी नाही.")
    if language == "hi":
        return (f"{container['container_id']} में {medicine}, बैच {batch}, है। अभी तापमान {temperature:.1f} डिग्री है; "
                f"सुरक्षित सीमा {minimum:.1f} से {maximum:.1f} डिग्री है। स्थिति {'सुरक्षित' if safe else 'जाँच आवश्यक'} है। "
                f"सीमा से बाहर रहने का समय {excursion:.1f} मिनट और अनुमानित सुरक्षित समय {remaining:.0f} मिनट है। "
                f"अगला तापमान अनुमान {predicted:.1f} डिग्री है। यह दवा की गुणवत्ता की गारंटी नहीं है।")
    return (f"{container['container_id']} carries {medicine}, batch {batch}. Temperature is {temperature:.1f}°C "
            f"against a {minimum:.1f}–{maximum:.1f}°C band; current status is {container['container_status']}. "
            f"Excursion duration is {excursion:.1f} minutes, estimated remaining safe time is {remaining:.0f} minutes, "
            f"and forecast temperature is {predicted:.1f}°C. This estimate does not certify product quality.")


def operational_turn(db, session, question, language, snapshot):
    """Return (answer, messages, mission) or None for the open-ended assistant."""
    q = question.lower().strip()
    if not snapshot:
        return None
    vehicle_id = snapshot["vehicle"]["vehicle_id"]
    name = _driver_name(question)
    if name:
        session.notes = {**(session.notes or {}), "driver_name": name}
        if language == "mr":
            return f"नमस्कार {name} जी. मी तुमची कशी मदत करू?", [], None
        if language == "en":
            return f"Hello {name}. How can I help with {vehicle_id}?", [], None
        return f"नमस्ते {name} जी। मैं {vehicle_id} के बारे में कैसे मदद कर सकता हूँ?", [], None

    if _contains(q, ["what can you answer", "what can i ask", "help me", "क्या पूछ", "क्या बता", "क्या कर सकते", "काय विचार", "काय सांगू शक"]):
        return {
            "en": "Ask me about battery range and health, medicine and container safety, risk reasons, alerts, route and ETA, fleet history, delays, or rescue status. You can also say: send a rescue request to Dispatch.",
            "mr": "बॅटरी रेंज व आरोग्य, औषध व कंटेनर सुरक्षा, धोक्याची कारणे, सूचना, मार्ग व पोहोचण्याची वेळ, इतिहास, उशीर किंवा बचाव स्थिती विचारा. 'Dispatch ला rescue request पाठवा' असेही सांगू शकता.",
        }.get(language, "आप बैटरी और रेंज, दवा और कंटेनर सुरक्षा, जोखिम की वजह, अलर्ट, रास्ता और ETA, history, delay या rescue status पूछ सकते हैं। आप यह भी बोल सकते हैं: Rescue request Dispatch को भेजो।"), [], None

    if _contains(q, ["history", "historical", "trend", "average", "last hour", "past hour", "इतिहास", "पिछले एक घंटे", "औसत", "मागील तास", "fleet", "सबसे कम", "सबसे ज्यादा", "सर्वात कमी", "सर्वाधिक", "highest risk", "lowest soc", "which shipment", "delayed deliveries", "deliveries delayed", "कौन सी deliveries", "कौन सी डिलीवरी", "कौनसी डिलीवरी", "देरी वाली", "bms faults"]):
        response = answer_live_query(db, session, question, language, snapshot)
        if response:
            answer, topic = response
            session.notes = {**(session.notes or {}), "last_topic": topic}
            return answer, [], None

    dispatch_words = ["message", "notify", "send", "भेज", "संदेश", "मैसेज", "कळव", "पाठव", "बोलो", "सांग"]
    rescue_request = _contains(q, ["rescue request", "send rescue", "dispatch rescue", "rescue vehicle", "replacement request", "रेस्क्यू", "बचाव वाहन", "नई गाड़ी भेज", "बदली वाहन पाठव"])
    wants_b = rescue_request or (_contains(q, ["point b", "पॉइंट बी", "पॉइंट ब", "destination", "डेस्टिनेशन"]) and _contains(q, dispatch_words))
    wants_a = rescue_request or (_contains(q, ["point a", "पॉइंट ए", "पॉइंट अ", "replacement", "रिप्लेसमेंट", "बदली वाहन", "नई गाड़ी", "नवीन गाडी"]) and _contains(q, dispatch_words))
    if wants_a or wants_b:
        delivery = snapshot["delivery"]
        container = snapshot["container"]
        messages = []
        mission = None
        if wants_a:
            mission, _ = create_rescue_mission(db, snapshot)
            vehicle = db.get(Vehicle, vehicle_id)
            if mission.status != "COMPLETED" and vehicle.scenario not in {"VEHICLE_FAILURE", "BMS_FAULT"}:
                vehicle.scenario = "VEHICLE_FAILURE"
                vehicle.state = {**(vehicle.state or {}), "speed": 0, "driver_reported_stop": True}
            if mission.status != "COMPLETED":
                messages.append(send_point_message(
                    db, "A", vehicle_id,
                    f"Replacement requested for {vehicle_id} at {snapshot['vehicle']['latitude']:.5f}, "
                    f"{snapshot['vehicle']['longitude']:.5f}. Assign {mission.replacement_vehicle_id} "
                    f"to collect {container['shipment_id']}; temperature {container['temperature']:.1f}°C. "
                    "Verify container integrity before transfer.",
                    mission.id, session.id,
                ))
        if wants_b:
            messages.append(send_point_message(
                db, "B", vehicle_id,
                f"Delivery delay reported for {container['shipment_id']} on {vehicle_id}. "
                f"Destination: {delivery['destination']}. Current delay {delivery['delay_minutes']:.0f} min; "
                f"distance remaining {delivery['distance_remaining']:.1f} km. "
                "Updated ETA will follow after rescue dispatch.",
                mission.id if mission else None, session.id,
            ))
        recipients = " and ".join(f"Point {message.point}" for message in messages)
        if language == "en":
            answer = f"Messages delivered to the in-app {recipients} inboxes." if messages else "No new dispatch message was sent."
            if mission:
                answer += (f" {mission.replacement_vehicle_id} already completed this shipment's recovery mission." if mission.status == "COMPLETED" else f" {mission.replacement_vehicle_id} is assigned to the stopped vehicle.")
            answer += f" Container remaining-safe-time estimate is {container['remaining_safe_time_minutes']:.0f} minutes, not a product-safety guarantee."
        elif language == "mr":
            answer = f"{recipients} च्या अॅपमधील चॅटमध्ये संदेश पोहोचले." if messages else "नवीन संदेश पाठवला नाही."
            if mission:
                answer += (f" {mission.replacement_vehicle_id} ची बचाव मोहीम आधीच पूर्ण झाली आहे." if mission.status == "COMPLETED" else f" {mission.replacement_vehicle_id} बदली वाहन पाठवले आहे.")
            answer += f" कंटेनरचा अंदाजे सुरक्षित वेळ {container['remaining_safe_time_minutes']:.0f} मिनिटे आहे; औषध सुरक्षित असल्याची हमी नाही."
        else:
            answer = f"{recipients} के ऐप चैट में संदेश पहुँच गए हैं।" if messages else "कोई नया संदेश नहीं भेजा गया।"
            if mission:
                answer += (f" {mission.replacement_vehicle_id} का रेस्क्यू मिशन पहले ही पूरा हो चुका है।" if mission.status == "COMPLETED" else f" {mission.replacement_vehicle_id} रिप्लेसमेंट गाड़ी भेजी गई है।")
            answer += f" कंटेनर का अनुमानित सुरक्षित समय {container['remaining_safe_time_minutes']:.0f} मिनट है; यह दवा की सुरक्षा की गारंटी नहीं है।"
        session.notes = {**(session.notes or {}), "last_topic": "dispatch"}
        return answer, [serialize_message(item) for item in messages], serialize_mission(mission) if mission else None

    if _contains(q, ["replacement status", "rescue status", "replacement कहाँ", "नई गाड़ी कहाँ", "बदली वाहन कुठे", "रिप्लेसमेंट कहाँ"]):
        mission = db.scalar(select(RescueMission).where(RescueMission.incident_vehicle_id == vehicle_id).order_by(RescueMission.id.desc()))
        if not mission:
            answer = {"hi": "इस गाड़ी के लिए अभी कोई replacement mission दर्ज नहीं है।", "mr": "या वाहनासाठी अद्याप बदली वाहन मोहीम नोंदलेली नाही."}.get(language, "No replacement mission is recorded for this vehicle yet.")
        elif language == "mr":
            answer = f"{mission.replacement_vehicle_id} ची स्थिती {mission.status} आहे. बचाव मोहीम {mission.progress:.0f}% पूर्ण झाली आहे; सध्याचा वेग {mission.speed:.1f} किमी प्रति तास आहे."
        elif language == "hi":
            answer = f"{mission.replacement_vehicle_id} की स्थिति {mission.status} है। Rescue mission {mission.progress:.0f}% पूरा है और अभी गति {mission.speed:.1f} किमी प्रति घंटा है।"
        else:
            answer = f"{mission.replacement_vehicle_id} is {mission.status}. The rescue mission is {mission.progress:.0f}% complete and moving at {mission.speed:.1f} km/h."
        session.notes = {**(session.notes or {}), "last_topic": "dispatch"}
        return answer, [], None

    stopped = _contains(q, ["रुक गई", "रुक गया", "बंद पड", "थांबली", "stopped", "broke down", "breakdown"])
    why_stopped = _contains(q, ["क्यों रुकी", "क्यों रुका", "का थांब", "why stopped", "why did", "cause of stop"])
    if (session.notes or {}).get("last_topic") == "breakdown" and q in {"क्यों", "क्यों?", "why", "why?", "कशामुळे", "का"}:
        why_stopped = True
    if not stopped and not why_stopped:
        container_answer = _container_turn(question, language, snapshot)
        if container_answer:
            session.notes = {**(session.notes or {}), "last_topic": "container"}
            return container_answer, [], None
    if stopped or why_stopped:
        vehicle = db.get(Vehicle, vehicle_id)
        if stopped and vehicle.scenario not in {"VEHICLE_FAILURE", "BMS_FAULT"}:
            vehicle.scenario = "VEHICLE_FAILURE"
            vehicle.state = {**(vehicle.state or {}), "speed": 0, "driver_reported_stop": True}
        cause = _cause(snapshot, language)
        session.notes = {**(session.notes or {}), "last_topic": "breakdown"}
        if language == "en":
            return f"I recorded the stop for {vehicle_id}. Telemetry shows {cause}. The exact mechanical cause is not confirmed; stop safely and arrange inspection.", [], None
        if language == "mr":
            return f"{vehicle_id} थांबल्याची नोंद केली. टेलिमेट्रीनुसार {cause}. नेमके तांत्रिक कारण निश्चित झालेले नाही; वाहन सुरक्षितपणे थांबवा.", [], None
        return f"{vehicle_id} के रुकने की सूचना दर्ज की। टेलिमेट्री के अनुसार {cause}। सटीक खराबी की पुष्टि नहीं हुई है; वाहन सुरक्षित रोकें।", [], None

    response = answer_live_query(db, session, question, language, snapshot)
    if response:
        answer, topic = response
        session.notes = {**(session.notes or {}), "last_topic": topic}
        return answer, [], None
    return None
