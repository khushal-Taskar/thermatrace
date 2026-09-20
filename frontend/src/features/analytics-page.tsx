"use client";
import {useState} from "react";
import {Download,ChartNoAxesCombined} from "lucide-react";
import {useMonitor} from "@/hooks/use-monitor";
import {TelemetryChart,type Metric,units} from "@/components/chart";
import {Card} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {api} from "@/lib/api";
import {download} from "@/lib/utils";
import type {History} from "@/types";
export function AnalyticsPage(){const {data,notify}=useMonitor();const [vehicle,setVehicle]=useState("PHARMA-EV-003"),[hours,setHours]=useState(1),[group,setGroup]=useState("All signals");const metrics:Metric[]=group==="Battery"?["soc","soh","battery_temperature","pack_current"]:group==="Cold chain"?["temperature","predicted_temperature","excursion_duration_minutes","remaining_safe_time_minutes","humidity"]:group==="Delivery"?["speed","delay_minutes","risk_score"]:["soc","soh","battery_temperature","motor_temperature","speed","temperature","predicted_temperature","excursion_duration_minutes","remaining_safe_time_minutes","humidity","risk_score","delay_minutes"];
 async function exportCsv(){try{const rows=await api<History[]>(`/history?vehicle_id=${vehicle}&hours=${hours}`);const keys:["timestamp","vehicle_id",...Metric[]]=["timestamp","vehicle_id",...Object.keys(units) as Metric[]];download(`${vehicle}-telemetry-${hours}h.csv`,[keys.join(","),...rows.map(row=>keys.map(k=>row[k]).join(","))].join("\n"));notify("Historical telemetry exported.");}catch(e){notify((e as Error).message);}}
 return <><div className="toolbar"><div><select aria-label="Analytics vehicle" value={vehicle} onChange={e=>setVehicle(e.target.value)}>{data?.fleet.map(s=><option key={s.vehicle.vehicle_id}>{s.vehicle.vehicle_id}</option>)}</select><select aria-label="Analytics time range" value={hours} onChange={e=>setHours(Number(e.target.value))}>{[1,6,24,168,720].map(h=><option key={h} value={h}>{h===1?"Last hour":h<24?`Last ${h} hours`:h===24?"Last 24 hours":`Last ${h/24} days`}</option>)}</select></div><Button variant="outline" size="sm" onClick={exportCsv}><Download size={15}/>Export telemetry</Button></div><div className="segmented analytics-tabs">{["All signals","Battery","Cold chain","Delivery"].map(g=><button key={g} onClick={()=>setGroup(g)} className={group===g?"active":""}>{g}</button>)}</div><div className="analytics-grid">{metrics.map(metric=><Card key={metric}><TelemetryChart metric={metric} vehicleId={vehicle} hours={hours}/></Card>)}</div><div className="info-callout"><ChartNoAxesCombined size={19}/><p>Charts preserve simulator versus MQTT provenance and include temperature forecasts, excursion duration, and remaining-safe-time history. Data is retained for 30 days; no missing values are fabricated. Time series refresh every 12 seconds.</p></div></>;
}
