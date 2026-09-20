"use client";
import {createContext,useContext,useEffect,useRef,useState,useCallback} from "react";
import {useRouter} from "next/navigation";
import {api} from "@/lib/api";
import type {Overview,Snapshot,UserAccount} from "@/types";
interface MonitorContext {data:Overview|null;user:UserAccount|null;connection:string;error:string;selected:Snapshot|null;select:(id:string|null)=>void;refresh:()=>Promise<void>;notify:(text:string)=>void;}
const Context=createContext<MonitorContext|null>(null);
export function MonitorProvider({children}:{children:React.ReactNode}) {
  const [data,setData]=useState<Overview|null>(null),[user,setUser]=useState<UserAccount|null>(null),[connection,setConnection]=useState("Connecting"),[error,setError]=useState(""),[selectedId,setSelectedId]=useState<string|null>(null),[toast,setToast]=useState("");
  const router=useRouter(); const toastTimer=useRef<ReturnType<typeof setTimeout>|null>(null),knownAlerts=useRef<Set<number>|null>(null);
  const applyOverview=useCallback((next:Overview)=>{const current=new Set(next.alerts.map(a=>a.id));if(knownAlerts.current&&typeof Notification!=="undefined"&&Notification.permission==="granted"&&localStorage.getItem("thermatrace-browser-notifications")==="enabled"){next.alerts.filter(a=>a.active&&!a.acknowledged&&["HIGH","CRITICAL"].includes(a.severity)&&!knownAlerts.current!.has(a.id)).slice(0,3).forEach(a=>{const notice=new Notification(`${a.severity}: ${a.type.replaceAll("_"," ")}`,{body:`${a.vehicle_id} · ${a.reason}`,tag:`thermatrace-alert-${a.id}`});notice.onclick=()=>{window.focus();router.push("/alerts");};});}knownAlerts.current=current;setData(next);},[router]);
  const notify=useCallback((text:string)=>{setToast(text);if(toastTimer.current)clearTimeout(toastTimer.current);toastTimer.current=setTimeout(()=>setToast(""),5000);},[]);
  const refresh=useCallback(async()=>{try {applyOverview(await api<Overview>("/overview"));setError("");}catch(e){setError((e as Error).message);}},[applyOverview]);
  useEffect(()=>{
    let alive=true,socket:WebSocket|null=null,timer:ReturnType<typeof setTimeout>|null=null,heartbeat:ReturnType<typeof setInterval>|null=null,retries=0;
    const stopHeartbeat=()=>{if(heartbeat){clearInterval(heartbeat);heartbeat=null;}};
    async function connect(){
      try {
        const identity=await api<UserAccount>("/auth/me");
        const initial=await api<Overview>("/overview");if(!alive)return;setUser(identity);applyOverview(initial);setError("");
        const {ticket}=await api<{ticket:string}>("/ws-ticket",{method:"POST"});if(!alive)return;
        const base=process.env.NEXT_PUBLIC_WS_URL || `${location.protocol==="https:" ? "wss" : "ws"}://${location.hostname}:8100/ws/telemetry`;
        socket=new WebSocket(`${base}?ticket=${encodeURIComponent(ticket)}`);
        socket.onopen=()=>{if(alive){setConnection("Live");retries=0;stopHeartbeat();heartbeat=setInterval(()=>{if(socket?.readyState===WebSocket.OPEN)socket.send("ping");},30000);}};
        socket.onmessage=(event)=>{if(alive){applyOverview(JSON.parse(event.data));setError("");}};
        socket.onclose=()=>{stopHeartbeat();if(alive){setConnection("Reconnecting");timer=setTimeout(connect,Math.min(15000,1000*2**retries++));}};
        socket.onerror=()=>{if(alive)setConnection("Reconnecting");};
      } catch(e){if(!alive)return;const message=(e as Error).message;if(message.includes("sign in")){router.replace("/login");return;}setError(message);setConnection("Offline");timer=setTimeout(connect,5000);}
    }
    connect();return ()=>{alive=false;if(timer)clearTimeout(timer);stopHeartbeat();socket?.close();if(toastTimer.current)clearTimeout(toastTimer.current);};
  },[router,applyOverview]);
  return <Context.Provider value={{data,user,connection,error,selected:data?.fleet.find(s=>s.vehicle.vehicle_id===selectedId)||null,select:setSelectedId,refresh,notify}}>{children}{toast&&<div role="status" className="toast">{toast}</div>}</Context.Provider>;
}
export function useMonitor(){const context=useContext(Context);if(!context)throw new Error("MonitorProvider is required");return context;}
