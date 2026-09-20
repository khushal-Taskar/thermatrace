# Functional requirements

| ID | Requirement | Implementation |
|---|---|---|
| FR01 | Authenticate and protect control routes/data | PBKDF2 + hashed sessions; server layout + API dependencies |
| FR02 | Monitor at least five EV transports | Seeded PHARMA-EV-001–005; Fleet/Vehicles |
| FR03 | Correlated simulated telemetry | Single backend tick engine; normalized + aggregate storage |
| FR04 | Monitor pack/BMS/motor diagnostics | Battery/Vehicles/details; fault scenarios |
| FR05 | Monitor pharmaceutical container integrity | Temperature/humidity/door/tamper/shock/vibration + batch/shipment |
| FR06 | Track planned/actual delivery location | OSM Leaflet map; moving markers, stored OSRM road geometry and actual tracks |
| FR07 | Detect deviation, stops, delay | Geometric deviation and explainable transport rules |
| FR08 | Real fitted local AI | IF anomaly detection + RF prediction + safety-rule floors |
| FR09 | Explain risk | Ranked center, factors/thresholds, feature sensitivity, actions |
| FR10 | Manage auditable alerts | Episode de-duplication, severity, snapshot, acknowledge actor/time, recovery |
| FR11 | Historical trend analysis | Range/vehicle/group selection; sampled charts + CSV |
| FR12 | Generate six report types | Exact DB aggregates, incident log, JSON, print and direct server PDF |
| FR13 | Query current operations in plain English | Local current/history intents, structured queries and report actions |
| FR14 | Manually trigger/reset scenarios | Simulation lab, thirteen scenarios, explicit journey reset |
| FR15 | Configure temperature band/pause | Persisted fallback plus medicine profiles, excursion budgets and forecasts |
| FR16 | Use all thirteen navigation sections | App Router sections and shared shell |
| FR17 | Operate on mobile and desktop | Responsive navigation/cards/tables/maps/drawers |
| FR18 | Enforce role-based access | VIEWER, OPERATOR and ADMIN API/UI permissions |
| FR19 | Notify operators | Foreground browser notifications and optional audited SMTP |
| FR20 | Accept future real sensors | Registered MQTT devices, allowlisted payloads, real-data provenance |
| FR21 | Evolve storage safely | Alembic migrations; SQLite default and PostgreSQL configuration |
| FR22 | Retrain when labelled data exists | Feature-schema validation, holdout metrics and versioned model bundle |
| FR23 | Speak with a local multilingual operations agent | Browser microphone, Whisper detection, grounded Hindi/English Qwen 2.5 answers, audited Marathi safety templates, Piper voices and browser speech fallback |
| FR24 | Preserve voice-call records without raw audio | Session transcript, automatic summary, risks, key facts and follow-up actions |

Core acceptance: database initializes, five vehicles appear, authenticated live updates move markers/change sensor values, scenario activation changes risk and alerts, explanations use actual recorded values, history is queryable, all navigation sections work, and documented startup commands work locally. Product-specific profiles and sensor adapters are implemented, but manufacturer/regulatory validation, production devices and representative labelled outcomes remain outside the validated demo evidence.
