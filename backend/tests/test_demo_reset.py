from app.database import SessionLocal
from app.models import TelemetryHistory
from sqlalchemy import select, func


def test_reset_preserves_history(client):
    client.post('/api/auth/login',json={'email':'admin@thermatrace.local','password':'PharmaDemo!2026'})
    with SessionLocal() as db:
        before=db.scalar(select(func.count(TelemetryHistory.id)))
    assert client.post('/api/simulation/reset').status_code==200
    overview=client.get('/api/overview').json()
    assert len(overview['fleet'])==5
    assert overview['metrics']['active_deliveries']==5
    assert not overview['simulation_paused']
    with SessionLocal() as db:
        assert db.scalar(select(func.count(TelemetryHistory.id)))>=before+5
    client.post('/api/auth/logout')
