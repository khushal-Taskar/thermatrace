import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={title:"ThermaTrace | Pharmaceutical Logistics",description:"AI-based pharmaceutical transportation and cold-chain risk monitoring — software simulation"};
export default function RootLayout({children}:{children:React.ReactNode}) {return <html lang="en" dir="ltr" suppressHydrationWarning><body>{children}</body></html>;}
