# Database Schema

Alembic migrations through `0003_rescue_dispatch` support populated SQLite databases and fresh SQLite/PostgreSQL schemas. JSON snapshots preserve full telemetry while indexed normalized tables support audit and targeted queries.

```mermaid
erDiagram
    USERS ||--o{ AUTH_SESSIONS : owns
    USERS ||--o{ ALERTS : acknowledges
    USERS ||--o{ NOTIFICATION_DELIVERIES : receives
    MEDICINE_PROFILES ||--o{ CONTAINERS : governs
    VEHICLES ||--|| DELIVERIES : performs
    CONTAINERS ||--|| DELIVERIES : carries
    ROUTES ||--o{ DELIVERIES : plans
    VEHICLES ||--o{ VEHICLE_TELEMETRY : emits
    VEHICLES ||--o{ BATTERY_TELEMETRY : emits
    CONTAINERS ||--o{ CONTAINER_TELEMETRY : emits
    VEHICLES ||--o{ TELEMETRY_HISTORY : snapshots
    VEHICLES ||--o{ ALERTS : raises
    VEHICLES ||--o{ RISK_EVENTS : produces
    VEHICLES ||--o| SENSOR_DEVICES : maps
    ALERTS ||--o{ NOTIFICATION_DELIVERIES : dispatches
    USERS ||--o{ VOICE_SESSIONS : starts
    VEHICLES ||--o{ VOICE_SESSIONS : discusses
    VOICE_SESSIONS ||--o{ VOICE_MESSAGES : contains

    USERS { int id PK string email UK string role boolean active }
    MEDICINE_PROFILES { string id PK float min_temperature float max_temperature float max_excursion_minutes int prediction_horizon_minutes }
    VEHICLES { string id PK string telemetry_source datetime last_sensor_at json state }
    CONTAINERS { string id PK string shipment_id UK string medicine_profile_id FK }
    ROUTES { string id PK json planned_route string provider float duration_minutes }
    TELEMETRY_HISTORY { int id PK string vehicle_id FK datetime timestamp json snapshot boolean synthetic }
    ALERTS { int id PK string severity boolean active boolean acknowledged json telemetry_snapshot }
    SENSOR_DEVICES { string id PK string vehicle_id FK string topic boolean active }
    MODEL_VERSIONS { int id PK string version UK json metrics boolean active }
    VOICE_SESSIONS { int id PK int user_id FK string vehicle_id FK string language string status datetime started_at datetime ended_at text summary json notes }
    VOICE_MESSAGES { int id PK int session_id FK string role text text string language string source datetime created_at }
```

`synthetic=false` distinguishes accepted MQTT records. Model artifacts stay on disk; `model_versions` stores provenance and validation metrics when an approved model is registered. Use PostgreSQL backups and secret management before production deployment.

Voice records store the human/assistant transcript and structured closing note. They intentionally contain no raw microphone payload or generated audio file.
