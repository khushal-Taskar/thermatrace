from sqlalchemy import select
from ..models import User, Vehicle, Container, Delivery, Route, SystemSettings, MedicineProfile
from ..config import settings
from ..services.auth import hash_password

# Synthetic route checkpoints around Pune. These are demo polylines, not turn-by-turn road guidance.
ROUTES = [
    ("Hinjewadi Pharma Hub", "Ruby Hall Clinic", [[18.5913,73.7389],[18.582,73.765],[18.564,73.785],[18.552,73.805],[18.538,73.835],[18.533,73.865],[18.536,73.877]], 28),
    ("Wakad Distribution Center", "Sahyadri Hospital", [[18.598,73.763],[18.582,73.777],[18.557,73.792],[18.536,73.808],[18.515,73.825],[18.509,73.841]], 25),
    ("Serum Logistics Depot", "Noble Hospital", [[18.487,73.957],[18.495,73.947],[18.504,73.936],[18.513,73.926],[18.518,73.914],[18.519,73.899]], 18),
    ("Pimpri Cold Store", "KEM Hospital", [[18.627,73.8],[18.605,73.817],[18.579,73.833],[18.557,73.847],[18.537,73.861],[18.52,73.875]], 30),
    ("Kharadi Pharma Park", "Deenanath Mangeshkar Hospital", [[18.559,73.948],[18.552,73.925],[18.543,73.9],[18.532,73.878],[18.522,73.853],[18.51,73.829]], 26),
]

PROFILES = [
    ("INSULIN_2_8", "Insulin glargine", 2, 8, .7, 30, 15, "Demo refrigerated insulin profile. Quarantine after sustained excursion and verify manufacturer stability data."),
    ("VACCINE_2_8", "Influenza vaccine", 2, 8, .6, 20, 10, "Demo vaccine profile with a conservative excursion budget. Validate the exact product label and national guidance."),
    ("BIOLOGIC_2_8", "Adalimumab biologic", 2, 8, .5, 15, 10, "Demo biologic profile. Protect from freezing and escalate warming trends early."),
    ("EPO_2_8", "Erythropoietin", 2, 8, .6, 20, 10, "Demo erythropoietin profile. Protect from light, freezing, and prolonged vibration."),
    ("HEPB_2_8", "Hepatitis B vaccine", 2, 8, .5, 15, 10, "Demo freeze-sensitive vaccine profile. Inspect for freeze exposure and follow validated handling instructions."),
]


def seed_database(db):
    admin=db.scalar(select(User).where(User.email==settings.admin_email))
    if not admin:
        db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password), role="ADMIN", notification_email=settings.admin_email))
        db.commit()
    elif admin.role!="ADMIN":
        admin.role="ADMIN"; db.commit()
    demo_users=[
        ("operator@thermatrace.local","Fleet Operator","OperatorDemo!2026","OPERATOR"),
        ("viewer@thermatrace.local","Quality Viewer","ViewerDemo!2026","VIEWER"),
    ]
    for email,name,password,role in demo_users:
        if not db.scalar(select(User).where(User.email==email)):
            db.add(User(email=email,name=name,password_hash=hash_password(password),role=role))
    for profile_id,name,minimum,maximum,margin,budget,horizon,notes in PROFILES:
        if not db.get(MedicineProfile,profile_id):
            db.add(MedicineProfile(id=profile_id,name=name,min_temperature=minimum,max_temperature=maximum,warning_margin=margin,max_excursion_minutes=budget,prediction_horizon_minutes=horizon,handling_notes=notes))
    db.commit()
    if not db.get(SystemSettings, 1):
        db.add(SystemSettings(id=1))
        db.commit()
    if db.scalar(select(Vehicle)):
        profiles={p.name:p for p in db.scalars(select(MedicineProfile))}
        for container in db.scalars(select(Container)):
            profile=profiles.get(container.medicine_name)
            if profile and container.medicine_profile_id!=profile.id:
                container.medicine_profile_id=profile.id
                container.min_temperature=profile.min_temperature
                container.max_temperature=profile.max_temperature
        db.commit()
        return
    drivers = ["Aarav Deshmukh", "Priya Nair", "Rohan Kulkarni", "Neha Shah", "Vikram Patil"]
    medicines = ["Insulin glargine", "Influenza vaccine", "Adalimumab biologic", "Erythropoietin", "Hepatitis B vaccine"]
    for i, (source,destination,points,distance) in enumerate(ROUTES):
        n=i+1
        db.add(Vehicle(id=f"PHARMA-EV-{n:03}", name=["Meridian", "Solstice", "Aster", "Atlas", "Nova"][i], driver_name=drivers[i], baseline_soc=[82,56,18,68,91][i], soh=[98,95,88,93,99][i], scenario=["NORMAL_DELIVERY","DELIVERY_DELAY","CONTAINER_TEMPERATURE_EXCURSION","BATTERY_OVERHEATING","NORMAL_DELIVERY"][i]))
        profile=next(p for p in PROFILES if p[1]==medicines[i])
        db.add(Container(id=f"CNT-{n:03}", shipment_id=f"SHP-2026-{n:03}", medicine_name=medicines[i], batch_number=f"RX26-09-{n:04}", min_temperature=profile[2], max_temperature=profile[3], medicine_profile_id=profile[0]))
        db.add(Route(id=f"RTE-{n:03}", source=source, destination=destination, planned_route=points, distance_km=distance))
    db.commit()
    for n in range(1,6):
        db.add(Delivery(id=f"DLV-{n:03}", vehicle_id=f"PHARMA-EV-{n:03}", container_id=f"CNT-{n:03}", route_id=f"RTE-{n:03}"))
    db.commit()
