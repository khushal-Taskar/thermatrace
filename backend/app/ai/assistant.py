"""Structured local assistant; no generated SQL, no external network dependencies."""
import re
from ..services.monitoring import overview, report


def answer_question(db, question):
    data=overview(db)
    fleet=data["fleet"]
    q=question.lower()
    vehicle_match=re.search(r"(?:pharma[- ]ev[- ]|vehicle\s+v?|\bv)(\d{1,3})", q)
    vehicle_id=f"PHARMA-EV-{int(vehicle_match.group(1)):03}" if vehicle_match else None
    hours_match=re.search(r"(?:last|past)\s+(\d+)\s*(hour|day)",q)
    hours=min(720,int(hours_match.group(1))*(24 if hours_match and hours_match.group(2)=="day" else 1)) if hours_match else 24
    actions=[]
    report_match=next((kind for kind in ["shipment","vehicle","battery","container","risk","incident"] if kind in q and "report" in q),None)
    if report_match or "generate report" in q or "download report" in q:
        kind=report_match or "risk"
        scoped=f"&vehicle_id={vehicle_id}" if vehicle_id else ""
        items=[s for s in fleet if not vehicle_id or s["vehicle"]["vehicle_id"]==vehicle_id]
        actions=[{"type":"DOWNLOAD_PDF","label":f"Download {kind.title()} Report","url":f"/reports/{kind}/pdf?hours={hours}{scoped}"},{"type":"OPEN_PAGE","label":"Open Reports","url":"/reports"}]
        text=f"I prepared a {kind} report for {vehicle_id or 'the entire fleet'} covering the last {hours} hours. Use the PDF action below to generate it directly from persisted telemetry and incidents."
        intent="report_action"
    elif any(term in q for term in ["trend","history","historical","average","maximum","minimum"]):
        kind="battery" if any(term in q for term in ["soc","battery","charge"]) else "container" if any(term in q for term in ["temperature","humidity","cold"]) else "risk"
        summary=report(db,kind,vehicle_id,hours)
        items=summary["fleet"]
        metrics="; ".join(f"{key.replace('_',' ')}: avg {value['average']}, min {value['minimum']}, max {value['maximum']}" for key,value in summary["statistics"].items())
        text=f"Historical {kind} analytics for {vehicle_id or 'the fleet'} over the last {hours} hours ({summary['sample_count']} persisted samples): {metrics or 'no samples in this interval'}."
        actions=[{"type":"DOWNLOAD_PDF","label":f"Download {kind.title()} Report","url":f"/reports/{kind}/pdf?hours={hours}"+(f"&vehicle_id={vehicle_id}" if vehicle_id else "")}]
        intent="historical_analytics"
    elif vehicle_match:
        items=[s for s in fleet if s["vehicle"]["vehicle_id"]==vehicle_id]
        if not items:
            return {"answer":f"No vehicle {vehicle_id} is present in this fleet.","intent":"vehicle_risk","references":[],"timestamp":data["timestamp"]}
        s=items[0]
        text=f"{vehicle_id} has a {s['risk']['risk_level']} risk score of {s['risk']['risk_score']}/100. {s['risk']['reason']}. Recommended action: {s['risk']['recommended_action']}"
        intent="vehicle_risk"
    elif "lowest" in q or "charge" in q or "soc" in q:
        items=[min(fleet,key=lambda s:s["battery"]["soc"])]
        s=items[0]
        text=f"{s['vehicle']['vehicle_id']} has the lowest SOC at {s['battery']['soc']:.1f}%, with {s['battery']['estimated_range']:.1f} km estimated range and {s['delivery']['distance_remaining']:.1f} km remaining."
        intent="lowest_soc"
    elif "temperature" in q or "incident" in q:
        alerts=[a for a in data["alerts"] if "TEMPERATURE" in a["type"] or "OVERHEAT" in a["type"]]
        items=[s for s in fleet if any(a["vehicle_id"]==s["vehicle"]["vehicle_id"] for a in alerts)]
        text="; ".join(f"{a['vehicle_id']}: {a['reason']} ({'active' if a['active'] else 'recovered'})" for a in alerts[:8]) or "No temperature incidents are recorded in the current incident window."
        intent="temperature_incidents"
    elif "delay" in q:
        items=[s for s in fleet if s["delivery"]["delivery_status"]=="DELAYED"]
        text="; ".join(f"{s['delivery']['delivery_id']} / {s['vehicle']['vehicle_id']}: {s['delivery']['delay_minutes']:.1f} min delayed, destination {s['delivery']['destination']}" for s in items) or "There are no delayed deliveries."
        intent="delayed_deliveries"
    elif "bms" in q or "fault" in q:
        items=[s for s in fleet if s["battery"]["bms_fault"]!="NONE"]
        text="; ".join(f"{s['vehicle']['vehicle_id']}: {s['battery']['bms_fault']}. {s['risk']['recommended_action']}" for s in items) or "No current BMS faults are detected."
        intent="bms_faults"
    elif "risk" in q or "critical" in q:
        items=[max(fleet,key=lambda s:s["risk"]["risk_score"])]
        s=items[0]
        text=f"{s['container']['shipment_id']} on {s['vehicle']['vehicle_id']} is the highest-risk shipment: {s['risk']['risk_score']}/100 ({s['risk']['risk_level']}). {s['risk']['reason']}. {s['risk']['recommended_action']}"
        intent="highest_risk"
    else:
        items=[]
        text="I can query current fleet risk, explain a vehicle (for example ‘Why is Vehicle V03 critical?’), find the lowest SOC, temperature incidents, delayed deliveries, or BMS faults. Please ask one of those questions."
        intent="help"
    return {"answer":text,"intent":intent,"references":[s["vehicle"]["vehicle_id"] for s in items],"actions":actions,"timestamp":data["timestamp"],"source":"Current SQL telemetry and incident records"}
