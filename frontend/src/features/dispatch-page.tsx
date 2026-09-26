"use client";

import {useState} from "react";
import dynamic from "next/dynamic";
import {ArrowRight, Clock3, MapPin, MessageSquare, Send, ShieldAlert, Truck} from "lucide-react";
import {useMonitor} from "@/hooks/use-monitor";
import {api} from "@/lib/api";
import {Card} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {time} from "@/lib/utils";
import type {DispatchMessage, RescueMission} from "@/types";

const FleetMap=dynamic(()=>import("@/components/fleet-map"),{ssr:false,loading:()=> <div className="map-skeleton skeleton">Loading recovery map…</div>});

export function DispatchPage(){
  const {data,user,refresh,notify}=useMonitor();
  const [vehicleId,setVehicleId]=useState("PHARMA-EV-001");
  const [drafts,setDrafts]=useState({A:"",B:""});
  const [busy,setBusy]=useState(false);
  if(!data)return null;
  const selected=data.fleet.find(item=>item.vehicle.vehicle_id===vehicleId)||data.fleet[0];
  if(!selected)return null;
  const id=selected.vehicle.vehicle_id;
  const mission=(data.rescue_missions||[]).find(item=>item.incident_vehicle_id===id && ["TO_PICKUP","AT_PICKUP","TO_DESTINATION"].includes(item.status))
    ||(data.rescue_missions||[]).find(item=>item.incident_vehicle_id===id);
  const canDispatch=user?.role==="ADMIN"||user?.role==="OPERATOR";
  const messages=(data.dispatch_messages||[]).filter(item=>item.incident_vehicle_id===id);

  async function startRescue(){
    setBusy(true);
    try { await api<RescueMission>("/dispatch/rescue",{method:"POST",body:JSON.stringify({vehicle_id:id})}); await refresh(); notify("Replacement mission started; both in-app point inboxes updated"); }
    catch(error){notify((error as Error).message);} finally{setBusy(false);}
  }
  async function send(point:"A"|"B"){
    const text=drafts[point].trim();
    if(!text)return;
    setBusy(true);
    try { await api<DispatchMessage>("/dispatch/messages",{method:"POST",body:JSON.stringify({point,vehicle_id:id,text})}); setDrafts(current=>({...current,[point]:""})); await refresh(); notify(`Message delivered to the Point ${point} in-app inbox`); }
    catch(error){notify((error as Error).message);} finally{setBusy(false);}
  }
  async function markRead(messageId:number){
    try { await api(`/dispatch/messages/${messageId}/read`,{method:"POST"}); await refresh(); }
    catch(error){notify((error as Error).message);}
  }

  return <div className="dispatch-page">
    <div className="dispatch-bar"><label>Incident vehicle<select value={id} onChange={event=>setVehicleId(event.target.value)}>{data.fleet.map(item=><option key={item.vehicle.vehicle_id} value={item.vehicle.vehicle_id}>{item.vehicle.vehicle_id} · {item.vehicle.driver_name}</option>)}</select></label><span><ShieldAlert size={15}/> Software simulation · messages stay inside ThermaTrace</span></div>
    <div className="dispatch-top-grid"><Card className="dispatch-map-card"><div className="card-heading"><div><span className="eyebrow">RECOVERY ROUTE</span><h2>Replacement vehicle movement</h2></div><MapPin size={20}/></div><FleetMap fleet={[selected]} missions={mission?[mission]:[]}/><div className="dispatch-map-caption"><span><i className="dispatch-dot pickup"/> Point A → stopped vehicle</span><span><i className="dispatch-dot onward"/> Pickup → Point B</span><span>{mission?.route_provider==="OSRM"?"OSRM road route":"Stored road route; OSRM refinement pending"}</span></div></Card>
    <Card className="dispatch-mission"><span className="eyebrow">INCIDENT RESPONSE</span><h2>{mission?mission.replacement_vehicle_id:"No replacement assigned"}</h2><p className="muted">{mission?`${mission.shipment_id} · ${mission.status.replaceAll("_"," ")}`:"Start a controlled breakdown scenario and dispatch a virtual vehicle."}</p>{mission?<><div className="dispatch-journey"><span className={mission.status==="TO_PICKUP"?"active":""}>To pickup</span><ArrowRight size={14}/><span className={mission.status==="AT_PICKUP"?"active":""}>Container handover</span><ArrowRight size={14}/><span className={mission.status==="TO_DESTINATION"?"active":""}>To destination</span></div><div className="dispatch-progress"><div style={{width:`${mission.progress}%`}}/></div><dl className="detail-list"><dt>Simulated road speed</dt><dd>{mission.speed} km/h</dd><dt>Distance remaining</dt><dd>{mission.distance_remaining} km</dd><dt>Road ETA (unaccelerated)</dt><dd>{time(mission.estimated_arrival_time)}</dd><dt>Medicine remaining safe time</dt><dd>{selected.container.remaining_safe_time_minutes.toFixed(0)} min estimate</dd><dt>Route provider</dt><dd>{mission.route_provider}</dd></dl></>:<div className="dispatch-standby"><Truck size={26}/><p>The replacement will move from Point A to the stopped vehicle, pause for a simulated handover, then follow a road route to Point B.</p></div>}{canDispatch&&<Button onClick={startRescue} disabled={busy||Boolean(mission&&mission.status!=="CANCELLED")}><Truck size={16}/>{busy?"Dispatching…":mission?mission.status==="COMPLETED"?"Mission completed":mission.status==="CANCELLED"?"Start new recovery scenario":"Mission in progress":"Simulate breakdown & dispatch"}</Button>}<small className="dispatch-disclaimer"><Clock3 size={13}/> Demo travel runs 20× real time. Safe-time is a forecast, not a medicine-release decision.</small></Card></div>
    <div className="dispatch-chats"><PointChat point="A" title={selected.delivery.source} subtitle="Origin operations & replacement dispatch" messages={messages.filter(item=>item.point==="A")} draft={drafts.A} setDraft={value=>setDrafts(current=>({...current,A:value}))} send={()=>send("A")} markRead={markRead} busy={busy} canDispatch={canDispatch}/><PointChat point="B" title={selected.delivery.destination} subtitle="Receiving site & delivery delay" messages={messages.filter(item=>item.point==="B")} draft={drafts.B} setDraft={value=>setDrafts(current=>({...current,B:value}))} send={()=>send("B")} markRead={markRead} busy={busy} canDispatch={canDispatch}/></div>
  </div>;
}

function PointChat({point,title,subtitle,messages,draft,setDraft,send,markRead,busy,canDispatch}:{point:"A"|"B";title:string;subtitle:string;messages:DispatchMessage[];draft:string;setDraft:(value:string)=>void;send:()=>void;markRead:(id:number)=>void;busy:boolean;canDispatch:boolean}){
  return <Card className="point-chat"><header><div className="point-badge">{point}</div><div><span className="eyebrow">POINT {point} · IN-APP INBOX</span><h2>{title}</h2><p>{subtitle}</p></div><MessageSquare size={18}/></header><div className="point-messages" aria-live="polite">{messages.length?messages.map(item=><div key={item.id} className="point-message"><div><strong>{item.sender==="AI_DISPATCH"?"AI dispatch":"Operations"}</strong><span>{time(item.created_at)} · {item.status}</span></div><p>{item.text}</p>{item.status==="DELIVERED"&&canDispatch&&<button onClick={()=>markRead(item.id)}>Mark read</button>}</div>):<div className="point-empty">No messages yet. Voice commands and manual dispatch appear here separately for Point {point}.</div>}</div>{canDispatch&&<div className="point-compose"><input aria-label={`Message Point ${point}`} value={draft} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==="Enter")send();}} placeholder={`Message Point ${point}…`}/><Button size="icon" aria-label={`Send to Point ${point}`} disabled={busy||!draft.trim()} onClick={send}><Send size={16}/></Button></div>}</Card>;
}
