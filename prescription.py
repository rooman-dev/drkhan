"""
DrKhan Hospital Management System
Prescription PDF Generator
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
from datetime import datetime
from fpdf import FPDF

from database import get_connection


def get_output_dir():
    """Get persistent output directory for PDFs."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if sys.platform == 'win32':
            app_data = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
            output_dir = app_data / 'DrKhan' / 'prescriptions'
        else:
            output_dir = Path.home() / '.drkhan' / 'prescriptions'
    else:
        output_dir = Path(__file__).parent / 'prescriptions'
    
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


class PrescriptionPDF(FPDF):
    """Custom PDF class for prescriptions."""
    
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
    
    def header(self):
        """Prescription header with clinic info."""
        # Navy blue color
        self.set_text_color(0, 31, 63)
        
        # Clinic name
        self.set_font('Helvetica', 'B', 24)
        self.cell(0, 12, 'DR.Khan Clinic', new_x='LMARGIN', new_y='NEXT', align='C')
        
        # Subtitle
        self.set_font('Helvetica', '', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, 'General Physician | Contact: +92 304 7501095', new_x='LMARGIN', new_y='NEXT', align='C')
        
        # Divider line
        self.set_draw_color(0, 31, 63)
        self.set_line_width(0.5)
        self.line(10, 32, 200, 32)
        self.ln(8)
    
    def footer(self):
        """Prescription footer."""
        self.set_y(-35)
        
        # Get well soon message
        self.set_font('Helvetica', 'I', 11)
        self.set_text_color(0, 31, 63)
        self.cell(0, 6, 'Get well soon!', new_x='LMARGIN', new_y='NEXT', align='C')
        
        # Signature line
        self.ln(3)
        self.set_draw_color(0, 31, 63)
        self.line(140, self.get_y(), 195, self.get_y())
        self.ln(2)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, "Doctor's Signature", align='R')


def generate_prescription_pdf(visit_id: int) -> str:
    """
    Generate a prescription PDF for a visit.
    
    Args:
        visit_id: The ID of the visit
        
    Returns:
        Path to the generated PDF file
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get visit details with patient info (using correct column names)
    cursor.execute("""
        SELECT 
            v.id, v.date, 
            v.vitals_bp, v.vitals_weight, v.vitals_temp, v.vitals_bsr, v.vitals_spo2, v.vitals_heart_rate,
            v.presenting_complaint, v.signs_symptoms, v.differentials, v.treatment_plan,
            p.id as patient_id, p.name as patient_name, p.age, p.gender, p.contact
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
    """, (visit_id,))
    
    visit = cursor.fetchone()
    
    if not visit:
        conn.close()
        raise ValueError(f"Visit {visit_id} not found")
    
    visit = dict(visit)
    
    # Get prescriptions for this visit
    cursor.execute("""
        SELECT medicine_name, dosage, duration, quantity, price
        FROM prescriptions
        WHERE visit_id = ?
        ORDER BY id
    """, (visit_id,))
    medicines = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Create PDF
    pdf = PrescriptionPDF()
    pdf.add_page()
    
    # Patient Information Box
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(0, 31, 63)
    pdf.rect(10, pdf.get_y(), 190, 25, 'DF')
    
    y_start = pdf.get_y() + 4
    pdf.set_y(y_start)
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(0, 31, 63)
    
    # Left column
    pdf.set_x(15)
    patient_name = visit.get('patient_name', 'N/A') or 'N/A'
    pdf.cell(90, 5, f"Patient: {patient_name}", new_x='LMARGIN', new_y='NEXT')
    pdf.set_x(15)
    age = visit.get('age', 'N/A') or 'N/A'
    gender = visit.get('gender', '') or ''
    pdf.cell(90, 5, f"Age: {age} years  |  Gender: {gender}", new_x='LMARGIN', new_y='NEXT')
    
    # Right column
    pdf.set_y(y_start)
    pdf.set_x(120)
    visit_date = visit.get('date', 'N/A') or 'N/A'
    pdf.cell(80, 5, f"Date: {visit_date}", new_x='LMARGIN', new_y='NEXT')
    pdf.set_x(120)
    pdf.cell(80, 5, f"Visit ID: #{visit.get('id', 'N/A')}", new_x='LMARGIN', new_y='NEXT')
    
    pdf.set_y(y_start + 22)
    pdf.ln(5)
    
    # Vitals Section
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(0, 31, 63)
    pdf.cell(0, 8, 'Vitals', new_x='LMARGIN', new_y='NEXT')
    
    pdf.set_fill_color(240, 248, 255)
    vitals_y = pdf.get_y()
    pdf.rect(10, vitals_y, 190, 12, 'DF')
    
    pdf.set_y(vitals_y + 3)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(50, 50, 50)
    
    bp = visit.get('vitals_bp') or '-'
    weight = f"{visit.get('vitals_weight')}kg" if visit.get('vitals_weight') else '-'
    temp = f"{visit.get('vitals_temp')}F" if visit.get('vitals_temp') else '-'
    bsr = visit.get('vitals_bsr') or '-'
    spo2 = visit.get('vitals_spo2') or '-'
    hr = visit.get('vitals_heart_rate') or '-'
    
    pdf.set_x(12)
    pdf.cell(32, 6, f"BP: {bp}", align='L')
    pdf.cell(32, 6, f"Wt: {weight}", align='L')
    pdf.cell(32, 6, f"Temp: {temp}", align='L')
    pdf.cell(32, 6, f"BSR: {bsr}", align='L')
    pdf.cell(32, 6, f"SPO2: {spo2}", align='L')
    pdf.cell(28, 6, f"HR: {hr}", align='L')
    pdf.ln(15)
    
    # Presenting Complaint
    complaint = visit.get('presenting_complaint')
    if complaint:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 31, 63)
        pdf.cell(0, 7, 'Presenting Complaint', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 5, str(complaint))
        pdf.ln(3)
    
    # Differential Diagnosis
    differentials = visit.get('differentials')
    if differentials:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 31, 63)
        pdf.cell(0, 7, 'Diagnosis', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 5, str(differentials))
        pdf.ln(3)
    
    # Treatment Plan
    treatment = visit.get('treatment_plan')
    if treatment:
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 31, 63)
        pdf.cell(0, 7, 'Treatment Plan', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 5, str(treatment))
        pdf.ln(3)
    
    # Prescription (Rx)
    pdf.ln(3)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(0, 31, 63)
    pdf.cell(0, 8, 'Rx', new_x='LMARGIN', new_y='NEXT')
    
    # Medicine table header
    pdf.set_fill_color(0, 31, 63)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 10)
    
    pdf.cell(10, 8, '#', border=1, align='C', fill=True)
    pdf.cell(70, 8, 'Medicine', border=1, align='C', fill=True)
    pdf.cell(15, 8, 'Qty', border=1, align='C', fill=True)
    pdf.cell(50, 8, 'Dosage', border=1, align='C', fill=True)
    pdf.cell(45, 8, 'Duration', border=1, align='C', fill=True)
    pdf.ln()
    
    # Medicine table rows
    pdf.set_text_color(50, 50, 50)
    pdf.set_font('Helvetica', '', 9)
    
    row_height = 7
    
    if medicines:
        for i, med in enumerate(medicines, 1):
            # Check if we need a new page (leave space for footer)
            if pdf.get_y() > 240:
                pdf.add_page()
                # Re-draw table header on new page
                pdf.set_fill_color(0, 31, 63)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font('Helvetica', 'B', 10)
                pdf.cell(10, 8, '#', border=1, align='C', fill=True)
                pdf.cell(70, 8, 'Medicine', border=1, align='C', fill=True)
                pdf.cell(15, 8, 'Qty', border=1, align='C', fill=True)
                pdf.cell(50, 8, 'Dosage', border=1, align='C', fill=True)
                pdf.cell(45, 8, 'Duration', border=1, align='C', fill=True)
                pdf.ln()
                pdf.set_text_color(50, 50, 50)
                pdf.set_font('Helvetica', '', 9)
            
            if i % 2 == 0:
                pdf.set_fill_color(255, 255, 255)
            else:
                pdf.set_fill_color(248, 249, 250)
            
            med_name = str(med.get('medicine_name', ''))[:35]
            qty = str(med.get('quantity', ''))
            dosage = str(med.get('dosage', 'As directed'))[:25]
            duration = str(med.get('duration', ''))[:20]
            
            pdf.cell(10, row_height, str(i), border=1, align='C', fill=True)
            pdf.cell(70, row_height, med_name, border=1, align='L', fill=True)
            pdf.cell(15, row_height, qty, border=1, align='C', fill=True)
            pdf.cell(50, row_height, dosage, border=1, align='C', fill=True)
            pdf.cell(45, row_height, duration, border=1, align='C', fill=True)
            pdf.ln()
    else:
        pdf.cell(190, 8, 'No medicines prescribed', border=1, align='C')
        pdf.ln()
    
    # Generate output path
    output_dir = get_output_dir()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"prescription_{visit_id}_{timestamp}.pdf"
    
    # Save PDF
    pdf.output(str(output_file))
    
    return str(output_file)


def open_pdf(file_path: str):
    """Open PDF in the default system viewer."""
    try:
        if platform.system() == 'Windows':
            os.startfile(file_path)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', file_path], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', file_path], check=True)
    except Exception as e:
        print(f"Could not open PDF: {e}")


def generate_and_open_prescription(visit_id: int) -> str:
    """Generate prescription PDF and open it in system viewer."""
    file_path = generate_prescription_pdf(visit_id)
    open_pdf(file_path)
    return file_path


if __name__ == "__main__":
    # Test with visit ID 1
    import sys
    visit_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    path = generate_and_open_prescription(visit_id)
    print(f"Prescription generated: {path}")
