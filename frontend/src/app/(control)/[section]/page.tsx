import {notFound} from "next/navigation";
import {ControlPage} from "@/features/control-page";
const sections=["dashboard","fleet","tracking","vehicles","battery","containers","deliveries","risk","voice-agent","alerts","analytics","reports","settings"];
export function generateStaticParams(){return sections.map(section=>({section}));}
export default async function Page({params}:{params:Promise<{section:string}>}){const {section}=await params;if(!sections.includes(section))notFound();return <ControlPage section={section}/>;}
