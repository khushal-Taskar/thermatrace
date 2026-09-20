# Modules

| Area | Main modules | Responsibility |
|---|---|---|
| API/auth | `app/api/routes.py`, `services/auth.py` | Session auth, RBAC, REST contracts, WebSocket tickets |
| Simulation | `simulation/engine.py`, `simulation/seed.py` | Correlated movement, BMS/container signals, scenarios, demo seed |
| Cold chain | `services/cold_chain.py` | Profiles, excursion timer, trend, safe-time estimate, predictive status |
| AI | `ai/engine.py`, `ai/training.py` | Hybrid inference and labelled-data validation/retraining |
| Assistant | `ai/assistant.py` | Current/history queries and constrained report actions |
| Voice intelligence | `services/voice_agent.py` | Whisper transcription, bounded telemetry evidence, Ollama answer, Piper audio and structured closing notes |
| Routes | `services/routing.py` | OSRM road geometry with stored fallback |
| Sensors | `services/mqtt_adapter.py` | Broker lifecycle, registry validation, normalized real-data ingest |
| Alerts | `services/notifications.py` | Deduplicated optional SMTP delivery; browser status |
| Reports | `services/pdf_reports.py`, `services/monitoring.py` | Aggregates, incident evidence, direct PDF bytes |
| Persistence | `models.py`, `database.py`, `alembic/` | SQLite/PostgreSQL models and migrations |
| Frontend state | `hooks/use-monitor.tsx` | Authenticated WebSocket, browser notifications, selected vehicle |
| Operations UI | `features/*`, `components/*` | Responsive views, maps, charts, AI Voice Center, RBAC controls and report actions |
