"""Short conversational answers grounded in the selected live vehicle snapshot."""
from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy import select

from ..models import Alert
from .monitoring import overview, report


def _has(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _reply(language: str, english: str, hindi: str, marathi: str) -> str:
    return {"hi": hindi, "mr": marathi}.get(language, english)


def _risk_cause(risk: dict, language: str) -> str:
    factor = (risk.get("contributing_factors") or [None])[0]
    if not factor:
        return _reply(language, risk.get("reason", "No major breach recorded"),
                      "अभी कोई बड़ा safety breach दर्ज नहीं है", "सध्या मोठा सुरक्षा भंग नोंदलेला नाही")
    value = factor.get("value")
    kind = factor.get("type")
    if kind == "LOW_SOC":
        return _reply(language, f"battery charge is {value:.1f}%", f"बैटरी चार्ज {value:.1f}% है", f"बॅटरी चार्ज {value:.1f}% आहे")
    if kind == "BATTERY_OVERHEAT":
        return _reply(language, f"battery temperature is {value:.1f} degrees", f"बैटरी तापमान {value:.1f} डिग्री है", f"बॅटरी तापमान {value:.1f} अंश आहे")
    if kind == "TEMPERATURE_EXCURSION":
        return _reply(language, f"container temperature is {value:.1f} degrees", f"कंटेनर तापमान {value:.1f} डिग्री है", f"कंटेनर तापमान {value:.1f} अंश आहे")
    return factor.get("reason", risk.get("reason", ""))


def _risk_action(risk: dict, language: str) -> str:
    action = risk.get("recommended_action", "")
    known = {
        "Check range margin and divert to a charging or replacement vehicle point.": (
            "चार्जिंग या बदली गाड़ी की व्यवस्था करें", "चार्जिंग किंवा बदली वाहनाची व्यवस्था करा"),
        "Stop safely, reduce load, and inspect the battery cooling system.": (
            "सुरक्षित जगह रुककर बैटरी कूलिंग जाँचें", "सुरक्षित ठिकाणी थांबून बॅटरी कूलिंग तपासा"),
        "Continue monitoring the delivery.": ("डिलीवरी की निगरानी जारी रखें", "डिलिव्हरीचे निरीक्षण सुरू ठेवा"),
    }
    if action in known and language in {"hi", "mr"}:
        return known[action][0 if language == "hi" else 1]
    return action


def answer_live_query(db, session, question: str, language: str, snapshot: dict) -> tuple[str, str] | None:
    """Return (answer, topic); never mutate telemetry or claim product release."""
    q = question.casefold().strip()
    previous = (session.notes or {}).get("last_topic")
    vehicle = snapshot["vehicle"]
    battery = snapshot["battery"]
    container = snapshot["container"]
    delivery = snapshot["delivery"]
    risk = snapshot["risk"]
    vehicle_id = vehicle["vehicle_id"]

    if _has(q, "नमस्ते", "नमस्कार", "hello", "hi agent", "हैलो"):
        return _reply(language,
            f"Hello. I can check {vehicle_id}'s battery, medicine, risk, alerts, route and ETA. What would you like to know?",
            f"नमस्ते। मैं {vehicle_id} की बैटरी, दवा, जोखिम, अलर्ट, रास्ता और पहुँचने का समय बता सकता हूँ। क्या जानना चाहेंगे?",
            f"नमस्कार. मी {vehicle_id} ची बॅटरी, औषध, धोका, सूचना, मार्ग आणि पोहोचण्याची वेळ सांगू शकतो. काय विचारायचे आहे?",
        ), "greeting"
    if _has(q, "thank", "धन्यवाद", "शुक्रिया", "धन्यवाद"):
        return _reply(language,
            "You're welcome. Ask me another question about this delivery whenever you need to.",
            "ज़रूर। इस डिलीवरी के बारे में अगला सवाल पूछिए।",
            "नक्की. या डिलिव्हरीबद्दल पुढचा प्रश्न विचारा.",
        ), "greeting"

    if _has(q, "history", "historical", "trend", "average", "last hour", "past hour", "इतिहास", "पिछले एक घंटे", "औसत", "कल का", "मागील तास", "सरासरी"):
        hours = 1 if _has(q, "hour", "घंट", "तास") else 24
        kind = "battery" if _has(q, "battery", "soc", "charge", "बैटरी", "बॅटरी", "चार्ज") else "container" if _has(q, "container", "temperature", "humidity", "दवा", "कंटेनर", "तापमान", "नमी") else "risk"
        summary = report(db, kind, vehicle_id, hours)
        field = "soc" if kind == "battery" else "temperature" if kind == "container" else "risk_score"
        stats = summary["statistics"].get(field)
        if not stats:
            return _reply(language,
                f"No persisted {kind} samples are available for {vehicle_id} in the last {hours} hours.",
                f"पिछले {hours} घंटों में {vehicle_id} के {kind} का historical data उपलब्ध नहीं है।",
                f"मागील {hours} तासांत {vehicle_id} चा {kind} इतिहास उपलब्ध नाही.",
            ), "history"
        unit = "%" if field == "soc" else " degrees Celsius" if field == "temperature" else " out of 100"
        return _reply(language,
            f"Across {summary['sample_count']} saved readings in the last {hours} hours, {vehicle_id}'s {field.replace('_', ' ')} averaged {stats['average']}{unit}; minimum {stats['minimum']}, maximum {stats['maximum']}.",
            f"पिछले {hours} घंटों की {summary['sample_count']} readings में {vehicle_id} का {field.replace('_', ' ')} औसतन {stats['average']}{unit} था; न्यूनतम {stats['minimum']} और अधिकतम {stats['maximum']}।",
            f"मागील {hours} तासांच्या {summary['sample_count']} नोंदींमध्ये {vehicle_id} चे {field.replace('_', ' ')} सरासरी {stats['average']}{unit} होते; किमान {stats['minimum']} आणि कमाल {stats['maximum']}.",
        ), "history"

    fleet_question = _has(q, "fleet", "सबसे कम", "सबसे ज्यादा", "सर्वात कमी", "सर्वाधिक", "highest risk", "lowest soc", "which shipment", "which vehicle", "delayed deliveries", "देरी वाली", "उशिरा", "bms faults")
    if fleet_question:
        fleet = overview(db)["fleet"]
        if fleet and _has(q, "lowest", "कम battery", "कम बैटरी", "कम चार्ज", "सर्वात कमी"):
            item = min(fleet, key=lambda s: s["battery"]["soc"])
            name, charge = item["vehicle"]["vehicle_id"], item["battery"]["soc"]
            return _reply(language, f"{name} has the lowest fleet charge at {charge:.1f}%.",
                          f"Fleet में सबसे कम बैटरी {name} की है: {charge:.1f}%।",
                          f"Fleet मध्ये सर्वात कमी बॅटरी {name} ची आहे: {charge:.1f}%।"), "fleet"
        if fleet and _has(q, "risk", "जोखिम", "धोका", "shipment", "शिपमेंट"):
            item = max(fleet, key=lambda s: s["risk"]["risk_score"])
            name, shipment, score = item["vehicle"]["vehicle_id"], item["container"]["shipment_id"], item["risk"]["risk_score"]
            return _reply(language, f"{shipment} on {name} has the highest fleet risk: {score} out of 100.",
                          f"सबसे अधिक जोखिम वाला shipment {shipment}, {name} पर है: 100 में {score}।",
                          f"सर्वाधिक धोका असलेली शिपमेंट {shipment}, {name} मध्ये आहे: 100 पैकी {score}."), "fleet"
        if _has(q, "delay", "देरी", "लेट", "उशीर"):
            delayed = [s for s in fleet if s["delivery"]["delivery_status"] == "DELAYED"]
            names = ", ".join(s["vehicle"]["vehicle_id"] for s in delayed[:5])
            return _reply(language, f"{len(delayed)} deliveries are delayed: {names or 'none'}.",
                          f"{len(delayed)} डिलीवरी में देरी है: {names or 'कोई नहीं'}।",
                          f"{len(delayed)} डिलिव्हरी उशिरा आहेत: {names or 'एकही नाही'}."), "fleet"
        if _has(q, "bms", "fault", "दोष", "बिघाड"):
            faulty = [s for s in fleet if s["battery"]["bms_fault"] != "NONE"]
            names = ", ".join(s["vehicle"]["vehicle_id"] for s in faulty[:5])
            return _reply(language, f"{len(faulty)} vehicles have an active BMS fault: {names or 'none'}.",
                          f"{len(faulty)} गाड़ियों में BMS fault है: {names or 'कोई नहीं'}।",
                          f"{len(faulty)} वाहनांमध्ये BMS दोष आहे: {names or 'एकही नाही'}."), "fleet"

    follow_up = q in {"why", "why?", "क्यों", "क्यों?", "क्यो", "का", "कशामुळे", "what about it", "और", "और?", "आणि", "बताओ", "सांगा"}
    why = _has(q, "why", "reason", "cause", "क्यों", "वजह", "कारण", "कशामुळे", "का आहे")
    if follow_up and previous:
        if previous in {"risk", "battery", "route", "container", "eta", "alerts"}:
            q = f"{previous} {q}"
            why = True
        if previous == "container":
            return _reply(language,
                f"{container['medicine_name']} is at {container['temperature']:.1f} degrees against its {container['min_temperature']:.1f} to {container['max_temperature']:.1f} degree band. Forecast is {container['predicted_temperature']:.1f} degrees; estimated safe time is {container['remaining_safe_time_minutes']:.0f} minutes. This is not a quality release decision.",
                f"{container['medicine_name']} का तापमान {container['temperature']:.1f} डिग्री है; सुरक्षित सीमा {container['min_temperature']:.1f} से {container['max_temperature']:.1f} डिग्री है। अनुमानित अगला तापमान {container['predicted_temperature']:.1f} डिग्री और सुरक्षित समय {container['remaining_safe_time_minutes']:.0f} मिनट है। अंतिम गुणवत्ता निर्णय अलग होगा।",
                f"{container['medicine_name']} चे तापमान {container['temperature']:.1f} अंश आहे; सुरक्षित मर्यादा {container['min_temperature']:.1f} ते {container['max_temperature']:.1f} अंश आहे. पुढचा अंदाज {container['predicted_temperature']:.1f} अंश आणि सुरक्षित वेळ {container['remaining_safe_time_minutes']:.0f} मिनिटे आहे. अंतिम गुणवत्ता निर्णय वेगळा असेल.",
            ), "container"

    if _has(q, "risk", "जोखिम", "खतरा", "धोका", "high", "critical", "गंभीर") and not _has(q, "safe time", "सुरक्षित समय", "सुरक्षित वेळ"):
        causes = _risk_cause(risk, language)
        score = risk["risk_score"]
        action = _risk_action(risk, language)
        if why:
            return _reply(language,
                f"{vehicle_id} is {risk['risk_level']} at {score} out of 100 because {causes}. Recommended action: {action}",
                f"{vehicle_id} का जोखिम 100 में {score}, {risk['risk_level']} है। मुख्य वजह: {causes}। सुझाया कदम: {action}",
                f"{vehicle_id} चा धोका 100 पैकी {score}, {risk['risk_level']} आहे. मुख्य कारण: {causes}. सुचवलेली कृती: {action}",
            ), "risk"
        return _reply(language,
            f"{vehicle_id}'s risk score is {score} out of 100, {risk['risk_level']}. The main factor is {causes}.",
            f"{vehicle_id} का जोखिम 100 में {score}, {risk['risk_level']} है। मुख्य वजह: {causes}।",
            f"{vehicle_id} चा धोका 100 पैकी {score}, {risk['risk_level']} आहे. मुख्य कारण: {causes}.",
        ), "risk"

    asks_battery = _has(q, "battery", "bms", "soc", "charge", "range", "बैटरी", "बॅटरी", "चार्ज", "कितना चल", "किती चाल", "बिजली")
    asks_container = _has(q, "container", "कंटेनर", "medicine", "दवा", "औषध")
    if asks_battery and asks_container:
        cooling = battery["battery_temperature"] >= 45
        return _reply(language,
            f"{vehicle_id}: battery charge {battery['soc']:.1f}% at {battery['battery_temperature']:.1f} degrees; container {container['temperature']:.1f} degrees, safe band {container['min_temperature']:.1f} to {container['max_temperature']:.1f}. {'Stop safely and inspect battery cooling.' if cooling else 'Continue monitoring both systems.'}",
            f"{vehicle_id}: बैटरी चार्ज {battery['soc']:.1f}% और तापमान {battery['battery_temperature']:.1f} डिग्री है। कंटेनर {container['temperature']:.1f} डिग्री है; सुरक्षित सीमा {container['min_temperature']:.1f} से {container['max_temperature']:.1f} डिग्री है। {'सुरक्षित जगह रुककर बैटरी कूलिंग जाँचें।' if cooling else 'दोनों की निगरानी जारी रखें।'}",
            f"{vehicle_id}: बॅटरीची चार्ज पातळी {battery['soc']:.1f}% आणि तापमान {battery['battery_temperature']:.1f} अंश आहे. कंटेनर {container['temperature']:.1f} अंश आहे; सुरक्षित मर्यादा {container['min_temperature']:.1f} ते {container['max_temperature']:.1f} अंश आहे. {'वाहन सुरक्षितपणे थांबवा आणि बॅटरी कूलिंग तपासा.' if cooling else 'दोन्हीचे निरीक्षण सुरू ठेवा.'}",
        ), "battery"
    if asks_battery:
        margin = battery["estimated_range"] - delivery["distance_remaining"]
        cooling = battery["battery_temperature"] >= 45
        if _has(q, "fault", "खराब", "दोष", "बिघाड"):
            fault = battery["bms_fault"]
            return _reply(language,
                f"{vehicle_id}'s BMS fault code is {fault}. Battery temperature is {battery['battery_temperature']:.1f} degrees Celsius.",
                f"{vehicle_id} का BMS fault code {fault} है। बैटरी तापमान {battery['battery_temperature']:.1f} डिग्री है।",
                f"{vehicle_id} चा BMS दोष कोड {fault} आहे. बॅटरीचे तापमान {battery['battery_temperature']:.1f} अंश आहे.",
            ), "battery"
        if _has(q, "range", "रेंज", "reach", "distance", "चल", "दूर", "पोहोच", "पहुँच", "पहुंच") or why:
            caution = margin < 10 or battery["soc"] < 25
            return _reply(language,
                f"Estimated range is {battery['estimated_range']:.1f} km; destination is {delivery['distance_remaining']:.1f} km away. Margin is {margin:.1f} km. {'Keep a charging or replacement option ready; this is only an estimate.' if caution else 'Current range estimate covers the route, but continue monitoring.'}",
                f"अनुमानित रेंज {battery['estimated_range']:.1f} किमी और गंतव्य {delivery['distance_remaining']:.1f} किमी दूर है। अंतर {margin:.1f} किमी है। {'चार्जिंग या दूसरी गाड़ी तैयार रखें; यह केवल अनुमान है।' if caution else 'अभी रेंज पर्याप्त दिखती है, निगरानी जारी रखें।'}",
                f"अंदाजे रेंज {battery['estimated_range']:.1f} किमी आणि गंतव्य {delivery['distance_remaining']:.1f} किमी दूर आहे. फरक {margin:.1f} किमी आहे. {'चार्जिंग किंवा बदली वाहन तयार ठेवा; हा फक्त अंदाज आहे.' if caution else 'सध्या रेंज पुरेशी दिसते; निरीक्षण सुरू ठेवा.'}",
            ), "battery"
        return _reply(language,
            f"{vehicle_id}'s charge is {battery['soc']:.1f}%. Battery health is {battery['soh']:.1f}% and temperature is {battery['battery_temperature']:.1f} degrees Celsius. Estimated range is {battery['estimated_range']:.1f} km. {'Stop safely and inspect battery cooling.' if cooling else ''}",
            f"{vehicle_id} की बैटरी {battery['soc']:.1f}% है। बैटरी health {battery['soh']:.1f}% और तापमान {battery['battery_temperature']:.1f} डिग्री है। अनुमानित रेंज {battery['estimated_range']:.1f} किमी है। {'वाहन सुरक्षित रोकें और बैटरी कूलिंग जाँचें।' if cooling else ''}",
            f"{vehicle_id} ची बॅटरी {battery['soc']:.1f}% आहे. बॅटरी आरोग्य {battery['soh']:.1f}% आणि तापमान {battery['battery_temperature']:.1f} अंश आहे. अंदाजे रेंज {battery['estimated_range']:.1f} किमी आहे. {'वाहन सुरक्षितपणे थांबवा आणि बॅटरी कूलिंग तपासा.' if cooling else ''}",
        ), "battery"

    if _has(q, "alert", "incident", "warning", "अलर्ट", "चेतावनी", "सूचना", "घटना", "इशारा"):
        alerts = list(db.scalars(select(Alert).where(Alert.vehicle_id == vehicle_id, Alert.active.is_(True)).order_by(Alert.timestamp.desc()).limit(3)))
        if not alerts:
            return _reply(language,
                f"There is no active alert for {vehicle_id} right now.",
                f"अभी {vehicle_id} के लिए कोई active alert नहीं है।",
                f"सध्या {vehicle_id} साठी कोणतीही सक्रिय सूचना नाही.",
            ), "alerts"
        items = "; ".join(f"{a.severity} {a.type.replace('_', ' ').lower()}: {a.reason}" for a in alerts)
        return _reply(language,
            f"{vehicle_id} has {len(alerts)} recent active alert(s): {items}.",
            f"{vehicle_id} के {len(alerts)} active alert हैं: {items}।",
            f"{vehicle_id} साठी {len(alerts)} सक्रिय सूचना आहेत: {items}.",
        ), "alerts"

    if _has(q, "route", "deviation", "road", "रास्ता", "मार्ग", "रूट", "भटक", "वळण"):
        deviation = delivery["route_deviation_distance"]
        return _reply(language,
            f"{vehicle_id} is heading from {delivery['source']} to {delivery['destination']}. Route deviation is {deviation:.1f} km; {delivery['distance_remaining']:.1f} km remains.",
            f"{vehicle_id} {delivery['source']} से {delivery['destination']} जा रही है। तय रास्ते से दूरी {deviation:.1f} किमी है और {delivery['distance_remaining']:.1f} किमी बाकी है।",
            f"{vehicle_id} {delivery['source']} येथून {delivery['destination']} कडे जात आहे. ठरलेल्या मार्गापासून अंतर {deviation:.1f} किमी आणि उरलेले अंतर {delivery['distance_remaining']:.1f} किमी आहे.",
        ), "route"

    if _has(q, "eta", "arrive", "arrival", "reach", "destination", "delay", "कब", "कितनी देर में", "पहुँच", "पहुंच", "गंतव्य", "देरी", "लेट", "पोहोच", "उशीर"):
        margin = battery["estimated_range"] - delivery["distance_remaining"]
        eta = delivery.get("estimated_arrival_time")
        try:
            eta_text = datetime.fromisoformat(eta).strftime("%I:%M %p") if eta else "unavailable"
        except ValueError:
            eta_text = "unavailable"
        asks_when = _has(q, "when", "what time", "eta", "कब", "कितनी देर में", "केव्हा", "कधी")
        asks_reachability = bool(re.search(r"\b(?:will|can|could)\b.{0,40}\breach\b", q)) or _has(q, "पहुँच पाए", "पहुंच पाए", "पोहोचेल का")
        if why or (not asks_when and asks_reachability):
            cold_margin = container["remaining_safe_time_minutes"] - max(0, (1-delivery["delivery_progress"]/100)*float(delivery.get("route_duration_minutes") or 60)+delivery["delay_minutes"])
            return _reply(language,
                f"{vehicle_id} has {delivery['distance_remaining']:.1f} km to {delivery['destination']}. Estimated battery margin is {margin:.1f} km and cold-chain time margin is {cold_margin:.0f} minutes. Arrival and product safety are not guaranteed.",
                f"{vehicle_id} को {delivery['destination']} तक {delivery['distance_remaining']:.1f} किमी जाना है। बैटरी की अनुमानित बचत {margin:.1f} किमी और cold-chain समय की बचत {cold_margin:.0f} मिनट है। पहुँचना और दवा की सुरक्षा निश्चित नहीं हैं।",
                f"{vehicle_id} ला {delivery['destination']} पर्यंत {delivery['distance_remaining']:.1f} किमी जायचे आहे. बॅटरीची अंदाजे शिल्लक {margin:.1f} किमी आणि शीतसाखळी वेळेची शिल्लक {cold_margin:.0f} मिनिटे आहे. पोहोचण्याची आणि औषध सुरक्षिततेची हमी नाही.",
            ), "eta"
        return _reply(language,
            f"{vehicle_id} is expected at {delivery['destination']} around {eta_text}. {delivery['distance_remaining']:.1f} km remains and the recorded delay is {delivery['delay_minutes']:.0f} minutes. ETA may change.",
            f"{vehicle_id} के {delivery['destination']} पहुँचने का अनुमान {eta_text} है। {delivery['distance_remaining']:.1f} किमी बाकी और दर्ज देरी {delivery['delay_minutes']:.0f} मिनट है। समय बदल सकता है।",
            f"{vehicle_id} चे {delivery['destination']} येथे पोहोचण्याचे अंदाजे वेळ {eta_text} आहे. {delivery['distance_remaining']:.1f} किमी बाकी आणि नोंदलेला उशीर {delivery['delay_minutes']:.0f} मिनिटे आहे. वेळ बदलू शकते.",
        ), "eta"

    if _has(q, "speed", "motor", "location", "where", "status", "गति", "स्पीड", "मोटर", "कहाँ", "कुठे", "स्थिति", "स्थिती"):
        return _reply(language,
            f"{vehicle_id} is {vehicle['vehicle_status']} at {vehicle['speed']:.1f} km/h. Motor temperature is {vehicle['motor_temperature']:.1f} degrees Celsius. It is heading to {delivery['destination']}.",
            f"{vehicle_id} {vehicle['vehicle_status']} है और गति {vehicle['speed']:.1f} किमी प्रति घंटा है। मोटर तापमान {vehicle['motor_temperature']:.1f} डिग्री है। यह {delivery['destination']} जा रही है।",
            f"{vehicle_id} ची स्थिती {vehicle['vehicle_status']} आहे, वेग {vehicle['speed']:.1f} किमी प्रति तास आहे. मोटर तापमान {vehicle['motor_temperature']:.1f} अंश आहे. ती {delivery['destination']} कडे जात आहे.",
        ), "vehicle"
    return None
