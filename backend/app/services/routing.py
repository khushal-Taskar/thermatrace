"""OSRM road-routing adapter with a deterministic stored-route fallback."""
from datetime import timezone
import httpx
from ..models import utcnow


class RoutingError(RuntimeError):
    pass


def osrm_route(points, base_url, timeout=12):
    if len(points)<2:
        raise RoutingError("A route needs at least two coordinates")
    waypoints=[points[0],*points[1:-1:2],points[-1]] if len(points)>3 else points
    coordinates=";".join(f"{lng},{lat}" for lat,lng in waypoints)
    url=f"{base_url.rstrip('/')}/route/v1/driving/{coordinates}"
    try:
        response=httpx.get(url,params={"overview":"full","geometries":"geojson","steps":"false"},timeout=timeout,follow_redirects=True)
        response.raise_for_status()
        payload=response.json()
    except (httpx.HTTPError,ValueError) as exc:
        raise RoutingError(f"OSRM request failed: {exc}") from exc
    if payload.get("code")!="Ok" or not payload.get("routes"):
        raise RoutingError(payload.get("message") or "OSRM did not return a route")
    route=payload["routes"][0]
    geometry=[[round(lat,6),round(lng,6)] for lng,lat in route["geometry"]["coordinates"]]
    return {"planned_route":geometry,"distance_km":round(route["distance"]/1000,2),"duration_minutes":round(route["duration"]/60,1),"provider":"OSRM","last_routed_at":utcnow()}


def refresh_route(route, base_url):
    result=osrm_route(route.planned_route,base_url)
    for key,value in result.items():
        setattr(route,key,value)
    return result

