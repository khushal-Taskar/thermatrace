from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/pharmatrace.db"
    admin_email: str = "admin@thermatrace.local"
    admin_password: str = "PharmaDemo!2026"
    frontend_origins: str = "http://localhost:3100,http://127.0.0.1:3100"
    simulation_interval: float = Field(default=3, ge=1, le=60)
    cookie_secure: bool = False
    osrm_base_url: str = "https://router.project-osrm.org"
    mqtt_enabled: bool = False
    mqtt_broker_host: str = ""
    mqtt_broker_port: int = 8883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic: str = "thermatrace/vehicles/+/telemetry"
    mqtt_tls: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@thermatrace.local"
    smtp_starttls: bool = True
    model_bundle_path: str = "data/models/validated-risk-model.joblib"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    voice_whisper_model: str = "small"
    voice_whisper_device: str = "cpu"
    voice_whisper_compute_type: str = "int8"
    voice_model_dir: str = "data/voices"
    voice_hindi_model: str = "hi_IN-pratham-medium"
    voice_english_model: str = "en_US-lessac-medium"
    voice_online_tts_enabled: bool = True
    voice_marathi_online: str = "mr-IN-AarohiNeural"
    voice_store_audio: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
