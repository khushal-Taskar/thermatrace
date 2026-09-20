# Testing Strategy and Results

Automated backend tests use a temporary SQLite database and FastAPI lifespan. They cover authentication and origin checks, all 13 scenarios, correlated smooth simulation, incident lifecycle, exact aggregates, history, WebSocket tickets, reset behavior, medicine profiles, excursion/forecast math, server PDF bytes, assistant analytics/actions, VIEWER/OPERATOR/ADMIN authorization, MQTT device validation and `synthetic=false`, OSRM GeoJSON parsing, labelled-model schema/training validation, voice-session authorization, database grounding, transcripts and structured call notes.

Verified on 20 September 2026:

- Backend: **41 passed** (`python -m pytest -q`). Two dependency deprecation warnings originate from Starlette TestClient compatibility aliases.
- Frontend: production Next.js build and TypeScript validation passed (`npm run build`), generating 18 routes.
- Migration: the populated SQLite database upgraded to `0002_voice_agent`; existing telemetry and incident history were retained.
- Routing: all five current routes refreshed from public OSRM and stored with 423–817 road points each.
- PDF: generated with ReportLab, parsed with pypdf, rendered with Poppler, and visually inspected.
- Local voice runtime: Qwen 2.5 3B ran through Ollama on the NVIDIA GPU; Whisper Small transcribed generated Hindi speech; Hindi and English Piper voices produced playable compressed speech; Marathi sessions preserve their language code, use an audited telemetry template and call an installed browser voice without retaining microphone recordings.

Environment-dependent checks still required before a real deployment include live broker authentication/TLS, SMTP deliverability, the chosen PostgreSQL server/backup policy, OSRM capacity or self-hosting, closed-browser push delivery, load/stress behavior, and validation against representative labelled pharmaceutical outcomes.
