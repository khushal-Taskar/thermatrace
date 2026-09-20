"use client";
import {useEffect,useRef} from "react";
import {motion,AnimatePresence} from "framer-motion";
import {X} from "lucide-react";
import {Button} from "./ui/button";
export function Drawer({open,onClose,title,subtitle,children}:{open:boolean;onClose:()=>void;title:string;subtitle?:string;children:React.ReactNode}){
 const ref=useRef<HTMLElement>(null);
 useEffect(()=>{if(!open)return;const previous=document.activeElement as HTMLElement;ref.current?.querySelector<HTMLButtonElement>("button")?.focus();const old=document.body.style.overflow;document.body.style.overflow="hidden";function key(e:KeyboardEvent){if(e.key==="Escape")onClose();if(e.key==="Tab"){const items=ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, textarea, a[href]');if(!items?.length)return;const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}document.addEventListener("keydown",key);return()=>{document.body.style.overflow=old;document.removeEventListener("keydown",key);previous?.focus();};},[open,onClose]);
 return <AnimatePresence>{open&&<div className="drawer-layer"><motion.div className="drawer-shade" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={onClose}/><motion.aside ref={ref} role="dialog" aria-modal="true" aria-label={title} className="drawer" initial={{x:80,opacity:0}} animate={{x:0,opacity:1}} exit={{x:80,opacity:0}} transition={{duration:.2}}><header><div><small>{subtitle}</small><h2>{title}</h2></div><Button variant="ghost" size="icon" aria-label="Close panel" onClick={onClose}><X size={20}/></Button></header><div className="drawer-content">{children}</div></motion.aside></div>}</AnimatePresence>;
}
