import {cn,label} from "@/lib/utils";
export function Badge({value}:{value:string}) {return <span className={cn("badge",["CRITICAL","FAULT","FAILED"].includes(value)?"critical":["HIGH","WARNING","DELAYED"].includes(value)?"warning":["NORMAL","SAFE","RUNNING","DELIVERED","IN_TRANSIT"].includes(value)?"normal":"neutral")}><i/>{label(value)}</span>;}
export function Progress({value,tone="teal"}:{value:number;tone?:string}) {return <div className="progress"><span className={tone} style={{width:`${Math.min(100,Math.max(0,value))}%`}}/></div>;}
export function Empty({text="No records match this view."}:{text?:string}) {return <div className="empty">{text}</div>;}
