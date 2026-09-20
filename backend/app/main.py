import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .database import Base, engine, SessionLocal
from .models import AuthSession, utcnow
from .config import settings
from .simulation.seed import seed_database
from .simulation.engine import Simulator
from .ai.engine import RiskEngine
from .services.monitoring import overview
from .services.auth import get_user
from .services.notifications import NotificationService
from .services.mqtt_adapter import MQTTAdapter
from .api.routes import router

logger=logging.getLogger("pharmatrace")
origins=[origin.strip().rstrip("/") for origin in settings.frontend_origins.split(",") if origin.strip()]


def origin_allowed(origin: str | None) -> bool:
    return not origin or origin.rstrip("/") in origins


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    app.state.risk_engine=RiskEngine()
    app.state.simulator=Simulator(app.state.risk_engine,settings.simulation_interval)
    app.state.notifier=NotificationService()
    app.state.clients={}
    app.state.tickets={}
    with SessionLocal() as db:
        seed_database(db)
        app.state.simulator.bootstrap_history(db)
        app.state.simulator.tick(db,force=True)

    async def broadcast():
        with SessionLocal() as db:
            payload=overview(db)
        async def send(ws,token):
            try:
                if not get_user(token):
                    await ws.close(code=4401)
                    app.state.clients.pop(ws,None)
                    return
                await asyncio.wait_for(ws.send_json(payload),timeout=3)
            except Exception:
                app.state.clients.pop(ws,None)
        await asyncio.gather(*(send(ws,token) for ws,token in list(app.state.clients.items())))
    app.state.broadcast=broadcast
    event_loop=asyncio.get_running_loop()
    app.state.mqtt=MQTTAdapter(app.state.risk_engine,app.state.simulator,lambda: asyncio.run_coroutine_threadsafe(broadcast(),event_loop))
    app.state.mqtt.start()

    async def loop():
        while True:
            await asyncio.sleep(settings.simulation_interval)
            try:
                with SessionLocal() as db:
                    app.state.simulator.tick(db)
                    app.state.notifier.dispatch(db)
                await broadcast()
            except Exception:
                logger.exception("Simulation tick failed")
    task=asyncio.create_task(loop())
    yield
    task.cancel()
    app.state.mqtt.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass
    for ws in list(app.state.clients):
        await ws.close(code=1001)


app=FastAPI(title="ThermaTrace Cold-Chain API",version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=["GET","POST","PUT"],allow_headers=["Content-Type"])


@app.middleware("http")
async def origin_guard(request: Request,call_next):
    origin=request.headers.get("origin")
    if request.method in ["POST","PUT","DELETE","PATCH"] and not origin_allowed(origin):
        return JSONResponse({"detail":"Untrusted request origin"},status_code=403)
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Cache-Control"]="no-store"
    return response


app.include_router(router)


@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket):
    origin=ws.headers.get("origin")
    if not origin_allowed(origin):
        await ws.close(code=4403)
        return
    ticket=app.state.tickets.pop(ws.query_params.get("ticket",""),None)
    if not ticket or ticket[1]<time.monotonic() or not get_user(ticket[0]):
        await ws.close(code=4401)
        return
    await ws.accept()
    app.state.clients[ws]=ticket[0]
    try:
        with SessionLocal() as db:
            await ws.send_json(overview(db))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        app.state.clients.pop(ws,None)
