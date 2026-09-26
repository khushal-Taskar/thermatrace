"""Auditable in-app dispatch and accelerated rescue-vehicle simulation."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from ..models import Delivery, DispatchMessage, RescueMission, Route, Vehicle, utcnow
from .routing import RoutingError, osrm_route

ACTIVE = ("TO_PICKUP", "AT_PICKUP", "TO_DESTINATION")


def _distance(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlng = lat2-lat1, math.radians(b[1]-a[1])
    value = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
    return 12742 * math.asin(min(1, math.sqrt(value)))


def _length(points):
    return sum(_distance(a, b) for a, b in zip(points, points[1:]))


def _point_at_distance(points, distance):
    remaining = distance
    for a, b in zip(points, points[1:]):
        segment = _distance(a, b)
        if remaining <= segment:
            fraction = remaining / segment if segment else 1
            return [round(a[0] + (b[0]-a[0])*fraction, 6), round(a[1] + (b[1]-a[1])*fraction, 6)]
        remaining -= segment
    return list(points[-1])


def serialize_mission(item):
    pickup_km = _length(item.pickup_route)
    onward_km = _length(item.onward_route)
    remaining = 0 if item.status in {"COMPLETED", "CANCELLED"} else (1-item.progress) * (pickup_km if item.status == "TO_PICKUP" else onward_km)
    if item.status == "TO_PICKUP":
        remaining += onward_km
    eta = utcnow() + timedelta(minutes=remaining/40*60 + (3 if item.status == "TO_PICKUP" else 0))
    return {
        "id": item.id, "incident_vehicle_id": item.incident_vehicle_id,
        "replacement_vehicle_id": item.replacement_vehicle_id,
        "shipment_id": item.shipment_id, "source": item.source,
        "destination": item.destination, "breakdown_location": item.breakdown_location,
        "pickup_route": item.pickup_route, "onward_route": item.onward_route,
        "route_provider": item.route_provider, "position": item.position,
        "status": item.status, "progress": round(item.progress*100, 1),
        "speed": item.speed, "distance_remaining": round(remaining, 1),
        "estimated_arrival_time": eta.isoformat(),
        "created_at": item.created_at.isoformat(),
        "transferred_at": item.transferred_at.isoformat() if item.transferred_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def serialize_message(item):
    return {
        "id": item.id, "point": item.point,
        "incident_vehicle_id": item.incident_vehicle_id,
        "mission_id": item.mission_id, "voice_session_id": item.voice_session_id,
        "sender": item.sender, "text": item.text, "status": item.status,
        "created_at": item.created_at.isoformat(),
        "read_at": item.read_at.isoformat() if item.read_at else None,
    }


def current_mission(db, vehicle_id):
    return db.scalar(select(RescueMission).where(
        RescueMission.incident_vehicle_id == vehicle_id,
        RescueMission.status.in_((*ACTIVE, "COMPLETED")),
    ).order_by(RescueMission.id.desc()))


def create_rescue_mission(db, snapshot):
    vehicle_id = snapshot["vehicle"]["vehicle_id"]
    existing = current_mission(db, vehicle_id)
    reset_at = db.get(Vehicle, vehicle_id).state.get("reset_at")
    if existing and (not reset_at or existing.created_at.replace(tzinfo=timezone.utc) >= datetime.fromisoformat(reset_at)):
        return existing, False
    delivery = db.scalar(select(Delivery).where(Delivery.vehicle_id == vehicle_id))
    route = db.get(Route, delivery.route_id)
    original = route.planned_route
    stopped = [snapshot["vehicle"]["latitude"], snapshot["vehicle"]["longitude"]]
    nearest = min(range(len(original)), key=lambda i: _distance(original[i], stopped))
    pickup = [*original[:nearest+1], stopped]
    onward = [stopped, *original[nearest+1:]]
    if len(pickup) < 2:
        pickup = [original[0], stopped]
    if len(onward) < 2:
        onward = [stopped, original[-1]]
    used = set(db.scalars(select(RescueMission.replacement_vehicle_id)).all())
    number = next(i for i in range(1, 1000) if f"PHARMA-RESCUE-{i:03}" not in used)
    mission = RescueMission(
        incident_vehicle_id=vehicle_id,
        replacement_vehicle_id=f"PHARMA-RESCUE-{number:03}",
        shipment_id=snapshot["container"]["shipment_id"],
        source=route.source, destination=route.destination,
        breakdown_location=stopped, pickup_route=pickup, onward_route=onward,
        route_provider="STORED_ROUTE", position=list(original[0]),
        status="TO_PICKUP", progress=0, speed=0, transfer_ticks=0,
    )
    db.add(mission)
    db.flush()
    return mission, True


def send_point_message(db, point, vehicle_id, text, mission_id=None, session_id=None, sender="AI_DISPATCH"):
    if point not in {"A", "B"}:
        raise ValueError("Point must be A or B")
    item = DispatchMessage(
        point=point, incident_vehicle_id=vehicle_id, text=text,
        mission_id=mission_id, voice_session_id=session_id,
        sender=sender, status="DELIVERED",
    )
    db.add(item)
    db.flush()
    return item


def advance_missions(db, interval):
    for item in db.scalars(select(RescueMission).where(RescueMission.status.in_(ACTIVE))):
        if item.status == "AT_PICKUP":
            item.transfer_ticks += 1
            if item.transfer_ticks >= 2:
                item.status = "TO_DESTINATION"
                item.progress = 0
                item.transferred_at = utcnow()
            continue
        route = item.pickup_route if item.status == "TO_PICKUP" else item.onward_route
        route_km = max(.01, _length(route))
        item.speed = 40
        # Demo animation runs 20x faster than road time; speed remains the
        # simulated road speed and the UI labels this acceleration.
        item.progress = min(1, item.progress + (item.speed * interval * 20 / 3600) / route_km)
        item.position = _point_at_distance(route, route_km * item.progress)
        if item.progress >= 1:
            item.speed = 0
            if item.status == "TO_PICKUP":
                item.status = "AT_PICKUP"
                item.position = item.breakdown_location
            else:
                item.status = "COMPLETED"
                item.completed_at = utcnow()


def refine_rescue_routes(mission_id, session_factory, base_url):
    """Optional public-OSRM refinement after dispatch has already committed."""
    with session_factory() as db:
        item = db.get(RescueMission, mission_id)
        if not item or item.status not in ACTIVE or item.route_provider != "STORED_ROUTE":
            return
        try:
            pickup = osrm_route([item.pickup_route[0], item.breakdown_location], base_url, timeout=5)
            onward = osrm_route([item.breakdown_location, item.onward_route[-1]], base_url, timeout=5)
        except RoutingError:
            return
        # Preserve progress and map position; route refinement only changes
        # the geometry of journeys that have not started yet.
        if item.status == "TO_PICKUP" and item.progress < .02:
            item.pickup_route = pickup["planned_route"]
        if item.status in ("TO_PICKUP", "AT_PICKUP"):
            item.onward_route = onward["planned_route"]
        item.route_provider = "OSRM"
        db.commit()
