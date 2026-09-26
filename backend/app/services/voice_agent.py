"""Local, database-grounded voice assistant services.

Audio is processed in temporary files and removed immediately. Conversation
text and structured notes are persisted; raw microphone audio is not retained.
"""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import httpx
from sqlalchemy import select

from ..ai.assistant import answer_question
from ..config import settings
from ..models import Alert, VoiceMessage, VoiceSession, utcnow
from .monitoring import overview

_transcriber=None
_transcriber_lock=threading.Lock()
_voices={}
_voices_lock=threading.Lock()


def _voice_dir() -> Path:
    path=Path(settings.voice_model_dir)
    if not path.is_absolute():
        path=Path(__file__).resolve().parents[2]/path
    return path


def runtime_status() -> dict:
    ollama=False
    installed_models=[]
    error=None
    try:
        response=httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags",timeout=2)
        response.raise_for_status()
        installed_models=[item.get("name","") for item in response.json().get("models",[])]
        ollama=any(name.split(":")[0:2]==settings.ollama_model.split(":")[0:2] or name.startswith(settings.ollama_model) for name in installed_models)
    except Exception as exc:
        error=str(exc)
    directory=_voice_dir()
    try:
        import edge_tts  # noqa: F401
        online_text_to_speech=settings.voice_online_tts_enabled
    except ImportError:
        online_text_to_speech=False
    voices={
        "hi":(directory/f"{settings.voice_hindi_model}.onnx").exists(),
        "en":(directory/f"{settings.voice_english_model}.onnx").exists(),
        "mr":online_text_to_speech,
    }
    try:
        import faster_whisper  # noqa: F401
        speech_to_text=True
    except ImportError:
        speech_to_text=False
    try:
        import piper  # noqa: F401
        piper_text_to_speech=True
    except ImportError:
        piper_text_to_speech=False
    text_to_speech=piper_text_to_speech or online_text_to_speech
    ready=ollama and speech_to_text
    return {
        "ready":ready,
        "ollama":ollama,
        "ollama_model":settings.ollama_model,
        "installed_models":installed_models,
        "speech_to_text":speech_to_text,
        "whisper_model":settings.voice_whisper_model,
        "whisper_device":settings.voice_whisper_device,
        "text_to_speech":text_to_speech,
        "voices":voices,
        "raw_audio_stored":settings.voice_store_audio,
        "error":error,
    }


def transcribe_audio(payload: bytes, suffix: str=".webm", language: str="auto") -> tuple[str,str]:
    global _transcriber
    if not payload:
        raise ValueError("The microphone recording was empty")
    with _transcriber_lock:
        if _transcriber is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Microphone transcription is available in the local desktop deployment. "
                    "Type the question here and the cloud agent will still answer and speak it."
                ) from exc
            _transcriber=WhisperModel(
                settings.voice_whisper_model,
                device=settings.voice_whisper_device,
                compute_type=settings.voice_whisper_compute_type,
            )
    path=None
    try:
        with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as handle:
            handle.write(payload)
            path=handle.name
        segments,info=_transcriber.transcribe(
            path,
            language=None if language=="auto" else language,
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text=" ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not text:
            raise ValueError("No speech was detected. Please speak closer to the microphone and try again.")
        detected=(info.language or language or "en").split("-")[0]
        return text,detected
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


def _selected_snapshot(db, vehicle_id: str | None, question: str) -> tuple[dict,dict | None,str | None]:
    data=overview(db)
    match=re.search(r"(?:pharma[- ]ev[- ]|vehicle\s+v?|\bv)(\d{1,3})",question.lower())
    mentioned=f"PHARMA-EV-{int(match.group(1)):03}" if match else None
    selected_id=mentioned or vehicle_id
    snapshot=next((item for item in data["fleet"] if item["vehicle"]["vehicle_id"]==selected_id),None)
    return data,snapshot,selected_id


def _grounding(db, vehicle_id: str | None, question: str) -> tuple[dict,str | None]:
    data,snapshot,selected_id=_selected_snapshot(db,vehicle_id,question)
    deterministic=answer_question(db,question)
    evidence={
        "timestamp":data["timestamp"],
        "fleet_metrics":data["metrics"],
        "structured_answer":deterministic["answer"],
        "active_alerts":[{
            "vehicle_id":a["vehicle_id"],"type":a["type"],"severity":a["severity"],
            "reason":a["reason"],"recommended_action":a["recommended_action"]
        } for a in data["alerts"] if a["active"]][:8],
    }
    if snapshot:
        battery=snapshot["battery"];delivery=snapshot["delivery"];container=snapshot["container"]
        range_margin=round(battery["estimated_range"]-delivery["distance_remaining"],1)
        eta_minutes=max(0,round((1-delivery["delivery_progress"]/100)*float(delivery.get("route_duration_minutes") or 60)+delivery["delay_minutes"]))
        cold_margin=round(container["remaining_safe_time_minutes"]-eta_minutes,1)
        cold_unsafe=bool(container.get("outside_safe_range")) or container.get("container_status")=="CRITICAL"
        if cold_unsafe or snapshot["risk"]["risk_level"]=="CRITICAL":
            reachability="INTERVENTION_REQUIRED"
        elif range_margin>=10 and cold_margin>=10:
            reachability="LIKELY_TO_REACH"
        elif range_margin>=0 and cold_margin>=0:
            reachability="MAY_REACH_WITH_RISK"
        else:
            reachability="INTERVENTION_REQUIRED"
        evidence["selected_vehicle"]={
            "vehicle":snapshot["vehicle"],"battery":battery,"container":container,
            "delivery":{key:delivery.get(key) for key in ["destination","distance_remaining","estimated_arrival_time","delivery_progress","delay_minutes","route_deviation_distance","delivery_status","route_risk_score"]},
            "risk":snapshot["risk"],
            "reachability":{"assessment":reachability,"range_margin_km":range_margin,"estimated_trip_minutes":eta_minutes,"cold_chain_time_margin_minutes":cold_margin},
        }
    return evidence,selected_id


def _fallback_answer(evidence: dict, language: str="en") -> str:
    selected=evidence.get("selected_vehicle")
    if not selected:
        return evidence["structured_answer"]
    vehicle=selected["vehicle"];battery=selected["battery"];container=selected["container"];delivery=selected["delivery"];reach=selected["reachability"]
    if language=="mr":
        statuses={"RUNNING":"चालू","IDLE":"निष्क्रिय","STOPPED":"थांबलेले","FAULT":"बिघाडाच्या","OFFLINE":"ऑफलाइन"}
        levels={"NORMAL":"सामान्य","WARNING":"इशारा","HIGH":"उच्च","CRITICAL":"गंभीर"}
        assessments={"LIKELY_TO_REACH":"सुरक्षितपणे पोहोचण्याची शक्यता चांगली","MAY_REACH_WITH_RISK":"पोहोचू शकते, परंतु धोका आहे","INTERVENTION_REQUIRED":"तातडीचा हस्तक्षेप आवश्यक"}
        actions={
            "Continue monitoring the delivery.":"डिलिव्हरीचे निरीक्षण सुरू ठेवा.",
            "Review current telemetry and compare with recent history.":"सध्याची टेलिमेट्री तपासा आणि अलीकडील इतिहासाशी तुलना करा.",
            "Notify receiving facility and review remaining cooling capacity.":"स्वीकारणाऱ्या केंद्राला कळवा आणि उरलेली शीतकरण क्षमता तपासा.",
            "Check range margin and divert to a charging or replacement vehicle point.":"उपलब्ध अंतर तपासा आणि चार्जिंग केंद्राकडे वळवा किंवा बदली वाहनाची व्यवस्था करा.",
            "Arrange a vehicle transfer before battery depletion.":"बॅटरी संपण्यापूर्वी शिपमेंट दुसऱ्या वाहनात हलवण्याची व्यवस्था करा.",
            "Stop safely, reduce load, and inspect the battery cooling system.":"वाहन सुरक्षितपणे थांबवा, भार कमी करा आणि बॅटरीची शीतकरण यंत्रणा तपासा.",
            "Reduce speed and inspect motor cooling at a safe stop.":"वेग कमी करा आणि सुरक्षित ठिकाणी थांबून मोटरची शीतकरण यंत्रणा तपासा.",
            "Restore refrigeration; quarantine affected shipment for product-specific quality review.":"शीतकरण पुन्हा सुरू करा आणि उत्पादन-विशिष्ट गुणवत्ता तपासणीसाठी शिपमेंट वेगळे ठेवा.",
            "Inspect refrigeration now and prepare an intervention before the product-specific limit is crossed.":"शीतकरण यंत्रणा तातडीने तपासा आणि औषधाची मर्यादा ओलांडण्यापूर्वी हस्तक्षेपाची तयारी करा.",
            "Inspect seals and desiccant; verify packaging integrity.":"सील आणि आर्द्रता शोषक तपासा तसेच पॅकेजिंग सुरक्षित असल्याची खात्री करा.",
            "Close the door and check temperature recovery.":"कंटेनरचे दार बंद करा आणि तापमान पुन्हा सुरक्षित होत आहे का ते तपासा.",
            "Secure the shipment and initiate a custody investigation.":"शिपमेंट सुरक्षित करा आणि ताबा-साखळीची चौकशी सुरू करा.",
            "Inspect fragile pharmaceutical packaging and record the incident.":"नाजूक औषधी पॅकेजिंग तपासा आणि घटनेची नोंद करा.",
            "Contact driver and verify the deviation and shipment security.":"चालकाशी संपर्क साधा आणि मार्ग बदल तसेच शिपमेंटची सुरक्षा तपासा.",
            "Dispatch roadside support and protect the cold chain with a vehicle transfer.":"रस्त्यावरील मदत पाठवा आणि वाहन बदलून शीतसाखळी सुरक्षित ठेवा.",
            "Stop safely and request qualified battery-system inspection.":"वाहन सुरक्षितपणे थांबवा आणि पात्र तंत्रज्ञाकडून बॅटरी प्रणालीची तपासणी करून घ्या.",
            "Contact the driver and verify ETA and cooling availability.":"चालकाशी संपर्क साधा आणि पोहोचण्याची अंदाजित वेळ तसेच शीतकरणाची उपलब्धता तपासा.",
        }
        return (
            f"{vehicle['vehicle_id']} सध्या {statuses.get(vehicle['vehicle_status'],vehicle['vehicle_status'])} स्थितीत आहे. "
            f"बॅटरीची चार्ज पातळी {battery['soc']:.1f} टक्के आहे आणि बॅटरीचे तापमान {battery['battery_temperature']:.1f} अंश सेल्सियस आहे. "
            f"कंटेनरचे तापमान {container['temperature']:.1f} अंश सेल्सियस आहे; सुरक्षित मर्यादा {container['min_temperature']:.1f} ते {container['max_temperature']:.1f} अंश सेल्सियस आहे. "
            f"गंतव्य {delivery['distance_remaining']:.1f} किमी दूर आहे. पोहोचण्याचा अंदाज: {assessments.get(reach['assessment'],reach['assessment'])}. "
            f"सध्याचा धोका शंभर पैकी {selected['risk']['risk_score']} ({levels.get(selected['risk']['risk_level'],selected['risk']['risk_level'])}) आहे. "
            f"शिफारस: {actions.get(selected['risk']['recommended_action'],selected['risk']['recommended_action'])}"
        )
    if language=="hi":
        return (
            f"{vehicle['vehicle_id']} अभी {vehicle['vehicle_status']} स्थिति में है। बैटरी एस ओ सी {battery['soc']:.1f} प्रतिशत और तापमान "
            f"{battery['battery_temperature']:.1f} डिग्री सेल्सियस है। कंटेनर तापमान {container['temperature']:.1f} डिग्री है, जबकि सुरक्षित सीमा "
            f"{container['min_temperature']:.1f} से {container['max_temperature']:.1f} डिग्री है। गंतव्य {delivery['distance_remaining']:.1f} किलोमीटर दूर है। "
            f"पहुँचने का आकलन {reach['assessment'].replace('_',' ').lower()} है। वर्तमान जोखिम {selected['risk']['risk_score']} प्रतिशत, "
            f"{selected['risk']['risk_level']} स्तर पर है। सुझाया कदम: {selected['risk']['recommended_action']}"
        )
    return (
        f"{vehicle['vehicle_id']} is {vehicle['vehicle_status']}. Battery SOC is {battery['soc']:.1f}% at "
        f"{battery['battery_temperature']:.1f}°C. Container temperature is {container['temperature']:.1f}°C "
        f"against its {container['min_temperature']:.1f}–{container['max_temperature']:.1f}°C range. "
        f"The destination is {delivery['distance_remaining']:.1f} km away. Reachability is {reach['assessment'].replace('_',' ').lower()}. "
        f"Current risk is {selected['risk']['risk_level']} at {selected['risk']['risk_score']}/100. "
        f"{selected['risk']['recommended_action']}"
    )


def _prompt_evidence(evidence: dict) -> dict:
    """Keep the local-model prompt small and limited to speakable evidence."""
    selected=evidence.get("selected_vehicle")
    compact={
        "timestamp":evidence["timestamp"],
        "fleet_metrics":evidence["fleet_metrics"],
        "database_answer":evidence["structured_answer"],
        "active_alerts":evidence["active_alerts"][:4],
    }
    if selected:
        vehicle=selected["vehicle"];battery=selected["battery"];container=selected["container"]
        compact["selected_vehicle"]={
            "vehicle_id":vehicle["vehicle_id"],
            "vehicle_status":vehicle["vehicle_status"],
            "soc_percent":round(battery["soc"],1),
            "battery_temperature_c":round(battery["battery_temperature"],1),
            "estimated_range_km":round(battery["estimated_range"],1),
            "container_temperature_c":round(container["temperature"],1),
            "safe_temperature_c":[round(container["min_temperature"],1),round(container["max_temperature"],1)],
            "remaining_safe_time_minutes":round(container["remaining_safe_time_minutes"],1),
            "destination":selected["delivery"]["destination"],
            "distance_remaining_km":round(selected["delivery"]["distance_remaining"],1),
            "delay_minutes":selected["delivery"]["delay_minutes"],
            "risk_score":selected["risk"]["risk_score"],
            "risk_level":selected["risk"]["risk_level"],
            "recommended_action":selected["risk"]["recommended_action"],
            "reachability":selected["reachability"],
        }
    return compact


def _answer_is_grounded(answer: str, evidence: dict) -> bool:
    """Reject fluent local-model answers that omit or contradict safety facts."""
    selected=evidence.get("selected_vehicle")
    if not answer or not selected:
        return bool(answer)
    if answer.rstrip()[-1:] not in {".","!","?","।","؟"}:
        return False
    lowered=answer.lower()
    vehicle_id=selected["vehicle"]["vehicle_id"].lower()
    if vehicle_id not in lowered:
        return False
    expected=[
        f"{selected['battery']['soc']:.1f}",
        f"{selected['container']['temperature']:.1f}",
        str(selected["risk"]["risk_score"]),
        f"{selected['delivery']['distance_remaining']:.1f}",
    ]
    if sum(value in answer for value in expected)<2:
        return False
    if selected["risk"]["risk_level"]=="CRITICAL" and not any(term in lowered for term in ["critical","intervention","तुरंत","गंभीर","जोखिम"]):
        return False
    return True


def generate_answer(db, session: VoiceSession, question: str, language: str) -> tuple[str,str | None,dict]:
    evidence,selected_id=_grounding(db,session.vehicle_id,question)
    if selected_id and evidence.get("selected_vehicle"):
        session.vehicle_id=selected_id
    language_names={"hi":"Hindi","en":"English","mr":"Marathi"}
    requested=language_names.get(language,"the same language and style as the operator")
    system=(
        "You are ThermaTrace's AI Driver Voice Agent for pharmaceutical logistics. You are an AI, never claim to be a real driver. "
        "Answer only from the supplied live system evidence. Never invent readings, locations, causes, or guarantees. "
        "State uncertainty when evidence is insufficient. Keep spoken answers under 90 words. Explain acronyms simply. "
        "For destination questions, use the reachability assessment and mention the main battery and cold-chain margins. "
        f"Respond in {requested}. Do not use markdown tables or bullet symbols because the answer will be spoken."
    )
    factual_draft=_fallback_answer(evidence,language)
    # The compact model is reliable for Hindi/English intent wording but its
    # Marathi translation can drift. Use the audited localized safety template
    # so operational values and instructions remain clear and exact.
    if language=="mr":
        return factual_draft,selected_id,evidence
    prompt_evidence=_prompt_evidence(evidence)
    if language not in {"hi","en"}:
        messages=[{"role":"system","content":(
            f"Translate the supplied pharmaceutical vehicle status into natural {requested}. Output only the translation in under 70 words. "
            "Keep the vehicle ID, every number, risk level, reachability assessment and recommended action unchanged. Do not add facts."
        )},{"role":"user","content":factual_draft}]
    else:
        messages=[{"role":"system","content":system},{"role":"user","content":(
            f"LIVE FACTS:\n{json.dumps(prompt_evidence,ensure_ascii=False)}\n\n"
            f"FACTUAL DRAFT:\n{factual_draft}\n\nOPERATOR QUESTION:\n{question}\n\n"
            "Answer the question using the exact readings and safety assessment above. Preserve the vehicle ID, numbers, risk level, and action."
        )}]
    try:
        response=httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json={"model":settings.ollama_model,"messages":messages,"stream":False,"keep_alive":"30m","options":{"temperature":0.05,"num_predict":280 if language not in {"hi","en"} else 180,"num_ctx":2048}},
            timeout=4,
        )
        response.raise_for_status()
        answer=response.json().get("message",{}).get("content","").strip()
        if not _answer_is_grounded(answer,evidence):
            raise ValueError("Local model answer did not preserve the grounded safety evidence")
    except Exception:
        answer=_fallback_answer(evidence,language)
    return answer,selected_id,evidence


def synthesize_answer(text: str, language: str) -> tuple[str | None,str,str | None]:
    code=language.split("-")[0].lower()
    if code=="mr" and settings.voice_online_tts_enabled:
        try:
            import edge_tts
            audio=bytearray()
            communicate=edge_tts.Communicate(text,settings.voice_marathi_online,rate="-8%")
            for chunk in communicate.stream_sync():
                if chunk.get("type")=="audio":
                    audio.extend(chunk["data"])
            if audio:
                return base64.b64encode(bytes(audio)).decode("ascii"),code,"audio/mpeg"
        except Exception:
            # The transcript and device speech fallback remain available if
            # the free neural voice endpoint is temporarily unreachable.
            pass
        return None,code,None
    if code not in {"hi","en"}:
        return None,language,None
    model_name=settings.voice_hindi_model if code=="hi" else settings.voice_english_model
    model_path=_voice_dir()/f"{model_name}.onnx"
    if not model_path.exists():
        return None,code,None
    with _voices_lock:
        if model_name not in _voices:
            from piper import PiperVoice
            _voices[model_name]=PiperVoice.load(str(model_path))
        voice=_voices[model_name]
    buffer=io.BytesIO()
    with wave.open(buffer,"wb") as wav_file:
        voice.synthesize_wav(text,wav_file)
    wav_bytes=buffer.getvalue()
    try:
        encoded=subprocess.run(
            ["ffmpeg","-hide_banner","-loglevel","error","-f","wav","-i","pipe:0","-vn","-ac","1","-ar","22050","-b:a","40k","-f","mp3","pipe:1"],
            input=wav_bytes,capture_output=True,check=True,timeout=20,
        ).stdout
        if encoded:
            return base64.b64encode(encoded).decode("ascii"),code,"audio/mpeg"
    except (FileNotFoundError,subprocess.SubprocessError):
        pass
    return base64.b64encode(wav_bytes).decode("ascii"),code,"audio/wav"


def serialize_message(item: VoiceMessage) -> dict:
    return {"id":item.id,"role":item.role,"text":item.text,"language":item.language,"source":item.source,"created_at":item.created_at.isoformat()}


def serialize_session(db, item: VoiceSession, include_messages: bool=True) -> dict:
    result={
        "id":item.id,"user_id":item.user_id,"vehicle_id":item.vehicle_id,"language":item.language,
        "status":item.status,"started_at":item.started_at.isoformat(),
        "ended_at":item.ended_at.isoformat() if item.ended_at else None,
        "summary":item.summary,"notes":item.notes or {},
    }
    if include_messages:
        result["messages"]=[serialize_message(message) for message in db.scalars(select(VoiceMessage).where(VoiceMessage.session_id==item.id).order_by(VoiceMessage.id))]
    return result


def complete_session(db, session: VoiceSession) -> dict:
    messages=list(db.scalars(select(VoiceMessage).where(VoiceMessage.session_id==session.id).order_by(VoiceMessage.id)))
    user_text=" ".join(item.text for item in messages if item.role=="USER").lower()
    topic_rules={
        "Battery health":["battery","soc","charge","range","bms","बैटरी","चार्ज"],
        "Cold-chain integrity":["container","temperature","humidity","medicine","safe time","कंटेनर","तापमान","दवा"],
        "Route and ETA":["destination","reach","route","eta","delay","location","गंतव्य","पहुँच","रास्ता","देरी"],
        "Risk and alerts":["risk","alert","critical","fault","warning","जोखिम","चेतावनी","खराबी"],
    }
    topics=[name for name,terms in topic_rules.items() if any(term in user_text for term in terms)] or ["General fleet status"]
    data,snapshot,_=_selected_snapshot(db,session.vehicle_id,user_text)
    risks=[];actions=[];facts=[]
    if snapshot:
        facts=[
            f"SOC {snapshot['battery']['soc']:.1f}%",
            f"Battery {snapshot['battery']['battery_temperature']:.1f}°C",
            f"Container {snapshot['container']['temperature']:.1f}°C",
            f"Destination {snapshot['delivery']['distance_remaining']:.1f} km",
            f"Risk {snapshot['risk']['risk_score']}/100 ({snapshot['risk']['risk_level']})",
        ]
        risks=[factor["reason"] for factor in snapshot["risk"].get("contributing_factors",[])][:5]
        if snapshot["risk"].get("recommended_action"):
            actions=[snapshot["risk"]["recommended_action"]]
    active=[a for a in data["alerts"] if a["active"] and (not session.vehicle_id or a["vehicle_id"]==session.vehicle_id)]
    risks.extend(a["reason"] for a in active[:3] if a["reason"] not in risks)
    actions.extend(a["recommended_action"] for a in active[:3] if a["recommended_action"] not in actions)
    summary=(
        f"Voice consultation completed for {session.vehicle_id or 'fleet operations'}. "
        f"Discussed {', '.join(topics).lower()}. {len(messages)//2} operator turn(s) were recorded."
    )
    session.status="COMPLETED";session.ended_at=utcnow();session.summary=summary
    session.notes={"topics":topics,"key_facts":facts,"risks":risks,"recommended_actions":actions,"data_timestamp":data["timestamp"],"raw_audio_retained":False}
    db.commit();db.refresh(session)
    return serialize_session(db,session)
