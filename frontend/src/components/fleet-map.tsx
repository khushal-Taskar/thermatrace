"use client";

import {Fragment, useEffect, useMemo, useRef, useState} from "react";
import {Maximize2} from "lucide-react";
import {CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, useMap} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type {Point, Snapshot} from "@/types";
import {useMonitor} from "@/hooks/use-monitor";

const colors = {NORMAL: "#17826e", WARNING: "#d79b28", HIGH: "#df8f20", CRITICAL: "#d95752"};
const PUNE_OPERATIONS_BOUNDS = L.latLngBounds([18.05, 72.95], [19.15, 74.55]);

function MapController({fleet, focus, fitSignal}: {fleet: Snapshot[]; focus?: string; fitSignal: number}) {
  const map = useMap();
  const latestFleet = useRef(fleet);
  latestFleet.current = fleet;

  useEffect(() => {
    const container = map.getContainer();
    const recoverSize = () => map.invalidateSize({pan: false});
    recoverSize();
    const observer = new ResizeObserver(recoverSize);
    observer.observe(container);
    window.addEventListener("resize", recoverSize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", recoverSize);
    };
  }, [map]);

  useEffect(() => {
    const snapshots = latestFleet.current;
    if (focus && focus !== "ALL" && snapshots.length === 1) {
      const vehicle = snapshots[0].vehicle;
      map.setView([vehicle.latitude, vehicle.longitude], 15, {animate: true});
      return;
    }
    const points = snapshots.flatMap((snapshot) => snapshot.delivery.planned_route);
    if (points.length) map.fitBounds(L.latLngBounds(points), {padding: [34, 34], maxZoom: 13, animate: true});
  }, [map, focus, fitSignal]);

  useEffect(() => {
    if (!focus || focus === "ALL" || fleet.length !== 1) return;
    const vehicle = fleet[0].vehicle;
    map.panTo([vehicle.latitude, vehicle.longitude], {animate: true, duration: 1.2});
  }, [map, focus, fleet]);

  return null;
}

function AnimatedVehicleMarker({snapshot, onSelect}: {snapshot: Snapshot; onSelect: (id: string) => void}) {
  const markerRef = useRef<L.Marker | null>(null);
  const initialPosition = useRef<Point>([snapshot.vehicle.latitude, snapshot.vehicle.longitude]);
  const frameRef = useRef<number | null>(null);
  const id = snapshot.vehicle.vehicle_id;
  const color = colors[snapshot.risk.risk_level];
  const moving = snapshot.vehicle.speed > 0.5;
  const icon = useMemo(() => L.divIcon({
    className: `vehicle-pin${moving ? " vehicle-pin-moving" : ""}`,
    html: `<div style="--pin-color:${color}"><span class="vehicle-pulse"></span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M3 6h12v11H3zM15 10h4l3 4v3h-7M7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4M18 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4"/></svg><b>${id.slice(-3)}</b></div>`,
    iconSize: [57, 32],
    iconAnchor: [28, 16],
  }), [color, id, moving]);

  useEffect(() => {
    const marker = markerRef.current;
    if (!marker) return;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    const from = marker.getLatLng();
    const to = L.latLng(snapshot.vehicle.latitude, snapshot.vehicle.longitude);
    if (from.distanceTo(to) > 5000) {
      marker.setLatLng(to);
      return;
    }
    const started = performance.now();
    const animate = (now: number) => {
      const progress = Math.min(1, (now - started) / 2800);
      marker.setLatLng([from.lat + (to.lat - from.lat) * progress, from.lng + (to.lng - from.lng) * progress]);
      if (progress < 1) frameRef.current = requestAnimationFrame(animate);
    };
    frameRef.current = requestAnimationFrame(animate);
    return () => { if (frameRef.current !== null) cancelAnimationFrame(frameRef.current); };
  }, [snapshot.vehicle.latitude, snapshot.vehicle.longitude]);

  return <Marker ref={markerRef} position={initialPosition.current} icon={icon}><Popup><strong>{id} · {snapshot.vehicle.vehicle_name}</strong><p>{snapshot.container.medicine_name}<br/>{snapshot.vehicle.speed} km/h · SOC {snapshot.battery.soc.toFixed(1)}%<br/>Risk {snapshot.risk.risk_score}/100<br/>{snapshot.delivery.destination}</p><button className="map-detail" onClick={() => onSelect(id)}>Open vehicle details →</button></Popup></Marker>;
}

export default function FleetMap({fleet, focus}: {fleet: Snapshot[]; focus?: string}) {
  const {select} = useMonitor();
  const [failed, setFailed] = useState(false);
  const [fitSignal, setFitSignal] = useState(0);

  return <div className="map-wrap"><MapContainer center={[18.557, 73.845]} zoom={12} minZoom={10} maxZoom={18} maxBounds={PUNE_OPERATIONS_BOUNDS} maxBoundsViscosity={1} scrollWheelZoom className="fleet-map"><MapController fleet={fleet} focus={focus} fitSignal={fitSignal}/><TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' minZoom={10} maxZoom={19} keepBuffer={4} updateWhenZooming={false} eventHandlers={{tileerror: () => setFailed(true), load: () => setFailed(false)}}/>{fleet.map((snapshot) => {const id=snapshot.vehicle.vehicle_id,color=colors[snapshot.risk.risk_level],routeIndex=Math.min(snapshot.delivery.planned_route.length-1,Math.round(snapshot.delivery.delivery_progress/100*(snapshot.delivery.planned_route.length-1)));return <Fragment key={id}><Polyline positions={snapshot.delivery.planned_route} pathOptions={{color:"#71968b",weight:3,opacity:.65,dashArray:"7 7"}}/><Polyline positions={snapshot.delivery.actual_route} pathOptions={{color,weight:4,opacity:.9}}/><CircleMarker center={snapshot.delivery.planned_route[0]} radius={4} pathOptions={{color:"#17826e",fillOpacity:1}}/><CircleMarker center={snapshot.delivery.planned_route.at(-1)!} radius={5} pathOptions={{color:"#233f38",fillOpacity:1}}/><AnimatedVehicleMarker snapshot={snapshot} onSelect={select}/>{snapshot.delivery.route_deviation_distance>.5&&<Polyline positions={[snapshot.delivery.current_location,snapshot.delivery.planned_route[routeIndex]]} pathOptions={{color:"#d95752",dashArray:"4 4",weight:2}}/>}</Fragment>;})}</MapContainer><button className="map-fit-control" onClick={() => setFitSignal((value) => value + 1)} title="Fit all live routes" aria-label="Fit all live routes"><Maximize2 size={15}/><span>Fit fleet</span></button><div className="map-legend"><span><i style={{background:"#17826e"}}/>Healthy</span><span><i style={{background:"#df8f20"}}/>Attention</span><span><i style={{background:"#d95752"}}/>Critical</span><span className="route-key">┄ Planned route</span></div>{failed&&<div className="tile-notice">The free OpenStreetMap basemap could not load. Live routes and positions are still available.</div>}<span className="map-region">{focus&&focus!=="ALL"?"FOLLOWING LIVE VEHICLE":"PUNE METROPOLITAN REGION"}</span></div>;
}
