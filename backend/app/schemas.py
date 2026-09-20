from enum import Enum
from pydantic import BaseModel, Field, model_validator


class Scenario(str, Enum):
    NORMAL_DELIVERY = "NORMAL_DELIVERY"
    LOW_BATTERY = "LOW_BATTERY"
    BATTERY_OVERHEATING = "BATTERY_OVERHEATING"
    MOTOR_OVERHEATING = "MOTOR_OVERHEATING"
    CONTAINER_TEMPERATURE_EXCURSION = "CONTAINER_TEMPERATURE_EXCURSION"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"
    DOOR_OPEN = "DOOR_OPEN"
    TAMPERING = "TAMPERING"
    SHOCK_EVENT = "SHOCK_EVENT"
    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    DELIVERY_DELAY = "DELIVERY_DELAY"
    VEHICLE_FAILURE = "VEHICLE_FAILURE"
    BMS_FAULT = "BMS_FAULT"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ScenarioRequest(BaseModel):
    vehicle_id: str
    scenario: Scenario


class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class SettingsRequest(BaseModel):
    organization: str = Field(min_length=2, max_length=100)
    min_temperature: float = Field(ge=-30, le=30)
    max_temperature: float = Field(ge=-30, le=40)
    simulation_paused: bool

    @model_validator(mode="after")
    def check_range(self):
        if self.min_temperature >= self.max_temperature:
            raise ValueError("Minimum temperature must be below maximum temperature")
        return self


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(pattern="^(ADMIN|OPERATOR|VIEWER)$")
    notification_email: str | None = Field(default=None, max_length=200)
    email_notifications: bool = False


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    role: str | None = Field(default=None, pattern="^(ADMIN|OPERATOR|VIEWER)$")
    active: bool | None = None
    notification_email: str | None = Field(default=None, max_length=200)
    email_notifications: bool | None = None


class MedicineProfileUpdate(BaseModel):
    min_temperature: float = Field(ge=-80, le=30)
    max_temperature: float = Field(ge=-30, le=50)
    warning_margin: float = Field(ge=0.1, le=10)
    max_excursion_minutes: float = Field(ge=1, le=10080)
    prediction_horizon_minutes: int = Field(ge=5, le=120)
    handling_notes: str = Field(min_length=10, max_length=1000)

    @model_validator(mode="after")
    def check_profile_range(self):
        if self.min_temperature >= self.max_temperature:
            raise ValueError("Minimum temperature must be below maximum temperature")
        return self


class SensorPacket(BaseModel):
    device_id: str = Field(min_length=2, max_length=80)
    vehicle_id: str = Field(pattern=r"^PHARMA-EV-\d{3}$")
    timestamp: str | None = None
    vehicle: dict = Field(default_factory=dict)
    battery: dict = Field(default_factory=dict)
    container: dict = Field(default_factory=dict)
    delivery: dict = Field(default_factory=dict)


class SensorDeviceRequest(BaseModel):
    device_id: str = Field(min_length=2, max_length=80)
    vehicle_id: str = Field(pattern=r"^PHARMA-EV-\d{3}$")
    topic: str = Field(min_length=3, max_length=200)


class NotificationPreferences(BaseModel):
    notification_email: str | None = Field(default=None, max_length=200)
    email_notifications: bool


class VoiceSessionCreate(BaseModel):
    vehicle_id: str | None = Field(default=None, pattern=r"^PHARMA-EV-\d{3}$")
    language: str = Field(default="auto", pattern="^(auto|hi|en|mr)$")


class VoiceTextTurn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    language: str = Field(default="auto", pattern="^(auto|hi|en|mr)$")
