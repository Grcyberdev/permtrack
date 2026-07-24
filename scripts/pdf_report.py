import os
import sys
from datetime import datetime
from fpdf import FPDF

class CustomPDF(FPDF):
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        # Page number
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

def generate_report_pdf(data_json):
    """
    Generates a beautifully structured PDF summary report for permits and dispatches.
    `data_json` is a list of permit/dispatch dictionaries.
    """
    pdf = CustomPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. Header Section
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42) # Slate-900
    pdf.cell(0, 8, "DAILY PERMIT & DISPATCH REPORT", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(71, 85, 105) # Slate-600
    pdf.cell(0, 6, "BORGOHAIN ENTERPRISES PRIVATE LIMITED", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Extract date
    date_str = datetime.now().strftime("%d-%b-%Y")
    for item in data_json:
        if item.get("Date"):
            date_str = item.get("Date")
            break
            
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, f"Date of Report: {date_str} | Generated: {datetime.now().strftime('%H:%M:%S')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    
    # Separate data
    pending = []
    completed = []
    for item in data_json:
        status = item.get("Status", "").upper()
        if status == "PENDING":
            app_date = item.get("Application Date")
            if not app_date or app_date == date_str:
                pending.append(item)
        elif status == "COMPLETED":
            prod_name = (item.get("Product Name") or "").upper()
            if not ("SUB TOTAL" in prod_name or "GRAND TOTAL" in prod_name or "SUBTOTAL" in prod_name or "GRANDTOTAL" in prod_name):
                completed.append(item)
            
    # Calculate metrics & summaries
    unique_pending_passes = set()
    total_pending_cases = 0
    total_pending_bottles = 0
    for p in pending:
        p_num = p.get("Permit Number") or p.get("Indent Number") or "N/A"
        unique_pending_passes.add(p_num)
        total_pending_cases += p.get("Cases", 0)
        total_pending_bottles += p.get("Bottles", 0)
        
    unique_completed_passes = set()
    total_completed_cases = 0
    total_completed_bottles = 0
    party_summary = {} # retailer -> {cases, bottles, mrp, passes}
    grand_mrp = 0.0
    
    for item in completed:
        pass_num = item.get("Transit Pass", "N/A")
        retailer = item.get("Retailer Name", "Unknown")
        cases = item.get("Cases", 0)
        bottles = item.get("Bottles", 0)
        mrp = item.get("Total MRP", 0.0)
        
        if pass_num:
            unique_completed_passes.add(pass_num)
        total_completed_cases += cases
        total_completed_bottles += bottles
        grand_mrp += mrp
        
        if retailer not in party_summary:
            party_summary[retailer] = {
                "cases": 0,
                "bottles": 0,
                "mrp": 0.0,
                "passes": set()
            }
        party_summary[retailer]["cases"] += cases
        party_summary[retailer]["bottles"] += bottles
        party_summary[retailer]["mrp"] += mrp
        if pass_num:
            party_summary[retailer]["passes"].add(pass_num)
            
    # 2. Section: Summary Metrics
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "SUMMARY METRICS", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)
    
    metrics_headers = ["Pending Permits", "Dispatched Permits", "Cases Loaded", "Bottles Loaded", "Pending Cases"]
    metrics_values = [
        str(len(unique_pending_passes)),
        str(len(unique_completed_passes)),
        str(total_completed_cases),
        str(total_completed_bottles),
        str(total_pending_cases)
    ]
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(15, 23, 42)
    with pdf.table(
        borders_layout="ALL", line_height=6, width=190, col_widths=(38, 38, 38, 38, 38),
        text_align=("CENTER", "CENTER", "CENTER", "CENTER", "CENTER")
    ) as table:
        row = table.row()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(71, 85, 105)
        for h in metrics_headers:
            row.cell(h)
        row = table.row()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 23, 42)
        for v in metrics_values:
            row.cell(v)
    pdf.ln(6)
    
    # 3. Section: Party-wise Loading Summary
    if party_summary:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, "PARTY-WISE LOADING SUMMARY", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
        
        party_headers = ["Retailer / Party Name", "Permits", "Total Cases", "Total Bottles", "Total Value (Rs)"]
        sorted_parties = sorted(party_summary.items(), key=lambda x: x[1]["cases"], reverse=True)
        
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)
        with pdf.table(
            borders_layout="ALL", line_height=5.5, width=190, col_widths=(90, 20, 25, 25, 30),
            text_align=("LEFT", "CENTER", "CENTER", "CENTER", "RIGHT")
        ) as table:
            row = table.row()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(71, 85, 105)
            for ph in party_headers:
                row.cell(ph)
                
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(15, 23, 42)
            for party_name, stats in sorted_parties:
                row = table.row()
                row.cell(party_name)
                row.cell(str(len(stats["passes"])))
                row.cell(str(stats["cases"]))
                row.cell(str(stats["bottles"]))
                row.cell(f"{stats['mrp']:,.2f}")
                
            row = table.row()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(15, 23, 42)
            row.cell("TOTAL LOADING SUMMARY")
            row.cell(str(len(unique_completed_passes)))
            row.cell(str(total_completed_cases))
            row.cell(str(total_completed_bottles))
            row.cell(f"{grand_mrp:,.2f}")
            
        pdf.ln(8)
        
    # Section: Brand-wise Daily Loading Summary
    brand_summary = {}
    for item in completed:
        prod = item.get("Product Name")
        if not prod:
            continue
        size = item.get("Size", "")
        key = f"{prod}|{size}"
        
        if key not in brand_summary:
            brand_summary[key] = {
                "name": prod,
                "size": size,
                "cases": 0,
                "bottles": 0,
                "mrp": 0.0
            }
        brand_summary[key]["cases"] += item.get("Cases", 0)
        brand_summary[key]["bottles"] += item.get("Bottles", 0)
        brand_summary[key]["mrp"] += item.get("Total MRP", 0.0)
        
    if brand_summary:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, "BRAND-WISE LOADING SUMMARY", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
        
        brand_headers = ["Product / Brand Name", "Size", "Total Cases", "Total Bottles", "Total Value (Rs)"]
        sorted_brands = sorted(brand_summary.values(), key=lambda x: x["cases"], reverse=True)
        
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)
        with pdf.table(
            borders_layout="ALL", line_height=5.5, width=190, col_widths=(95, 20, 20, 20, 35),
            text_align=("LEFT", "CENTER", "CENTER", "CENTER", "RIGHT")
        ) as table:
            row = table.row()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(71, 85, 105)
            for bh in brand_headers:
                row.cell(bh)
                
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(15, 23, 42)
            total_cases = 0
            total_bottles = 0
            grand_mrp_brands = 0.0
            
            for b in sorted_brands:
                row = table.row()
                row.cell(b["name"].replace("`", "'"))
                row.cell(b["size"])
                row.cell(str(b["cases"]))
                row.cell(str(b["bottles"]))
                row.cell(f"{b['mrp']:,.2f}")
                
                total_cases += b["cases"]
                total_bottles += b["bottles"]
                grand_mrp_brands += b["mrp"]
                
            row = table.row()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(15, 23, 42)
            row.cell("TOTAL LOADING")
            row.cell("")
            row.cell(str(total_cases))
            row.cell(str(total_bottles))
            row.cell(f"{grand_mrp_brands:,.2f}")
            
        pdf.ln(8)
        
    # 4. Section: Applied Permits (Pending Approval)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(220, 38, 38) # Red-600
    pdf.cell(0, 8, "APPLIED PERMITS (PENDING APPROVAL)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)
    
    if not pending:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, "No pending permits recorded.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
    else:
        # Deduplicate pending listing and aggregate cases/bottles
        unique_pending = {}
        for p in pending:
            p_num = p.get("Permit Number", "N/A")
            if p_num not in unique_pending:
                unique_pending[p_num] = {
                    "retailer": p.get("Retailer Name", "Unknown"),
                    "indent": p.get("Indent Number", "N/A"),
                    "permit": p_num,
                    "type": p.get("Bond Type", "IMFL"),
                    "cases": 0,
                    "bottles": 0
                }
            unique_pending[p_num]["cases"] += p.get("Cases", 0)
            unique_pending[p_num]["bottles"] += p.get("Bottles", 0)
            
        pending_headers = ["S.No", "Retailer Name", "Indent Number", "Permit Number", "Bond Type", "Cases", "Bottles"]
        pending_rows = []
        for idx, p in enumerate(unique_pending.values()):
            pending_rows.append([
                str(idx+1),
                p["retailer"],
                p["indent"],
                p["permit"],
                p["type"],
                str(p["cases"]),
                str(p["bottles"])
            ])
            
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)
        with pdf.table(
            borders_layout="ALL", line_height=6, width=190, col_widths=(10, 70, 35, 35, 16, 12, 12),
            text_align=("CENTER", "LEFT", "CENTER", "CENTER", "CENTER", "CENTER", "CENTER")
        ) as table:
            row = table.row()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(71, 85, 105)
            for h in pending_headers:
                row.cell(h)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(15, 23, 42)
            for r in pending_rows:
                row = table.row()
                for cell in r:
                    row.cell(cell)
        pdf.ln(8)
        
    # 5. Section: Dispatched Passes (Completed)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(5, 150, 105) # Green-600
    pdf.cell(0, 8, "DISPATCHED PERMITS (PASSES ISSUED TODAY)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)
    
    if not completed:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, "No dispatched passes recorded for today.", new_x="LMARGIN", new_y="NEXT")
    else:
        # Group dispatches by Transit Pass
        grouped = {}
        for item in completed:
            pass_key = item.get("Transit Pass", "N/A")
            if pass_key not in grouped:
                grouped[pass_key] = {
                    "retailer": item.get("Retailer Name", "Unknown"),
                    "vehicle": item.get("Vehicle Number", "No Vehicle"),
                    "permit": item.get("Permit Number", "N/A"),
                    "type": item.get("Bond Type", "IMFL"),
                    "brands": []
                }
            grouped[pass_key]["brands"].append({
                "name": item.get("Product Name", "Unknown"),
                "size": item.get("Size", ""),
                "cases": item.get("Cases", 0),
                "bottles": item.get("Bottles", 0),
                "mrp": item.get("Total MRP", 0.0)
            })
            
        # Draw each dispatch block
        for idx, (pass_num, details) in enumerate(grouped.items()):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(0, 6, f"{idx+1}. Vehicle: {details['vehicle']} | Retailer: {details['retailer']} ({details['type']})", new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 4.5, f"   Transit Pass: {pass_num} | Permit: {details['permit']}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
            
            # Table of brands loaded
            brand_headers = ["Product / Brand Name", "Size", "Cases", "Bottles", "Total MRP (Rs)"]
            
            with pdf.table(
                borders_layout="ALL", line_height=5.5, width=190, col_widths=(95, 20, 20, 20, 35),
                text_align=("LEFT", "CENTER", "CENTER", "CENTER", "RIGHT")
            ) as table:
                # Header Row
                row = table.row()
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(71, 85, 105)
                for bh in brand_headers:
                    row.cell(bh)
                
                # Data Rows
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(15, 23, 42)
                total_cases = 0
                total_bottles = 0
                grand_mrp_block = 0.0
                
                for b in details["brands"]:
                    row = table.row()
                    row.cell(b["name"].replace("`", "'"))
                    row.cell(b["size"])
                    row.cell(str(b["cases"]))
                    row.cell(str(b["bottles"]))
                    row.cell(f"{b['mrp']:,.2f}")
                    
                    total_cases += b["cases"]
                    total_bottles += b["bottles"]
                    grand_mrp_block += b["mrp"]
                    
                # Total Row
                row = table.row()
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(15, 23, 42)
                row.cell("TOTAL LOADING SUMMARY")
                row.cell("")
                row.cell(str(total_cases))
                row.cell(str(total_bottles))
                row.cell(f"{grand_mrp_block:,.2f}")
                
            pdf.ln(5)
            
    return bytes(pdf.output())
