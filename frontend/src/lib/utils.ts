import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
export function label(value: string) { return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()); }
export function time(value: string) { return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value+"Z").toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"}); }
export function download(name: string, body: string, type="text/csv") { const url=URL.createObjectURL(new Blob([body],{type})); const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
