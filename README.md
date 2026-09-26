# ThermaTrace

**AI-Based Intelligent Pharmaceutical Transportation and Cold-Chain Risk Monitoring System**

A complete local software simulation for a final-year engineering project. ThermaTrace brings pharmaceutical containers, electric transport vehicles, battery health, delivery routes, incidents, historical telemetry, and explainable local AI into one responsive operations control center. No devices, cloud subscriptions, maps keys, or paid LLM APIs are required.

## Live demonstration

- Web application: **https://thermatrace-pharma.vercel.app**
- API health: **https://thermatrace-api.onrender.com/api/health**
- Cloud demo admin: `admin@thermatrace.local` / the password configured during deployment. The local seeded default is shown in the login screen.

The public demo uses Vercel, Render and Supabase free tiers. The Render service can sleep after inactivity, so the first request may take about a minute while it wakes. The local setup below remains the full zero-cost option and includes the local voice-model runtime.

## Problem statement and objectives

Temperature excursions, delivery delays, vehicle failures, and insufficient battery range can compromise temperature-sensitive shipments. This project demonstrates continuous simulated monitoring, early risk prioritization, explainable interventions, and auditable incident records. Its objectives are to correlate transport and cold-chain signals, monitor multiple vehicles, make AI results inspectable, and produce useful operational reports.

This is an educational simulation. Its generated medicine labels, drivers, routes, vehicles, and sensor data are fictional. It does not establish pharmaceutical suitability, regulatory compliance, or validated failure probabilities.

## Features

- Fourteen working sections: Dashboard, Fleet, Live Tracking, Vehicles, Battery / BMS, Containers, Deliveries, Dispatch, AI Risk Center, AI Voice Center, Alerts, Analytics, Reports, Settings.
- Five populated EVs (`PHARMA-EV-001` through `005`) transporting different medicine shipments around Pune.
- Correlated telemetry every three seconds: GPS, motor, speed, SOC/SOH, current, voltage, battery temperature, container conditions, delivery progress, and risk.
- FastAPI native WebSocket updates with authentication, automatic reconnection, and one-time connection tickets.
- OpenStreetMap / React-Leaflet map with smoothly moving markers, OSRM road geometry, actual track, source/destination, ETA, and deviation indication. Public OSRM is free and stored routes remain available offline.
- Thirteen scenarios: normal delivery, low battery, battery overheating, motor overheating, temperature excursion, humidity, open door, tampering, shock, route deviation, delay, vehicle failure, BMS fault.
- Five medicine-specific cold-chain profiles with configurable bands, warning margins, excursion budgets, forecast horizons, handling notes, live excursion duration, remaining-safe-time estimation, and predictive alerts.
- Rule-based safety detection, trained Isolation Forest anomaly detection, and trained Random Forest risk prediction across 16 signals. Evidence, thresholds, recommended actions, model metrics, and counterfactual feature sensitivities are visible.
- Local operations assistant with intent recognition, current and historical analytics, and one-click PDF report actions; no paid LLM required.
- AI Voice Center with Hindi, English and Marathi multi-turn conversations, live database grounding, remembered follow-up topics, question-specific battery/container/risk/alert/route/ETA/history answers, breakdown/dispatch actions, spoken replies, hands-free turn-taking, transcripts, and automatic closing notes. Fast browser recognition is the default when available; private local Faster Whisper can be selected on the local installation. Piper provides Hindi/English speech locally, while Marathi can use a free online neural voice. Raw recordings are not retained by ThermaTrace.
- Dispatch & recovery page with separate persistent Point A and Point B in-app chats, voice-triggered messages, read status, a simulated replacement vehicle, live recovery progress, OSRM road-route refinement and moving map marker. Dispatch is an in-app simulation; it does not send SMS or email to real facilities.
- Persistent incident episodes, acknowledgement audit, recovery history, and CSV export.
- Twelve historical signal charts, including temperature forecast, excursion duration, remaining safe time and battery current, with configurable ranges and CSV export.
- Six database-generated report types with exact full-range statistics, downloadable JSON, printable preview, and direct server-generated PDF files.
- Light/dark mode, responsive navigation, restrained motion, reduced-motion support, detail panels, loading, empty, and error states.
- ADMIN / OPERATOR / VIEWER accounts, hashed passwords, eight-hour HTTP-only sessions, server-enforced permissions, origin checks, and protected control routes.
- Foreground browser notifications plus optional SMTP email delivery for deduplicated HIGH / CRITICAL alerts, failed-send retry, per-user destinations and a Settings-page test email.
- Optional validated MQTT device registry and ingest adapter; sensor records are explicitly tagged `synthetic=false`.
- SQLite by default, PostgreSQL driver and Docker Compose option, plus versioned Alembic migrations.

## Architecture and stack

```mermaid
flowchart LR
    Sim[Correlated simulator] --> AI[Rules + Isolation Forest + Random Forest]
    MQTT[Optional MQTT sensors] --> AI
    AI --> DB[(SQLAlchemy: SQLite / PostgreSQL)]
    OSRM[OSRM road service] --> API[FastAPI services]
    DB --> API
    DB --> WS[Authenticated WebSocket]
    API --> PDF[ReportLab PDF]
    API --> Notify[Browser / optional SMTP]
    API --> Next[Next.js / React / TypeScript]
    Voice[Browser speech or Whisper → grounded intents → deferred speech] --> API
    API --> Dispatch[Point A/B in-app dispatch]
    Dispatch --> Rescue[Virtual replacement mission]
    Rescue --> DB
    WS --> Next
    Next --> UI[Leaflet / Recharts control center]
```

Frontend: Next.js 16, React 19, TypeScript, Tailwind 4, shadcn-style Button/Card primitives with Radix Slot and class-variance-authority, Lucide, Framer Motion, Recharts, React-Leaflet, OpenStreetMap. Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite/PostgreSQL, NumPy, pandas, scikit-learn, ReportLab, Paho MQTT, Faster Whisper, Piper, and HTTPX/OSRM/Ollama. Exact frontend resolutions are in `frontend/package-lock.json`; backend versions are pinned in `backend/requirements.txt`.

The original ElectroSim/OpenHW workspace is separate. No OpenHW runtime or simulator components are modified or embedded here.

## Quick start — Windows

Prerequisites: **Node.js 22+** (tested with 24.16), **Python 3.12**, PowerShell, and **Ollama** for the conversational voice agent. First dependency/model installation requires internet access. Thereafter AI, speech, and simulation run locally. OpenStreetMap tiles need internet; an unavailable-tile message is shown while route overlays and telemetry remain usable.

From the project root:

```powershell
cd 'C:\electronic simulation\pharmatrace'
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The launcher creates the Python virtual environment if missing, installs missing dependencies using the pinned requirements / npm lockfile, applies Alembic migrations, starts both services in hidden background processes, and waits for readiness. Open **http://localhost:3100**. API docs: **http://127.0.0.1:8100/docs**. Logs: `logs/`. It does not stop unrelated listeners on occupied ports.

```powershell
# Stop only processes created by this launcher
powershell -ExecutionPolicy Bypass -File .\stop.ps1

# Build and serve the production frontend (stop dev first)
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Production
```

The policy flag applies only to that PowerShell invocation; it does not change your system execution policy.

Local voice models are installed once:

```powershell
ollama pull qwen2.5:3b
cd 'C:\electronic simulation\pharmatrace\backend'
.\.venv\Scripts\python.exe -m piper.download_voices --download-dir data/voices hi_IN-pratham-medium en_US-lessac-medium
```

The first spoken turn downloads the Faster Whisper `small` model into the local Hugging Face cache. Use Chrome or Edge and allow microphone access for `localhost:3100`. Text questions remain available if the microphone or a speech model is temporarily unavailable.

### Demo credentials

```text
ADMIN    admin@thermatrace.local / PharmaDemo!2026
OPERATOR operator@thermatrace.local / OperatorDemo!2026
VIEWER   viewer@thermatrace.local / ViewerDemo!2026
```

This is a public local demo credential, not a real secret. `.env` can override the seeded admin email/password **before the first database initialization**. Password configuration does not overwrite an existing account. Use a separate secure account/password and HTTPS before any real deployment.

## Manual installation and startup

Backend, PowerShell terminal:

```powershell
cd 'C:\electronic simulation\pharmatrace\backend'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Frontend, second PowerShell terminal:

```powershell
cd 'C:\electronic simulation\pharmatrace\frontend'
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Linux/macOS equivalents, from the project root in two terminals:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Use `localhost:3100` consistently. Both `localhost:3100` and `127.0.0.1:3100` are allowed origins. The Next.js `/api` rewrite forwards REST calls and HTTP-only cookies to FastAPI. The browser connects directly to port 8100 for WebSockets with a single-use, 30-second ticket. For custom ports/hosts, update backend `FRONTEND_ORIGINS`, frontend `BACKEND_URL`, and `NEXT_PUBLIC_WS_URL`. Build again after changing public frontend environment variables.

## Database setup

`start.ps1` runs `alembic upgrade head`, then seeds profiles, users, routes, vehicles, containers, deliveries, and one hour of chart history when needed. SQLite remains the zero-configuration default at `backend/data/pharmatrace.db`; foreign keys and WAL are enabled. Live records survive restart, old telemetry/risk history is pruned after 30 days, and incident audit records are retained.

To use free local PostgreSQL with Docker:

```powershell
docker compose -f docker-compose.postgres.yml up -d
$env:DATABASE_URL='postgresql+psycopg://thermatrace:local-development-only@localhost:5432/thermatrace'
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Change the development password before any shared deployment. Supabase or another managed PostgreSQL service can be selected with the same `DATABASE_URL`. The included migration was exercised against the populated SQLite demo; install/run a PostgreSQL service to perform environment-specific integration and backup testing.

## Simulation and demonstration

1. Sign in. Observe five vehicles and varied shipment/energy risks.
2. Open **Simulation lab**. Select a target vehicle and a scenario, then **Trigger scenario**.
3. Digital door/tamper/BMS faults appear immediately. Analog temperature/current/SOC/deviation values approach target conditions smoothly, typically over 15–60 seconds.
4. Inspect **AI Risk Center → Inspect detection evidence** to see observed values, thresholds, model outputs, and feature sensitivity.
5. Acknowledge an incident under **Alerts**. Acknowledgement does not remove the underlying fault or the record. Severity changes reopen acknowledgement; a recovered condition is marked inactive.
6. Ask the assistant “Which shipment is highest risk?” or “Why is Vehicle V03 critical?”.
7. Explore Analytics and generate Reports. Download CSV/JSON, preview, print, or create the PDF directly.
8. **Restore normal conditions** resets a vehicle's demo SOC/delay and removes the chosen scenario target. Thermal values cool gradually. **Restart all demo journeys** restores the initial scenario distribution and positions without deleting telemetry or incidents.
9. Open **AI Voice Center**, select a vehicle and Hindi, English or Marathi, and start a call. The agent greets you. Say a breakdown report and request Point A/B dispatch, or type the same command. Fast browser recognition may use the browser provider's speech service; select Local Whisper for private server-side transcription. End the call to generate persisted notes and transcript.
10. Open **Dispatch** to see the separate Point A/B message records and replacement route. The demo vehicle moves at an accelerated 20× clock, while the displayed road ETA is unaccelerated. Use **Restart all demo journeys** to cancel active recovery simulations and restore the seeded fleet state.

The simulator recycles completed demo routes to keep a continuously populated map; use **Restart all demo journeys** to restore seed SOC and positions for a presentation. It is an educational simulation, not a physical fleet scheduler. Settings can pause automatic advancement; an explicit scenario/reset/settings action can still recalculate a tick. SOH is fixed per vehicle during this short demonstration because realistic degradation does not oscillate every few seconds.

Seed checkpoints are converted to OSRM road-following geometry and stored in the database. The five included demo routes have been refreshed from the public OSRM service; the stored route remains available if that service is offline. Route deviation is the geometric distance to the nearest planned road segment. ETA uses remaining distance and current speed with a fallback speed while stopped. Delay and unexpected-stop rules are explainable demonstration heuristics.

## AI/ML explanation

The engine creates 3,500 reproducible synthetic correlated training records and uses 16 features, including temperature trend, excursion duration, remaining safe time, and predicted temperature. Isolation Forest learns the nominal subset. A Random Forest regressor learns a synthetic hazard target incorporating battery margin, heat, cold-chain excursion, humidity, shock, deviation, and delay. The regressor uses an 80/20 holdout split; the current seeded run has MAE **1.67 risk points against synthetic targets**. This is not real-world validation.

The final priority score combines rule safety floors, model prediction, anomaly index, and escalation for simultaneous breaches, capped at 100. Levels: NORMAL 0–30; WARNING 31–60; HIGH 61–80; CRITICAL 81–100. Each output includes score, level, reason, factors, action, anomaly status, detection time, and uncertainty. Feature bars show one-feature nominal-baseline counterfactual changes in model prediction; they are not SHAP values and are not additive final-score contributions.

The assistant is a replaceable local service interface (`app/ai/assistant.py`). It recognizes supported intents, queries current and historical ORM-derived telemetry, and returns validated UI actions for direct PDF reports. It never executes generated SQL/code. An optional future LLM can translate questions into validated intents while preserving this query layer.

The voice assistant also has deterministic operational answers for medicine, batch, current/predicted container temperature, product range, humidity, excursion duration, remaining-safe-time estimate, door/tamper/shock state, vehicle/BMS condition, breakdown recording and Point A/Point B rescue dispatch. These answers come from the current database snapshot, and safety-time text remains an estimate rather than a product-release decision.

To activate direct alert email, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_FROM` in `backend/.env` or the backend host's secret environment. Use `SMTP_STARTTLS=true` for port 587, or `SMTP_USE_SSL=true` for implicit TLS (commonly port 465). Then open **Settings → Alert delivery**, save the recipient address, enable HIGH / CRITICAL email, and press **Send test**. SMTP credentials are deliberately never stored in the repository.

## API endpoints

Interactive schema is available at `/docs`. All operational endpoints require the session cookie.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Public health and disclosed model metadata |
| POST | `/api/auth/login` | Authenticate and set HTTP-only session cookie |
| GET / POST | `/api/auth/me`, `/api/auth/logout` | Inspect / revoke session |
| GET | `/api/overview` | Fleet, metrics, incidents, rescue missions and dispatch messages |
| GET | `/api/vehicles`, `/api/vehicles/{id}` | Fleet / full vehicle snapshot |
| GET | `/api/containers`, `/api/deliveries` | Current container / delivery records |
| GET | `/api/risk` | Ranked snapshots and model metadata |
| GET | `/api/alerts` | Recent 200 incident records |
| POST | `/api/alerts/{id}/acknowledge` | Persist actor/time acknowledgement |
| GET | `/api/history?vehicle_id=...&hours=...` | Chronological sampled chart telemetry |
| GET | `/api/reports/{kind}?vehicle_id=...&hours=...` | Exact aggregate statistics + fleet/incidents |
| GET | `/api/reports/{kind}/pdf?...` | Direct professional PDF download |
| GET / PUT | `/api/medicine-profiles`, `/api/medicine-profiles/{id}` | Read/update product cold-chain limits |
| GET / POST / PUT | `/api/users`, `/api/users/{id}` | ADMIN account and role management |
| GET / POST | `/api/integrations/mqtt/status`, `/api/integrations/mqtt/devices` | MQTT status / device registry |
| POST | `/api/integrations/mqtt/test-ingest` | Validate the real-sensor ingest path |
| POST | `/api/routes/refresh` | Refresh all road routes from OSRM |
| GET / PUT | `/api/notifications/status`, `/api/me/notifications` | Channels and user email preferences |
| GET | `/api/notifications/deliveries` | Signed-in user's recent sent/failed email audit |
| POST | `/api/notifications/test` | Send a test message to the signed-in user's alert address |
| GET | `/api/ai/model-validation` | Model provenance, schema, and retraining command |
| POST | `/api/assistant` | `{ "question": "Which shipment is highest risk?" }` |
| GET | `/api/voice/status` | Local Ollama, Whisper, Piper, and voice-model readiness |
| GET / POST | `/api/voice/sessions` | Review calls / start an Admin or Operator call |
| POST | `/api/voice/sessions/{id}/turn?fast=true` | Transcribe a microphone recording and return grounded answer text immediately |
| POST | `/api/voice/sessions/{id}/message?fast=true` | Typed or browser-recognized fast voice turn |
| GET | `/api/voice/messages/{id}/audio` | Fetch the spoken answer separately from the fast text response |
| POST | `/api/voice/sessions/{id}/end` | Close a call and persist structured notes |
| GET / POST | `/api/dispatch/messages` | Point A/B in-app inboxes and manual message |
| POST | `/api/dispatch/messages/{id}/read` | Record inbox read state |
| POST | `/api/dispatch/rescue` | Start one simulated replacement mission for a stopped shipment |
| GET | `/api/simulation/scenarios` | Available scenarios |
| POST | `/api/simulation/scenario` | `{ "vehicle_id": "PHARMA-EV-001", "scenario": "TAMPERING" }` |
| POST | `/api/simulation/reset` | Restart demo journeys; retain audit/history |
| GET / PUT | `/api/settings` | Persist temperature band, organization, pause state |
| POST | `/api/ws-ticket` | One-time authenticated connection ticket |
| WS | `/ws/telemetry?ticket=...` | Full overview frames every simulation interval |

Report kinds: `shipment`, `vehicle`, `battery`, `container`, `risk`, `incident`. History ranges: 0.016–720 hours; evenly sampled across the **entire** range to about 600 points. Reports aggregate **all** persisted samples in the selected range rather than downsampled chart points.

## Folder structure

```text
pharmatrace/
  start.ps1 / stop.ps1
  backend/
    app/
      api/routes.py
      ai/engine.py / assistant.py / training.py
      simulation/engine.py / seed.py
      services/auth.py / monitoring.py / cold_chain.py / routing.py / voice_agent.py
      services/mqtt_adapter.py / notifications.py / pdf_reports.py
      database.py / models.py / schemas.py / config.py / main.py
    alembic/ / alembic.ini
    tests/
    requirements.txt / .env.example
  frontend/
    src/app/           Next.js routes, layouts, login, global styles
    src/components/    Shell, maps, charts, drawers, status, UI primitives
    src/features/      Modular operational pages and panels
    src/hooks/         Shared authenticated WebSocket state
    src/lib/           API client and utilities
    src/types/         Typed telemetry and operational contracts
    package.json / package-lock.json / .env.example
  docs/                Architecture, schema, AI, algorithms, requirements, QA
```

## Verification

```powershell
cd 'C:\electronic simulation\pharmatrace\backend'
.\.venv\Scripts\python.exe -m pytest -q

cd 'C:\electronic simulation\pharmatrace\frontend'
npm run typecheck
npm run build
```

The backend tests use a temporary SQLite database, leaving the demo database intact. Browser verification covers all thirteen sections, native WebSocket frames, voice session lifecycle, scenario controls, assistant explanations, acknowledgement, history and report interactions. See `docs/TESTING.md` for test strategy and actual results. Direct PDF generation is server-side and needs no external service; browser print remains available as a second option.

## Cost and deployment

The complete local demonstration is designed to run without paid APIs, cloud services, or hardware. Internet is used only for the OpenStreetMap basemap and initial dependency installation. Optional public hosting, production map/routing services, a custom domain, SMS alerts, managed database capacity, or an external LLM can introduce cost. See [`docs/COSTS_AND_FREE_DEPLOYMENT.md`](docs/COSTS_AND_FREE_DEPLOYMENT.md) for the free-first deployment recommendation and cost matrix.

### Public free-tier deployment

The repository is prepared for a three-service deployment:

- **Vercel Hobby** builds `frontend/` and supplies the public `*.vercel.app` site.
- **Render Free Web Service** reads `render.yaml`, runs Alembic, starts FastAPI, and serves the native WebSocket.
- **Supabase Free** supplies persistent PostgreSQL storage so telemetry, alerts, users, and reports survive Render restarts.

Use [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the exact order and environment values. The cloud build intentionally omits Whisper and Piper because their model/runtime memory exceeds a reliable free web service. The deployed Voice Center retains typed, database-grounded answers and browser speech; the full microphone, Whisper, Ollama, and Piper workflow remains available in the local demonstration.

## Reference repositories and attribution

Inspected through the connected GitHub integration:

- [Pharmaceutical Supply Chain Agentic AI](https://github.com/MahdiNavaei/pharmaceutical-supply-chain-agentic-ai): separate monitoring/service architecture and severity-prioritized insight patterns. Its paid LLM/inventory architecture is not carried into this project.
- [AWS FSAE EV Telemetry](https://github.com/Zinale/aws-iot-fsae-telemetry): grouped motor/GPS/pack/fault telemetry schema and producer-to-consumer flow. AWS/serial hardware dependencies are not used.
- [Pharmaceutical Cold Chain Monitoring](https://github.com/abikeidris235/Pharmaceutical-cold-chain-monitoring): excursion records, acknowledgement, and custody/audit concepts. Blockchain and regulatory compliance claims are not inherited.
- [TrackMate](https://github.com/Maganti-Praveen/TrackMate): timestamped tracks, route checkpoint sequencing, and trip-state patterns. Bus/student concepts are replaced with pharmaceutical vehicle/container/delivery domain models.

No source code or assets were copied from these repositories. This is a separate implementation using conceptual references. Higgsfield was inspected for optional design assets; the connected account had no image-generation credits, so the frontend visuals are maintained directly in code and require no generated assets.

## Future improvements

Obtain manufacturer-approved stability profiles and a representative labelled fleet dataset; retrain, calibrate and clinically/operationally validate the model; provision a production PostgreSQL service with backups; self-host OSRM and an MQTT broker at scale; add push notifications for closed-browser/mobile delivery; add bounded scheduling and charging plans; move WebSocket fan-out to a shared event broker for multiple workers; and optionally add an LLM only as a constrained intent translator.
