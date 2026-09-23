import io
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.models.sales import DispatchOrder
from app.models.procurement import WasteGrade
from app.models.plant import Plant


class DocumentService:
    @staticmethod
    def generate_gate_pass_pdf(dispatch: DispatchOrder, plant: Plant, grade: WasteGrade) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        styles = getSampleStyleSheet()
        elements = []

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1b4332"),
            alignment=1,
        )
        sub_style = ParagraphStyle(
            "SubTitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#555555"),
            alignment=1,
        )

        elements.append(Paragraph(f"<b>{plant.name.upper()}</b>", title_style))
        elements.append(Paragraph("OUTWARD WEIGHBRIDGE GATE PASS & CONSIGNMENT NOTE", sub_style))
        elements.append(Spacer(1, 0.2 * inch))

        header_data = [
            [
                Paragraph(f"<b>Gate Pass No:</b> {dispatch.dispatch_number}", styles["Normal"]),
                Paragraph(f"<b>Date:</b> {dispatch.dispatch_date.strftime('%d-%b-%Y')}", styles["Normal"]),
            ],
            [
                Paragraph(f"<b>Vehicle No:</b> {dispatch.vehicle_number}", styles["Normal"]),
                Paragraph(f"<b>Driver:</b> {dispatch.driver_name or 'N/A'}", styles["Normal"]),
            ],
            [
                Paragraph(f"<b>Buyer:</b> {dispatch.buyer.name}", styles["Normal"]),
                Paragraph(f"<b>Driver Phone:</b> {dispatch.driver_phone or 'N/A'}", styles["Normal"]),
            ],
        ]
        t_header = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
        t_header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_header)
        elements.append(Spacer(1, 0.2 * inch))

        measurements = [
            ["Description", "Details / Measurement"],
            ["Material / Waste Grade", f"{grade.grade_code} ({grade.category_name})"],
            ["Bales Loaded", f"{dispatch.bales_count} units"],
            ["Gross Weight", f"{dispatch.gross_weight_kg:,.2f} kg"],
            ["Tare (Truck) Weight", f"{dispatch.tare_weight_kg:,.2f} kg"],
            ["Net Outward Weight", f"{dispatch.net_weight_kg:,.2f} kg"],
        ]
        t_measure = Table(measurements, colWidths=[3.0 * inch, 4.0 * inch])
        t_measure.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
        ]))
        elements.append(t_measure)
        elements.append(Spacer(1, 0.4 * inch))

        signatures = [
            ["_______________________", "_______________________"],
            ["Weighbridge Operator", "Driver Signature"],
        ]
        t_sig = Table(signatures, colWidths=[3.5 * inch, 3.5 * inch])
        t_sig.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 1), (-1, 1), 9),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#666666")),
        ]))
        elements.append(t_sig)

        doc.build(elements)
        buffer.seek(0)
        return buffer

    @staticmethod
    def generate_invoice_pdf(dispatch: DispatchOrder, plant: Plant, grade: WasteGrade) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        styles = getSampleStyleSheet()
        elements = []

        taxable_value = dispatch.total_amount
        cgst_rate = Decimal("0.025")
        sgst_rate = Decimal("0.025")
        cgst_amt = round(taxable_value * cgst_rate, 2)
        sgst_amt = round(taxable_value * sgst_rate, 2)
        grand_total = taxable_value + cgst_amt + sgst_amt

        elements.append(Paragraph(f"<b>{plant.name.upper()}</b>", styles["Heading1"]))
        elements.append(Paragraph("TAX INVOICE", styles["Heading3"]))
        elements.append(Spacer(1, 0.15 * inch))

        info_data = [
            [
                Paragraph(f"<b>Invoice Ref:</b> INV-{dispatch.dispatch_number}", styles["Normal"]),
                Paragraph(f"<b>Billed To:</b> {dispatch.buyer.name}", styles["Normal"]),
            ],
            [
                Paragraph(f"<b>Date:</b> {dispatch.dispatch_date.strftime('%d-%b-%Y')}", styles["Normal"]),
                Paragraph(f"<b>GSTIN:</b> {dispatch.buyer.gstin or 'URP'}", styles["Normal"]),
            ],
            [
                Paragraph(f"<b>Dispatch Ref:</b> {dispatch.dispatch_number}", styles["Normal"]),
                Paragraph(f"<b>Address:</b> {dispatch.buyer.billing_address}", styles["Normal"]),
            ],
        ]
        t_info = Table(info_data, colWidths=[3.5 * inch, 3.5 * inch])
        elements.append(t_info)
        elements.append(Spacer(1, 0.2 * inch))

        items_data = [
            ["Item / Grade", "Net Qty (kg)", "Rate (₹/kg)", "Taxable Value (₹)"],
            [
                f"{grade.grade_code}\n({grade.category_name})",
                f"{dispatch.net_weight_kg:,.2f}",
                f"{dispatch.rate_per_kg:,.2f}",
                f"{taxable_value:,.2f}",
            ],
            ["", "", "CGST (2.5%):", f"{cgst_amt:,.2f}"],
            ["", "", "SGST (2.5%):", f"{sgst_amt:,.2f}"],
            ["", "", "Grand Total:", f"{grand_total:,.2f}"],
        ]
        t_items = Table(items_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
        t_items.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4332")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, 1), 0.5, colors.grey),
            ("LINEBELOW", (2, -1), (3, -1), 1, colors.black),
            ("FONTNAME", (2, -1), (3, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(t_items)

        doc.build(elements)
        buffer.seek(0)
        return buffer