import {MonitorProvider} from "@/hooks/use-monitor";
import {Shell} from "@/components/shell";
import {cookies} from "next/headers";
import {redirect} from "next/navigation";
export default async function ControlLayout({children}:{children:React.ReactNode}) {
 const token=(await cookies()).get("pharma_session")?.value;
 if(!token)redirect("/login");
 let unauthorized=false;
 try{const response=await fetch(`${process.env.BACKEND_URL||"http://127.0.0.1:8100"}/api/auth/me`,{headers:{Cookie:`pharma_session=${token}`},cache:"no-store"});unauthorized=response.status===401;}catch{/* Client reconnect view handles a temporarily unavailable backend. */}
 if(unauthorized)redirect("/login");
 return <MonitorProvider><Shell>{children}</Shell></MonitorProvider>;
}
