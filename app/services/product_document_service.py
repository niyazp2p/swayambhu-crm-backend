import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class ProductDocumentService:
    @staticmethod
    def generate_product_spec_pdf(product) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#063D2A"),
            spaceAfter=8,
        )
        body_style = styles["Normal"]

        # Header
        elements.append(Paragraph(f"<b>SWAYAMBHU PRODUCT SPEC SHEET: {product.name}</b>", title_style))
        elements.append(Paragraph(f"SKU: {product.sku} | Generated Date: Standard Release", body_style))
        elements.append(Spacer(1, 16))

        # Basic Info Table
        meta_data = [
            ["Product SKU:", product.sku, "Available Stock:", f"{product.total_quantity} {product.unit_measure}"],
            ["Dimensions:", product.dimensions or "N/A", "Unit Weight (KG):", f"{product.total_weight_kg:.3f} kg"],
        ]
        meta_table = Table(meta_data, colWidths=[110, 160, 110, 160])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF8EE")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#063D2A")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 20))

        # Material Compositions Table
        elements.append(Paragraph("<b>Material Composition & Upcycled Weight Breakdown:</b>", styles["Heading3"]))
        elements.append(Spacer(1, 8))

        mat_headers = ["Category", "Sub-Category", "Unit Mass", "Unit", "Composition %"]
        mat_rows = [mat_headers]

        for item in product.materials_used:
            sub = item.sub_category
            cat_name = sub.category.name if sub and sub.category else "Standard Scrap"
            sub_name = sub.name if sub else "Scrap Item"
            share = f"{item.percentage_share:.1f}%" if item.percentage_share else "-"
            mat_rows.append([cat_name, sub_name, f"{item.weight:.3f}", item.unit.value, share])

        mat_table = Table(mat_rows, colWidths=[120, 130, 100, 90, 100])
        mat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#006B3C")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF8F5")]),
        ]))
        elements.append(mat_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer