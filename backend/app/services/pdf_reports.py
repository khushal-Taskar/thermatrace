"""Server-generated operational PDF reports."""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def build_report_pdf(data):
    buffer=BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=22*mm,bottomMargin=18*mm,title=data["title"],author="ThermaTrace")
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand",parent=styles["Heading1"],fontName="Helvetica-Bold",fontSize=19,textColor=colors.HexColor("#187b67"),spaceAfter=4))
    styles.add(ParagraphStyle(name="Title2",parent=styles["Heading2"],fontSize=14,textColor=colors.HexColor("#203a32"),spaceBefore=13,spaceAfter=8))
    styles.add(ParagraphStyle(name="Small2",parent=styles["BodyText"],fontSize=7.5,leading=10,textColor=colors.HexColor("#63756c")))
    styles.add(ParagraphStyle(name="RightSmall",parent=styles["Small2"],alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="Body2",parent=styles["BodyText"],fontSize=8.5,leading=12,textColor=colors.HexColor("#263d35")))
    story=[Paragraph("ThermaTrace",styles["Brand"]),Paragraph("PHARMACEUTICAL LOGISTICS INTELLIGENCE",styles["Small2"]),Spacer(1,5*mm),Paragraph(data["title"],styles["Title"]),Paragraph(f"Scope: {data['vehicle_id']} | Period: last {data['period_hours']} hours | Generated: {data['generated_at']}",styles["Small2"]),Spacer(1,5*mm)]
    summary=[["Telemetry samples","Vehicles","Incidents","Acknowledged"],[str(data["sample_count"]),str(len(data["fleet"])),str(len(data["incidents"])),str(sum(a["acknowledged"] for a in data["incidents"]))]]
    table=Table(summary,colWidths=[42*mm]*4,rowHeights=[7*mm,11*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eaf4ef")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#4f6d61")),("FONTNAME",(0,0),(-1,0),"Helvetica"),("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),7),("FONTSIZE",(0,1),(-1,1),15),("ALIGN",(0,0),(-1,-1),"CENTER"),("BOX",(0,0),(-1,-1),.4,colors.HexColor("#d7e4dc")),("INNERGRID",(0,0),(-1,-1),.25,colors.HexColor("#d7e4dc"))]))
    story.extend([table,Paragraph("Telemetry summary",styles["Title2"])])
    stat_rows=[["Signal","Minimum","Average","Maximum"]]+[[key.replace("_"," ").title(),str(value["minimum"]),str(value["average"]),str(value["maximum"])] for key,value in data["statistics"].items()]
    story.append(_data_table(stat_rows,[63*mm,35*mm,35*mm,35*mm]))
    story.append(Paragraph("Current fleet status",styles["Title2"]))
    for snapshot in data["fleet"]:
        container=snapshot["container"]; risk=snapshot["risk"]; delivery=snapshot["delivery"]; battery=snapshot["battery"]
        remaining=container.get("remaining_safe_time_minutes",720)
        card=[[Paragraph(f"<b>{snapshot['vehicle']['vehicle_id']}</b> | {container['shipment_id']} | {container['medicine_name']}",styles["Body2"]),Paragraph(f"<b>{risk['risk_level']} {risk['risk_score']}/100</b>",styles["RightSmall"])],[Paragraph(f"{delivery['source']} to {delivery['destination']}<br/>SOC {battery['soc']:.1f}% | Container {container['temperature']:.1f} C | Excursion {container.get('excursion_duration_minutes',0):.1f} min | Safe-time buffer {remaining:.1f} min",styles["Small2"]),""],[Paragraph(f"<b>Evidence:</b> {risk['reason']}<br/><b>Action:</b> {risk['recommended_action']}",styles["Small2"]),""]]
        fleet_table=Table(card,colWidths=[135*mm,33*mm])
        fleet_table.setStyle(TableStyle([("SPAN",(0,1),(-1,1)),("SPAN",(0,2),(-1,2)),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f1f6f3")),("BOX",(0,0),(-1,-1),.45,colors.HexColor("#d7e4dc")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(KeepTogether([fleet_table,Spacer(1,2.5*mm)]))
    story.extend([Spacer(1,3*mm),Paragraph("Incident log",styles["Title2"])])
    if data["incidents"]:
        incident_rows=[["Time / vehicle","Severity","Incident and action","Status"]]
        for alert in data["incidents"]:
            incident_rows.append([Paragraph(f"{alert['timestamp'][:16]}<br/>{alert['vehicle_id']}",styles["Small2"]),alert["severity"],Paragraph(f"{alert['reason']}<br/><b>Action:</b> {alert['recommended_action']}",styles["Small2"]),"Acknowledged" if alert["acknowledged"] else "Open"])
        story.append(_data_table(incident_rows,[30*mm,20*mm,91*mm,27*mm]))
    else:
        story.append(Paragraph("No incidents were recorded in the selected period.",styles["Body2"]))
    story.extend([Spacer(1,8*mm),Paragraph(data["data_source"],styles["Small2"]),Paragraph("Operational decision support only. Medicine profiles and model outputs require validation before regulated use.",styles["Small2"])])

    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor("#d7e4dc"));canvas.line(16*mm,14*mm,194*mm,14*mm);canvas.setFont("Helvetica",7);canvas.setFillColor(colors.HexColor("#73847c"));canvas.drawString(16*mm,9*mm,"ThermaTrace - controlled simulation report");canvas.drawRightString(194*mm,9*mm,f"Page {doc.page}");canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()


def _data_table(rows,widths):
    styles=getSampleStyleSheet()
    body=ParagraphStyle("TableBody",parent=styles["BodyText"],fontSize=7.2,leading=9,textColor=colors.HexColor("#263d35"))
    header=ParagraphStyle("TableHeader",parent=body,fontName="Helvetica-Bold",textColor=colors.white)
    normalized=[[Paragraph(str(cell),header if row_index==0 else body) if not hasattr(cell,"wrap") else cell for cell in row] for row_index,row in enumerate(rows)]
    table=Table(normalized,colWidths=widths,repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#203a32")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d8e2dc")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f7f9f8")]),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    return table
