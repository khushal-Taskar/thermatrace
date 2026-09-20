import { cn } from "@/lib/utils";
export function Card({className,...props}:React.ComponentProps<"section">) {return <section data-slot="card" className={cn("card",className)} {...props}/>;}
