"""
DrKhan Hospital Management System
Prescription PDF Generator
"""

import os
import sys
import subprocess
import platform
import re
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


def _slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "prescription"


def _find_symbol_font() -> Path | None:
    windows_root = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windows_root / "Fonts" / "seguisym.ttf",
        windows_root / "Fonts" / "seguiemj.ttf",
        windows_root / "Fonts" / "segoeui.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class PrescriptionSheetPDF(FPDF):
    """PDF layout for the prescription capture form."""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(12, 12, 12)
        self.symbol_font_name: str | None = None

    def set_symbol_font(self, font_name: str) -> None:
        self.symbol_font_name = font_name

    def _fit_text(self, text: str, width: float) -> str:
        text = str(text)
        if self.get_string_width(text) <= width:
            return text
        ellipsis = "..."
        while text and self.get_string_width(text + ellipsis) > width:
            text = text[:-1]
        return text + ellipsis if text else ellipsis

    def header(self):
        margin_x = 12
        top_y = 18
        left_x = margin_x
        left_width = 96
        right_x = 112
        right_width = 82

        # Center clinic logo at top if available.
        try:
            logo_path = Path(__file__).parent / "logopdf.png"
            if logo_path.exists():
                logo_w = 18
                logo_x = (self.w - logo_w) / 2
                self.image(str(logo_path), x=logo_x, y=8, w=logo_w)
                top_y = 28
        except Exception:
            pass

        self.set_y(top_y)

        self.set_xy(left_x, top_y)
        self.set_font("Helvetica", "B", 18)
        self.cell(left_width, 8, "DR. SHEHRAM KHAN", border=0)
        self.ln(7)

        self.set_x(left_x)
        self.set_font("Helvetica", "", 10)
        self.cell(left_width, 5, "MBBS, RMP", border=0)
        self.ln(5)

        self.set_x(left_x)
        self.cell(left_width, 5, "Family Physician", border=0)
        self.ln(5)

        self.set_x(left_x)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(left_width, 4, "EX House Physician & Surgeon Aziz Bhatti Shaheed", border=0)

        self.set_xy(right_x, top_y)
        self.set_font("Helvetica", "B", 18)
        self.cell(right_width, 8, "DR KHAN CLINIC", border=0, align="R")
        self.ln(7)

        self.set_x(right_x)
        self.set_font("Helvetica", "", 10)
        self.cell(right_width, 5, "QUALITY HEALTHCARE FOR EVERY AGE", border=0, align="R")
        self.ln(5)

        self.set_x(right_x)
        self.cell(right_width, 5, "Ph: 0304 7501095", border=0, align="R")
        self.ln(5)

        self.set_x(right_x)
        self.cell(right_width, 5, "khanshehram000@gmail.com", border=0, align="R")
        self.ln(4)

        self.set_y(max(self.get_y(), top_y + 23) + 2)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "", 9)
        footer_text = "Chak R.S Main Shujabad Road. Shujabad Pir Mubeen Town       NOT VALID IN COURT"
        self.cell(0, 5, footer_text, align="C")

    def inline_row(self, pairs, widths, font_size=10):
        self.set_font("Helvetica", "", font_size)
        for index, ((label, value), width) in enumerate(zip(pairs, widths)):
            text = f"{label}: {value if value not in [None, ''] else '__'}"
            text = self._fit_text(text, width - 2)
            self.cell(width, 8, text, border=0)
        self.ln(8)

    def divider(self):
        self.ln(2)

    def underline_field(self, label: str, value: str, width: float):
        text = str(value).strip() if value not in [None, ""] else ""
        label_width = self.get_string_width(f"{label}:") + 1
        max_text_width = max(12, width - label_width - 2)
        display = self._fit_text(text if text else "", max_text_width)

        self.set_font("Helvetica", "", 10)
        self.cell(label_width, 7, f"{label}:", border=0)
        start_x = self.get_x()
        baseline_y = self.get_y() + 6
        self.cell(width - label_width, 7, display, border=0)
        line_y = baseline_y
        self.line(start_x, line_y, start_x + width - label_width, line_y)

    def underlined_row(self, pairs, widths):
        row_top = self.get_y()
        max_height = 0
        start_x = self.l_margin
        for (label, value), width in zip(pairs, widths):
            self.set_xy(start_x, row_top)
            self.underline_field(label, value, width)
            start_x += width
            max_height = max(max_height, 7)
        self.set_y(row_top + max_height + 2)

    def labeled_box(self, title: str, content: str, height: float):
        left = self.l_margin
        width = self.w - self.l_margin - self.r_margin

        self.set_font("Helvetica", "B", 12)
        self.cell(0, 6, title, border=0, ln=1)

        box_y = self.get_y()
        self.rect(left, box_y, width, height)
        self.set_xy(left + 2, box_y + 2)

        self.set_font("Helvetica", "", 10)
        text = content.strip() if content else ""
        if text:
            self.multi_cell(width - 4, 5, text)

        self.set_y(box_y + height + 4)

    def handwriting_box(self, title: str, height: float = 24, lines: int = 3):
        """Draw a large empty box with light guide lines for hand-written notes."""
        left = self.l_margin
        width = self.w - self.l_margin - self.r_margin

        self.set_font("Helvetica", "B", 12)
        self.cell(0, 6, title, border=0, ln=1)

        box_y = self.get_y()
        self.rect(left, box_y, width, height)

        if lines > 1:
            self.set_draw_color(210, 210, 210)
            line_gap = height / (lines + 1)
            for i in range(1, lines + 1):
                y = box_y + (line_gap * i)
                self.line(left + 2, y, left + width - 2, y)

        self.set_y(box_y + height + 4)

    def full_page_handwriting_section(self, title: str, subtitle: str = "", lines: int = 20):
        """Start a new page with a very large writing area for handwritten notes."""
        self.add_page()

        self.set_font("Helvetica", "B", 16)
        self.set_text_color(0, 31, 63)
        self.cell(0, 10, title, border=0, ln=1)

        if subtitle:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(90, 90, 90)
            self.cell(0, 6, subtitle, border=0, ln=1)

        top = self.get_y() + 4
        left = self.l_margin
        width = self.w - self.l_margin - self.r_margin
        height = self.h - top - self.b_margin - 10

        self.set_draw_color(180, 180, 180)
        self.rect(left, top, width, height)

        if lines > 0:
            self.set_draw_color(220, 220, 220)
            line_gap = height / (lines + 1)
            for i in range(1, lines + 1):
                y = top + (line_gap * i)
                self.line(left + 3, y, left + width - 3, y)

        self.set_y(top + height + 4)

    def render_prescription_sheet(self, payload: dict) -> None:
        self.add_page()

        pt_name = payload.get("pt_name", "")
        age = payload.get("age", "")
        contact = payload.get("contact", "")
        visit_date = payload.get("date", "")

        bp = payload.get("bp", "")
        hr = payload.get("hr", "")
        so2 = payload.get("so2", "")
        rr = payload.get("rr", "")
        temp = payload.get("temp", "")

        ht_wt = payload.get("ht_wt", "")
        bmi = payload.get("bmi", "")
        rbs = payload.get("rbs", "")
        fbs = payload.get("fbs", "")

        comorbs = payload.get("comorbs", "")
        pc_dx = payload.get("pc_dx", "")
        rx = payload.get("rx", "")
        advice = payload.get("advice", "")
        include_clinical_sections = bool(payload.get("include_clinical_sections", False))

        self.underlined_row(
            [
                ("Pt. Name", pt_name),
                ("Age", age),
                ("Contact", contact),
                ("Date", visit_date),
            ],
            [66, 38, 42, 40],
        )

        self.underlined_row(
            [
                ("BP", bp),
                ("HR", hr),
                ("So2", so2),
                ("RR", rr),
                ("Temp", temp),
            ],
            [37, 37, 37, 37, 38],
        )

        self.underlined_row(
            [
                ("Ht/Wt", ht_wt),
                ("BMI", bmi),
                ("RBS", rbs),
                ("FBS", fbs),
            ],
            [46, 46, 47, 47],
        )

        self.set_font("Helvetica", "B", 11)
        self.underlined_row([("CoMorbs", comorbs)], [180])

        if include_clinical_sections:
            def render_text_section(title: str, text: str):
                if not str(text or "").strip():
                    return
                self.set_font("Helvetica", "B", 11)
                self.cell(0, 6, title, border=0, ln=1)
                self.set_font("Helvetica", "", 10)
                self.multi_cell(0, 5, str(text).strip())
                self.ln(2)

            render_text_section("PC/DX", pc_dx)
            render_text_section("RX", rx)
            render_text_section("Advice", advice)


def generate_form_prescription_pdf(payload: dict) -> str:
    """Generate a formatted prescription PDF from captured patient data."""
    pdf = PrescriptionSheetPDF()

    symbol_font = _find_symbol_font()
    if symbol_font:
        pdf.add_font("DrKhanSymbol", "", str(symbol_font), uni=True)
        pdf.set_symbol_font("DrKhanSymbol")

    pdf.render_prescription_sheet(payload)

    output_dir = get_output_dir()
    safe_name = _slugify(str(payload.get("pt_name", "prescription")))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"prescription_{safe_name}_{timestamp}.pdf"
    pdf.output(str(output_file))
    return str(output_file)


def generate_prescription_form_pdf(payload: dict) -> str:
    """Compatibility alias for the prescription form PDF generator."""
    return generate_form_prescription_pdf(payload)


def generate_patient_history_pdf(patient_id: int) -> str:
    """Generate a patient history PDF with all visits and prescriptions."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()

    if not patient:
        conn.close()
        raise ValueError(f"Patient {patient_id} not found")

    patient = dict(patient)

    cursor.execute("""
        SELECT id, date, vitals_bp, vitals_weight, vitals_temp, vitals_bsr,
            vitals_spo2, vitals_heart_rate, presenting_complaint, signs_symptoms,
            history_presenting_illness, past_medical_hx, family_history,
            examination, differentials, treatment_plan
        FROM visits
        WHERE patient_id = ?
        ORDER BY date DESC
    """, (patient_id,))

    visits = []
    for visit_row in cursor.fetchall():
        visit = dict(visit_row)
        cursor.execute("""
            SELECT medicine_name, dosage, duration, quantity
            FROM prescriptions
            WHERE visit_id = ?
        """, (visit['id'],))
        visit['prescriptions'] = [dict(row) for row in cursor.fetchall()]
        visits.append(visit)

    conn.close()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(0, 31, 63)
    pdf.cell(0, 12, 'DrKhan Clinic', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, 'Patient History - All Visits', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(5)

    pdf.set_fill_color(0, 31, 63)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, ' Patient Information', new_x='LMARGIN', new_y='NEXT', align='L', fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 11)
    pdf.ln(3)

    info_items = [
        f"Patient ID: #{patient['id']}",
        f"Name: {patient['name']}",
        f"Age: {patient.get('age', 'N/A')} years",
        f"Gender: {patient.get('gender', 'N/A')}",
        f"Contact: {patient.get('contact', 'N/A')}",
        f"Occupation: {patient.get('occupation', 'N/A')}",
        f"Marital Status: {patient.get('marital_status', 'N/A')}",
        f"Address: {patient.get('address', 'N/A')}"
    ]

    for item in info_items:
        pdf.cell(0, 7, item, new_x='LMARGIN', new_y='NEXT')

    pdf.ln(5)

    pdf.set_fill_color(0, 31, 63)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, f' Medical Records ({len(visits)} visits)', new_x='LMARGIN', new_y='NEXT', align='L', fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    for index, visit in enumerate(visits):
        if pdf.get_y() > 230:
            pdf.add_page()

        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 31, 63)
        pdf.cell(0, 8, f"Visit {len(visits) - index}: {visit['date']}", new_x='LMARGIN', new_y='NEXT')

        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(0, 0, 0)

        vitals = []
        if visit.get('vitals_bp'):
            vitals.append(f"BP: {visit['vitals_bp']}")
        if visit.get('vitals_weight'):
            vitals.append(f"Weight: {visit['vitals_weight']}kg")
        if visit.get('vitals_temp'):
            vitals.append(f"Temp: {visit['vitals_temp']}F")
        if visit.get('vitals_bsr'):
            vitals.append(f"BSR: {visit['vitals_bsr']}")
        if visit.get('vitals_spo2'):
            vitals.append(f"SPO2: {visit['vitals_spo2']}")
        if visit.get('vitals_heart_rate'):
            vitals.append(f"HR: {visit['vitals_heart_rate']}")

        if vitals:
            pdf.multi_cell(0, 6, "Vitals: " + " | ".join(vitals))

        complaint = visit.get('presenting_complaint')
        if complaint:
            pdf.set_x(10)
            pdf.multi_cell(0, 5, f"Complaint: {str(complaint)[:200]}")

        symptoms = visit.get('signs_symptoms')
        if symptoms:
            pdf.set_x(10)
            pdf.multi_cell(0, 5, f"Signs & Symptoms: {str(symptoms)[:200]}")

        differentials = visit.get('differentials')
        if differentials:
            pdf.set_x(10)
            pdf.multi_cell(0, 5, f"Differential Diagnosis: {str(differentials)[:200]}")

        treatment = visit.get('treatment_plan')
        if treatment:
            pdf.set_x(10)
            pdf.multi_cell(0, 5, f"Treatment Plan: {str(treatment)[:200]}")

        if visit.get('prescriptions'):
            pdf.set_font('Helvetica', 'I', 10)
            pdf.set_x(10)
            pdf.multi_cell(0, 6, 'Prescription:')
            for rx in visit['prescriptions']:
                med_name = str(rx.get('medicine_name', '') or '')[:40]
                qty = str(rx.get('quantity', '') or '')
                dosage = str(rx.get('dosage', '') or '')[:25]
                duration = str(rx.get('duration', '') or '')[:20]
                pdf.set_x(10)
                pdf.multi_cell(0, 5, f"  - {med_name} (Qty: {qty}) {dosage} {duration}")
            pdf.set_font('Helvetica', '', 10)

        pdf.ln(3)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    output_dir = get_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"patient_history_{patient_id}_{timestamp}.pdf"
    pdf.output(str(output_file))
    return str(output_file)


class PrescriptionPDF(FPDF):
    """Custom PDF class for prescriptions."""
    
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
    
    def header(self):
        """Prescription header with clinic info."""
        # Navy blue color
        self.set_text_color(0, 31, 63)
        # Try to place logo at top-left; ignore if missing
        try:
            logo_path = Path(__file__).parent / 'logopdf.png'
            if logo_path.exists():
                # x=10, y=6, width=18mm keeps it small and professional
                self.image(str(logo_path), x=10, y=6, w=18)
        except FileNotFoundError:
            pass
        except Exception:
            # Ignore any other image loading errors to avoid breaking PDF generation
            pass
        
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

    cursor.execute("""
        SELECT
            v.id, v.date,
            v.vitals_bp, v.vitals_weight, v.vitals_temp, v.vitals_bsr, v.vitals_spo2, v.vitals_heart_rate,
            v.past_medical_hx,
            p.name as patient_name, p.age, p.contact
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
    """, (visit_id,))
    visit = cursor.fetchone()

    if not visit:
        conn.close()
        raise ValueError(f"Visit {visit_id} not found")

    visit = dict(visit)

    cursor.execute("""
        SELECT medicine_name, dosage, duration, quantity
        FROM prescriptions
        WHERE visit_id = ?
        ORDER BY id
    """, (visit_id,))
    medicines = [dict(row) for row in cursor.fetchall()]
    conn.close()

    rx_text = "\n".join(
        f"{index + 1}. {med.get('medicine_name', '')} - {med.get('dosage', '')} ({med.get('quantity', '')}) {med.get('duration', '')}".strip()
        for index, med in enumerate(medicines)
    )

    payload = {
        "pt_name": visit.get("patient_name", ""),
        "age": str(visit.get("age", "") or ""),
        "contact": visit.get("contact", "") or "",
        "date": str(visit.get("date", "") or ""),
        "bp": visit.get("vitals_bp", "") or "",
        "hr": visit.get("vitals_heart_rate", "") or "",
        "so2": visit.get("vitals_spo2", "") or "",
        "rr": "",
        "temp": str(visit.get("vitals_temp", "") or ""),
        "ht_wt": f"Weight: {visit.get('vitals_weight')} kg" if visit.get("vitals_weight") else "",
        "bmi": "",
        "rbs": visit.get("vitals_bsr", "") or "",
        "fbs": "",
        "comorbs": visit.get("past_medical_hx", "") or "",
        "rx": rx_text,
        "pc_dx": "",
        "advice": "",
    }

    return generate_form_prescription_pdf(payload)


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