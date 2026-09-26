import secrets
import time
import re
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from io import BytesIO
from sqlalchemy import select, delete
from ..database import SessionLocal
from ..models import User, AuthSession, Vehicle, Container, Alert, NotificationDelivery, SystemSettings, MedicineProfile, Route, SensorDevice, ModelVersion, VoiceSession, VoiceMessage, RescueMission, DispatchMessage, utcnow
from ..schemas import LoginRequest, ScenarioRequest, Scenario, AssistantRequest, SettingsRequest, UserCreate, UserUpdate, MedicineProfileUpdate, SensorDeviceRequest, SensorPacket, NotificationPreferences, VoiceSessionCreate, VoiceTextTurn, DispatchMessageCreate, RescueStart
from ..services.auth import require_user, require_roles, verify_password, create_session, token_hash, hash_password
from ..services.monitoring import overview, fleet_snapshot, vehicle_snapshot, history, report
from ..ai.assistant import answer_question
from ..config import settings
from ..services.routing import refresh_route, RoutingError
from ..services.pdf_reports import build_report_pdf
from ..services.mqtt_adapter import ingest_sensor_packet
from ..services.voice_agent import runtime_status, transcribe_audio, generate_answer, synthesize_answer, serialize_session, serialize_message, complete_session
from ..services.voice_operations import operational_turn
from ..services.rescue_dispatch import create_rescue_mission, send_point_message, serialize_mission, serialize_message as serialize_dispatch_message, refine_rescue_routes

router=APIRouter(prefix="/api")
attempts=defaultdict(list)


def _dispatch_pending_notifications(notifier):
    """Open a fresh session so SMTP work never shares an API request transaction."""
    with SessionLocal() as db:
        return notifier.dispatch(db)


@router.get("/health")
async def health(request: Request):
    return {"status":"ok","simulation":"software","model":request.app.state.risk_engine.metadata,"tick_count":request.app.state.simulator.ticks}


@router.post("/auth/login")
def login(body: LoginRequest, response: Response, request: Request):
    key=request.client.host
    now=time.monotonic()
    attempts[key]=[t for t in attempts[key] if now-t<60]
    if len(attempts[key])>=10:
        raise HTTPException(429,"Too many attempts. Try again in one minute.")
    attempts[key].append(now)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==body.email.strip().lower()))
        if not user or not user.active or not verify_password(body.password,user.password_hash):
            raise HTTPException(401,"Email or password is incorrect")
        token=create_session(db,user)
        response.set_cookie("pharma_session",token,httponly=True,secure=settings.cookie_secure,samesite="strict",max_age=28800,path="/")
        return {"id":user.id,"name":user.name,"email":user.email,"role":user.role}


@router.get("/auth/me")
def me(user=Depends(require_user)):
    return {"id":user.id,"name":user.name,"email":user.email,"role":user.role,"notification_email":user.notification_email,"email_notifications":user.email_notifications}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(require_user)):
    with SessionLocal() as db:
        db.execute(delete(AuthSession).where(AuthSession.token_hash==token_hash(request.cookies["pharma_session"])))
        db.commit()
    response.delete_cookie("pharma_session",path="/")
    return {"ok":True}


@router.get("/overview")
def get_overview(user=Depends(require_user)):
    with SessionLocal() as db:
        return overview(db)


@router.get("/vehicles")
def get_vehicles(user=Depends(require_user)):
    with SessionLocal() as db:
        return fleet_snapshot(db)


@router.get("/vehicles/{vehicle_id}")
def get_vehicle(vehicle_id: str, user=Depends(require_user)):
    with SessionLocal() as db:
        items=[s for s in fleet_snapshot(db) if s["vehicle"]["vehicle_id"]==vehicle_id]
        if not items:
            raise HTTPException(404,"Vehicle not found")
        return items[0]


@router.get("/containers")
def get_containers(user=Depends(require_user)):
    with SessionLocal() as db:
        return [s["container"] for s in fleet_snapshot(db)]


@router.get("/deliveries")
def get_deliveries(user=Depends(require_user)):
    with SessionLocal() as db:
        return [s["delivery"] for s in fleet_snapshot(db)]


@router.get("/risk")
def get_risks(request: Request,user=Depends(require_user)):
    with SessionLocal() as db:
        return {"model":request.app.state.risk_engine.metadata,"vehicles":sorted(fleet_snapshot(db),key=lambda s:s["risk"]["risk_score"],reverse=True)}


@router.get("/alerts")
def get_alerts(user=Depends(require_user)):
    with SessionLocal() as db:
        return overview(db)["alerts"]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id: int,request: Request,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        alert=db.get(Alert,alert_id)
        if not alert:
            raise HTTPException(404,"Alert not found")
        alert.acknowledged=True
        alert.acknowledged_at=utcnow()
        alert.acknowledged_by=user.id
        db.commit()
    await request.app.state.broadcast()
    return {"ok":True}


@router.get("/history")
def get_history(vehicle_id: str|None=None,hours: float=Query(default=1,ge=.016,le=720),user=Depends(require_user)):
    with SessionLocal() as db:
        if vehicle_id and not db.get(Vehicle,vehicle_id):
            raise HTTPException(404,"Vehicle not found")
        return history(db,vehicle_id,hours)


@router.get("/reports/{kind}")
def get_report(kind: str,vehicle_id: str|None=None,hours: int=Query(default=24,ge=1,le=720),user=Depends(require_user)):
    if kind not in ["shipment","vehicle","battery","container","risk","incident"]:
        raise HTTPException(404,"Report type not found")
    with SessionLocal() as db:
        if vehicle_id and not db.get(Vehicle,vehicle_id):
            raise HTTPException(404,"Vehicle not found")
        return report(db,kind,vehicle_id,hours)


@router.get("/reports/{kind}/pdf")
def get_report_pdf(kind: str,vehicle_id: str|None=None,hours: int=Query(default=24,ge=1,le=720),user=Depends(require_user)):
    if kind not in ["shipment","vehicle","battery","container","risk","incident"]:
        raise HTTPException(404,"Report type not found")
    with SessionLocal() as db:
        if vehicle_id and not db.get(Vehicle,vehicle_id):
            raise HTTPException(404,"Vehicle not found")
        payload=report(db,kind,vehicle_id,hours)
    filename=f"thermatrace-{kind}-{vehicle_id or 'fleet'}.pdf"
    return StreamingResponse(BytesIO(build_report_pdf(payload)),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{filename}"'})


@router.post("/assistant")
def assistant(body: AssistantRequest,user=Depends(require_user)):
    with SessionLocal() as db:
        return answer_question(db,body.question)


def _voice_session(db,session_id: int):
    session=db.get(VoiceSession,session_id)
    if not session:
        raise HTTPException(404,"Voice session not found")
    return session


def _owned_voice_session(db, session_id: int, user):
    session = _voice_session(db, session_id)
    if session.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(403, "This conversation belongs to another operator")
    return session


def _voice_turn(db,session: VoiceSession,text: str,language: str,source: str,fast: bool=False):
    if session.status!="ACTIVE":
        raise HTTPException(409,"This voice session has already ended")
    detected=language if language!="auto" else ("hi" if re.search(r"[\u0900-\u097f]",text) else "en")
    operator=VoiceMessage(session_id=session.id,role="USER",text=text.strip(),language=detected,source=source)
    db.add(operator);db.flush()
    mentioned=re.search(r"(?:pharma[- ]ev[- ]|vehicle\s+v?|\bv)(\d{1,3})",text.lower())
    selected_id=f"PHARMA-EV-{int(mentioned.group(1)):03}" if mentioned else session.vehicle_id
    snapshot=vehicle_snapshot(db,selected_id) if selected_id else None
    if mentioned and snapshot:
        session.vehicle_id=selected_id
    action=operational_turn(db,session,text.strip(),detected,snapshot)
    dispatch_messages=[];rescue_mission=None
    if action:
        answer,dispatch_messages,rescue_mission=action
        evidence={"timestamp":utcnow().isoformat()}
    else:
        answer,selected_id,evidence=generate_answer(db,session,text.strip(),detected)
    agent=VoiceMessage(session_id=session.id,role="ASSISTANT",text=answer,language=detected,source="LOCAL_AI")
    db.add(agent);db.commit();db.refresh(operator);db.refresh(agent)
    if fast:
        audio,spoken_language,audio_mime=None,detected,None
    else:
        try:
            audio,spoken_language,audio_mime=synthesize_answer(answer,detected)
        except Exception:
            audio,spoken_language,audio_mime=None,detected,None
    return {
        "operator":serialize_message(operator),"assistant":serialize_message(agent),
        "vehicle_id":selected_id or session.vehicle_id,"audio_base64":audio,
        "audio_mime":audio_mime,"spoken_language":spoken_language,
        "audio_fallback":"BROWSER_SPEECH" if not audio and not fast else None,
        "audio_pending":fast,"dispatch_messages":dispatch_messages,"rescue_mission":rescue_mission,
        "evidence_timestamp":evidence["timestamp"],
    }


@router.get("/voice/status")
async def voice_status(user=Depends(require_user)):
    return await run_in_threadpool(runtime_status)


@router.get("/voice/sessions")
def voice_sessions(limit: int=Query(default=20,ge=1,le=100),user=Depends(require_user)):
    with SessionLocal() as db:
        items=db.scalars(select(VoiceSession).order_by(VoiceSession.started_at.desc()).limit(limit))
        return [serialize_session(db,item,include_messages=False) for item in items]


@router.get("/voice/sessions/{session_id}")
def voice_session_detail(session_id: int,user=Depends(require_user)):
    with SessionLocal() as db:
        return serialize_session(db,_owned_voice_session(db,session_id,user))


@router.post("/voice/sessions",status_code=201)
def start_voice_session(body: VoiceSessionCreate,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        if body.vehicle_id and not db.get(Vehicle,body.vehicle_id):
            raise HTTPException(404,"Vehicle not found")
        item=VoiceSession(user_id=user.id,vehicle_id=body.vehicle_id,language=body.language)
        db.add(item);db.flush()
        greeting={"hi":"नमस्ते, मैं थर्माट्रेस एआई एजेंट हूँ। मैं आपकी क्या सहायता कर सकता हूँ?", "mr":"नमस्कार, मी थर्माट्रेस एआय एजंट आहे. मी तुम्हाला कशी मदत करू?", "en":"Hello, I am the ThermaTrace AI agent. How can I help you?"}
        language=body.language if body.language!="auto" else "hi"
        db.add(VoiceMessage(session_id=item.id,role="ASSISTANT",text=greeting[language],language=language,source="GREETING"))
        db.commit();db.refresh(item)
        return serialize_session(db,item)


@router.post("/voice/sessions/{session_id}/message")
async def voice_text_turn(session_id: int,body: VoiceTextTurn,background_tasks: BackgroundTasks,request: Request,fast: bool=False,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        session=_owned_voice_session(db,session_id,user)
        result=await run_in_threadpool(_voice_turn,db,session,body.text,body.language,"TEXT",fast)
    if result["rescue_mission"]:
        background_tasks.add_task(refine_rescue_routes,result["rescue_mission"]["id"],SessionLocal,settings.osrm_base_url)
    if result["dispatch_messages"] or result["rescue_mission"]:
        background_tasks.add_task(request.app.state.broadcast)
    return result


@router.post("/voice/sessions/{session_id}/turn")
async def voice_audio_turn(session_id: int,background_tasks: BackgroundTasks,request: Request,audio: UploadFile=File(...),language: str=Form(default="auto"),fast: bool=False,user=Depends(require_roles("ADMIN","OPERATOR"))):
    supported={"auto","hi","en","mr"}
    if language not in supported:
        raise HTTPException(422,"Use auto detection or a supported Indian language code")
    allowed={"audio/webm","audio/wav","audio/x-wav","audio/mp4","audio/mpeg","audio/ogg","application/octet-stream"}
    content_type=(audio.content_type or "application/octet-stream").split(";",1)[0].strip().lower()
    if content_type not in allowed:
        raise HTTPException(415,"Use a WebM, WAV, MP4, MP3, or OGG microphone recording")
    payload=await audio.read(8*1024*1024+1)
    if len(payload)>8*1024*1024:
        raise HTTPException(413,"Voice turn must be smaller than 8 MB")
    suffix=Path(audio.filename or "turn.webm").suffix or ".webm"
    try:
        text,detected=await run_in_threadpool(transcribe_audio,payload,suffix,language)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc
    with SessionLocal() as db:
        session=_owned_voice_session(db,session_id,user)
        result=await run_in_threadpool(_voice_turn,db,session,text,detected,"VOICE",fast)
    if result["rescue_mission"]:
        background_tasks.add_task(refine_rescue_routes,result["rescue_mission"]["id"],SessionLocal,settings.osrm_base_url)
    if result["dispatch_messages"] or result["rescue_mission"]:
        background_tasks.add_task(request.app.state.broadcast)
    return result


@router.get("/voice/messages/{message_id}/audio")
async def voice_message_audio(message_id: int,user=Depends(require_user)):
    with SessionLocal() as db:
        message=db.get(VoiceMessage,message_id)
        if not message or message.role!="ASSISTANT":
            raise HTTPException(404,"Assistant message not found")
        session=db.get(VoiceSession,message.session_id)
        if session.user_id!=user.id and user.role!="ADMIN":
            raise HTTPException(403,"This conversation belongs to another operator")
        text,language=message.text,message.language
    try:
        audio,spoken_language,mime=await run_in_threadpool(synthesize_answer,text,language)
    except Exception:
        audio,spoken_language,mime=None,language,None
    return {"audio_base64":audio,"audio_mime":mime,"spoken_language":spoken_language,"audio_fallback":"BROWSER_SPEECH" if not audio else None}


@router.get("/dispatch/messages")
def dispatch_messages(point: str | None=Query(default=None,pattern="^(A|B)$"),user=Depends(require_user)):
    with SessionLocal() as db:
        query=select(DispatchMessage)
        if point:
            query=query.where(DispatchMessage.point==point)
        return [serialize_dispatch_message(item) for item in db.scalars(query.order_by(DispatchMessage.id.desc()).limit(100))]


@router.post("/dispatch/messages",status_code=201)
async def create_dispatch_message(body: DispatchMessageCreate,request: Request,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        if not db.get(Vehicle,body.vehicle_id):
            raise HTTPException(404,"Vehicle not found")
        item=send_point_message(db,body.point,body.vehicle_id,body.text,sender="OPERATIONS")
        db.commit()
        result=serialize_dispatch_message(item)
    await request.app.state.broadcast()
    return result


@router.post("/dispatch/messages/{message_id}/read")
async def read_dispatch_message(message_id: int,request: Request,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        item=db.get(DispatchMessage,message_id)
        if not item:
            raise HTTPException(404,"Message not found")
        item.status="READ";item.read_at=utcnow();db.commit()
        result=serialize_dispatch_message(item)
    await request.app.state.broadcast()
    return result


@router.post("/dispatch/rescue",status_code=201)
async def create_rescue(body: RescueStart,background_tasks: BackgroundTasks,request: Request,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        vehicle=db.get(Vehicle,body.vehicle_id)
        if not vehicle:
            raise HTTPException(404,"Vehicle not found")
        snapshot=next((item for item in fleet_snapshot(db) if item["vehicle"]["vehicle_id"]==body.vehicle_id),None)
        if not snapshot:
            raise HTTPException(409,"Vehicle telemetry is not ready")
        mission,created=create_rescue_mission(db,snapshot)
        if created:
            vehicle.scenario="VEHICLE_FAILURE"
            vehicle.state={**(vehicle.state or {}),"speed":0,"driver_reported_stop":True}
            send_point_message(db,"A",body.vehicle_id,f"Rescue requested for {mission.shipment_id}; dispatch {mission.replacement_vehicle_id} to {mission.breakdown_location}.",mission.id,sender="OPERATIONS")
            send_point_message(db,"B",body.vehicle_id,f"Delivery delay for {mission.shipment_id}; replacement {mission.replacement_vehicle_id} dispatched. Updated ETA will follow.",mission.id,sender="OPERATIONS")
        db.commit()
        result=serialize_mission(mission)
    if created:
        background_tasks.add_task(refine_rescue_routes,mission.id,SessionLocal,settings.osrm_base_url)
    background_tasks.add_task(request.app.state.broadcast)
    return result


@router.post("/voice/sessions/{session_id}/end")
def end_voice_session(session_id: int,user=Depends(require_roles("ADMIN","OPERATOR"))):
    with SessionLocal() as db:
        session=_owned_voice_session(db,session_id,user)
        if session.status=="ACTIVE":
            return complete_session(db,session)
        return serialize_session(db,session)


@router.get("/simulation/scenarios")
def scenarios(user=Depends(require_user)):
    return [s.value for s in Scenario]


@router.post("/simulation/scenario")
async def set_scenario(body: ScenarioRequest,request: Request,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        vehicle=db.get(Vehicle,body.vehicle_id)
        if not vehicle:
            raise HTTPException(404,"Vehicle not found")
        vehicle.scenario=body.scenario.value
        # NORMAL_DELIVERY is an explicit reset of scenario conditions for repeatable demos.
        if body.scenario==Scenario.NORMAL_DELIVERY:
            vehicle.state={**vehicle.state,"soc":vehicle.baseline_soc,"delay":0,"reset_at":utcnow().isoformat()}
            for mission in db.scalars(select(RescueMission).where(RescueMission.incident_vehicle_id==vehicle.id,RescueMission.status.in_(("TO_PICKUP","AT_PICKUP","TO_DESTINATION")))):
                mission.status="CANCELLED";mission.speed=0
        if body.scenario==Scenario.DELIVERY_DELAY:
            vehicle.state={**vehicle.state,"delay":18}
        vehicle.telemetry_source="SIMULATION"
        db.commit()
        request.app.state.simulator.tick(db,force=True)
    await run_in_threadpool(_dispatch_pending_notifications,request.app.state.notifier)
    await request.app.state.broadcast()
    return {"ok":True,"message":"Scenario applied. Analog sensors settle smoothly over subsequent ticks."}


@router.get("/settings")
def get_settings(user=Depends(require_user)):
    with SessionLocal() as db:
        system=db.get(SystemSettings,1)
        container=db.scalar(select(Container))
        return {"organization":system.organization,"simulation_paused":system.simulation_paused,"min_temperature":container.min_temperature,"max_temperature":container.max_temperature}


@router.post("/simulation/reset")
async def reset_demo(request: Request,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        seeded_scenarios=["NORMAL_DELIVERY","DELIVERY_DELAY","CONTAINER_TEMPERATURE_EXCURSION","BATTERY_OVERHEATING","NORMAL_DELIVERY"]
        reset_at=utcnow().isoformat()
        for index,vehicle in enumerate(db.scalars(select(Vehicle).order_by(Vehicle.id))):
            vehicle.state={"reset_at":reset_at}
            vehicle.scenario=seeded_scenarios[index%5]
            vehicle.telemetry_source="SIMULATION"
        for mission in db.scalars(select(RescueMission).where(RescueMission.status.in_(("TO_PICKUP","AT_PICKUP","TO_DESTINATION")))):
            mission.status="CANCELLED";mission.speed=0
        db.get(SystemSettings,1).simulation_paused=False
        db.commit()
        request.app.state.simulator.tick(db,force=True)
    await run_in_threadpool(_dispatch_pending_notifications,request.app.state.notifier)
    await request.app.state.broadcast()
    return {"ok":True,"message":"Demo journeys restarted; history and incident audit records retained."}


@router.put("/settings")
async def save_settings(body: SettingsRequest,request: Request,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        system=db.get(SystemSettings,1)
        system.organization=body.organization
        system.simulation_paused=body.simulation_paused
        for container in db.scalars(select(Container).where(Container.medicine_profile_id==None)):
            container.min_temperature=body.min_temperature
            container.max_temperature=body.max_temperature
        db.commit()
        request.app.state.simulator.tick(db,force=True)
    await run_in_threadpool(_dispatch_pending_notifications,request.app.state.notifier)
    await request.app.state.broadcast()
    return body


def serialize_user(user):
    return {"id":user.id,"email":user.email,"name":user.name,"role":user.role,"active":user.active,"notification_email":user.notification_email,"email_notifications":user.email_notifications,"created_at":user.created_at.isoformat() if user.created_at else None}


@router.get("/users")
def list_users(user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        return [serialize_user(item) for item in db.scalars(select(User).order_by(User.id))]


@router.post("/users",status_code=201)
def create_user(body: UserCreate,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        email=body.email.strip().lower()
        if db.scalar(select(User).where(User.email==email)):
            raise HTTPException(409,"A user with this email already exists")
        item=User(email=email,name=body.name.strip(),password_hash=hash_password(body.password),role=body.role,notification_email=body.notification_email,email_notifications=body.email_notifications)
        db.add(item);db.commit();db.refresh(item)
        return serialize_user(item)


@router.put("/users/{user_id}")
def update_user(user_id: int,body: UserUpdate,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        item=db.get(User,user_id)
        if not item:
            raise HTTPException(404,"User not found")
        changes=body.model_dump(exclude_unset=True)
        if item.id==user.id and changes.get("active") is False:
            raise HTTPException(400,"You cannot deactivate your current account")
        if item.id==user.id and changes.get("role") and changes["role"]!="ADMIN":
            raise HTTPException(400,"You cannot remove your own administrator role")
        for key,value in changes.items(): setattr(item,key,value)
        db.commit();db.refresh(item);return serialize_user(item)


@router.put("/me/notifications")
def notification_preferences(body: NotificationPreferences,user=Depends(require_user)):
    with SessionLocal() as db:
        item=db.get(User,user.id);item.notification_email=body.notification_email;item.email_notifications=body.email_notifications;db.commit();return serialize_user(item)


@router.get("/notifications/status")
def notification_status(request: Request,user=Depends(require_user)):
    return request.app.state.notifier.status()


@router.get("/notifications/deliveries")
def notification_deliveries(user=Depends(require_user)):
    with SessionLocal() as db:
        rows=db.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id==user.id).order_by(NotificationDelivery.created_at.desc(),NotificationDelivery.id.desc()).limit(10)).all()
        result=[]
        for row in rows:
            alert=db.get(Alert,row.alert_id)
            result.append({
                "id":row.id,"status":row.status,"destination":row.destination,
                "alert_type":alert.type if alert else "UNKNOWN",
                "severity":alert.severity if alert else "UNKNOWN",
                "vehicle_id":alert.vehicle_id if alert else None,
                "created_at":row.created_at.isoformat() if row.created_at else None,
                "sent_at":row.sent_at.isoformat() if row.sent_at else None,
                "error":row.error,
            })
        return result


@router.post("/notifications/test")
async def test_notification_email(request: Request,user=Depends(require_user)):
    destination=(user.notification_email or user.email).strip().lower()
    if not request.app.state.notifier.status()["email_configured"]:
        raise HTTPException(409,"SMTP email is not configured on the backend")
    try:
        await run_in_threadpool(request.app.state.notifier.send_test,destination)
    except Exception as exc:
        raise HTTPException(502,f"Test email could not be sent: {str(exc)[:300]}") from exc
    return {"ok":True,"destination":destination}


def serialize_profile(item):
    return {column.name:getattr(item,column.name) for column in MedicineProfile.__table__.columns}


@router.get("/medicine-profiles")
def medicine_profiles(user=Depends(require_user)):
    with SessionLocal() as db:
        return [serialize_profile(item) for item in db.scalars(select(MedicineProfile).order_by(MedicineProfile.name))]


@router.put("/medicine-profiles/{profile_id}")
async def update_medicine_profile(profile_id: str,body: MedicineProfileUpdate,request: Request,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        profile=db.get(MedicineProfile,profile_id)
        if not profile: raise HTTPException(404,"Medicine profile not found")
        for key,value in body.model_dump().items(): setattr(profile,key,value)
        for container in db.scalars(select(Container).where(Container.medicine_profile_id==profile.id)):
            container.min_temperature=profile.min_temperature;container.max_temperature=profile.max_temperature
        db.commit();request.app.state.simulator.tick(db,force=True)
        result=serialize_profile(profile)
    await run_in_threadpool(_dispatch_pending_notifications,request.app.state.notifier)
    await request.app.state.broadcast();return result


@router.post("/routes/refresh")
def refresh_routes(user=Depends(require_roles("ADMIN"))):
    updated=[];errors=[]
    with SessionLocal() as db:
        for route in db.scalars(select(Route).order_by(Route.id)):
            try:
                result=refresh_route(route,settings.osrm_base_url);updated.append({"route_id":route.id,"distance_km":result["distance_km"],"duration_minutes":result["duration_minutes"],"points":len(result["planned_route"])})
            except RoutingError as exc:
                errors.append({"route_id":route.id,"error":str(exc)})
        db.commit()
    if not updated:
        raise HTTPException(503,{"message":"OSRM routing was unavailable; stored routes were preserved","errors":errors})
    return {"provider":"OSRM","updated":updated,"errors":errors}


@router.get("/integrations/mqtt/status")
def mqtt_status(request: Request,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        devices=[{"device_id":d.id,"vehicle_id":d.vehicle_id,"topic":d.topic,"active":d.active,"last_seen":d.last_seen.isoformat() if d.last_seen else None} for d in db.scalars(select(SensorDevice))]
    return {**request.app.state.mqtt.status(),"devices":devices}


@router.post("/integrations/mqtt/devices",status_code=201)
def register_sensor(body: SensorDeviceRequest,user=Depends(require_roles("ADMIN"))):
    with SessionLocal() as db:
        if not db.get(Vehicle,body.vehicle_id): raise HTTPException(404,"Vehicle not found")
        if db.get(SensorDevice,body.device_id): raise HTTPException(409,"Device already exists")
        existing=db.scalar(select(SensorDevice).where(SensorDevice.vehicle_id==body.vehicle_id))
        if existing: raise HTTPException(409,"This vehicle already has a registered sensor device")
        device=SensorDevice(id=body.device_id,vehicle_id=body.vehicle_id,topic=body.topic);db.add(device);db.commit()
        return {"device_id":device.id,"vehicle_id":device.vehicle_id,"topic":device.topic}


@router.post("/integrations/mqtt/test-ingest")
async def test_sensor_ingest(body: SensorPacket,request: Request,user=Depends(require_roles("ADMIN"))):
    try:
        with SessionLocal() as db:
            snapshot=ingest_sensor_packet(db,body,request.app.state.risk_engine,request.app.state.simulator)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    await run_in_threadpool(_dispatch_pending_notifications,request.app.state.notifier)
    await request.app.state.broadcast();return snapshot


@router.get("/ai/model-validation")
def model_validation(request: Request,user=Depends(require_user)):
    metadata=request.app.state.risk_engine.metadata
    with SessionLocal() as db:
        versions=[{"version":item.version,"training_source":item.training_source,"sample_count":item.sample_count,"metrics":item.metrics,"active":item.active,"created_at":item.created_at.isoformat()} for item in db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()))]
    return {"active_model":metadata,"registered_versions":versions,"retraining_command":"python -m app.ai.training labelled_telemetry.csv --output data/models/validated-risk-model.joblib","required_features":metadata["features"]+["risk_target"]}


@router.post("/ws-ticket")
def ws_ticket(request: Request,user=Depends(require_user)):
    tickets=request.app.state.tickets
    now=time.monotonic()
    for key, value in list(tickets.items()):
        if value[1]<now:
            del tickets[key]
    ticket=secrets.token_urlsafe(32)
    tickets[ticket]=(request.cookies["pharma_session"],now+30)
    return {"ticket":ticket}
