"""
DrKhan Hospital Management System
Prescription PDF Generator (cleaned)
"""

import os
import sys
import subprocess
import platform
import re
from pathlib import Path
from datetime import datetime
from math import ceil
from fpdf import FPDF

from database import get_connection
from utils import resource_path


def get_output_dir():
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            output_dir = app_data / "DrKhan" / "prescriptions"
        else:
            output_dir = Path.home() / ".drkhan" / "prescriptions"
    else:
        output_dir = Path(__file__).parent / "prescriptions"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", (value or "").strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "prescription"


def _find_symbol_font() -> Path | None:
    windows_root = Path(os.environ.get("WINDIR", r"C:\\Windows"))
    candidates = [
        windows_root / "Fonts" / "seguisym.ttf",
        windows_root / "Fonts" / "seguiemj.ttf",
        windows_root / "Fonts" / "segoeui.ttf",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _grayscale_logo_path() -> Path | None:
    p = Path(resource_path("static/logopdf.png"))
    return p if p.exists() else None


class PrescriptionSheetPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(12, 12, 12)
        self.symbol_font_name: str | None = None

    def set_symbol_font(self, font_name: str) -> None:
        self.symbol_font_name = font_name

    def _fit_text(self, text: str, width: float) -> str:
        text = str(text or "")
        if self.get_string_width(text) <= width:
            return text
        ellipsis = "..."
        while text and self.get_string_width(text + ellipsis) > width:
            text = text[:-1]
        return (text + ellipsis) if text else ellipsis

    def _value_text(self, value) -> str:
        if value in [None, ""]:
            return ""
        return str(value).strip()

    def _draw_grid(self, title: str, fields, columns: int, cell_height: float) -> None:
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(0, 0, 0)
        self.cell(0, 6, title, border=0, ln=1)

        usable_width = self.w - self.l_margin - self.r_margin
        gap = 2
        cell_width = (usable_width - (columns - 1) * gap) / columns
        start_x = self.l_margin
        start_y = self.get_y()

        for index, (label, value) in enumerate(fields):
            row = index // columns
            col = index % columns
            x = start_x + (col * (cell_width + gap))
            y = start_y + (row * (cell_height + gap))

            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.15)
            self.set_fill_color(255, 255, 255)
            self.rect(x, y, cell_width, cell_height)

            self.set_xy(x + 2, y + 2)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(0, 0, 0)
            self.multi_cell(cell_width - 4, 3.5, str(label), border=0)

            self.set_xy(x + 2, y + cell_height - 6)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(0, 0, 0)
            self.cell(cell_width - 4, 4, self._fit_text(self._value_text(value) or "__", cell_width - 4), border=0)

        rows = ceil(len(fields) / columns) if fields else 1
        self.set_y(start_y + (rows * (cell_height + gap)) + 1)

    def _draw_note_box(self, title: str, content: str, x: float, y: float, w: float, h: float, guide_lines: int = 3, draw_border: bool = True) -> None:
        if draw_border:
            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.15)
            self.rect(x, y, w, h)

        self.set_xy(x + 2, y + 2)
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(0, 0, 0)
        self.multi_cell(w - 4, 4, title)

        body_top = self.get_y() + 1
        body_left = x + 2
        body_width = w - 4
        body_height = h - (body_top - y) - 2

        text = self._value_text(content)
        if text:
            self.set_xy(body_left, body_top)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(30, 30, 30)
            self.multi_cell(body_width, 4.2, text)
        elif guide_lines > 0:
            self.set_draw_color(230, 230, 230)
            line_gap = max(4, body_height / (guide_lines + 1))
            for idx in range(guide_lines):
                line_y = body_top + (idx + 1) * line_gap
                if line_y < y + h - 2:
                    self.line(body_left, line_y, body_left + body_width, line_y)

    def _draw_rx_table(self, x: float, y: float, w: float, h: float, medicines) -> None:
        # RX title
        self.set_xy(x + 2, y + 2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(0, 0, 0)
        self.cell(w - 4, 5, "RX / Prescription", border=0, ln=1)

        inner_left = x + 2
        inner_top = self.get_y() + 1
        inner_width = w - 4

        # Use four columns (no column headers). Give the first column more width
        # so medicine names can fit better while the other three keep equal smaller widths.
        columns = 4
        first_col_share = 0.4  # 40% of inner width for medicine name
        remaining_share = 1.0 - first_col_share
        other_col_width = (inner_width * remaining_share) / (columns - 1)
        col_widths = [inner_width * first_col_share] + [other_col_width for _ in range(columns - 1)]

        rows = list(medicines or [])
        visible_rows = max(6, len(rows))

        # Base row height constraints and line height for wrapping
        min_row_h = 9
        line_h = 4.2

        def _estimate_lines(text: str, col_w: float) -> int:
            # Estimate number of wrapped lines for `text` within `col_w - 4` (padding)
            if not text:
                return 0
            content_w = max(col_w - 4, 10)
            self.set_font("Helvetica", "", 8)
            words = str(text).split()
            if not words:
                return 1
            lines = 0
            cur_w = 0.0
            space_w = self.get_string_width(' ')
            for word in words:
                w = self.get_string_width(word)
                if cur_w == 0:
                    # first word on line
                    cur_w = w
                else:
                    if cur_w + space_w + w <= content_w:
                        cur_w += space_w + w
                    else:
                        lines += 1
                        cur_w = w
                # handle overly long single word
                if cur_w > content_w:
                    # split roughly into chunks
                    approx = int(cur_w / content_w) + 1
                    lines += approx
                    cur_w = 0
            if cur_w > 0:
                lines += 1
            return max(1, lines)

        cur_y = inner_top
        for index in range(visible_rows):
            item = rows[index] if index < len(rows) else {}

            # Map the four free-form fields into columns
            col1 = self._value_text(item.get("medicine_name") if isinstance(item, dict) else getattr(item, "medicine_name", ""))
            col2 = self._value_text(item.get("dosage") if isinstance(item, dict) else getattr(item, "dosage", ""))
            col3 = self._value_text(item.get("duration") if isinstance(item, dict) else getattr(item, "duration", ""))
            # quantity may be numeric or free-form string
            col4 = self._value_text(item.get("quantity") if isinstance(item, dict) else getattr(item, "quantity", ""))

            values = [col1, col2, col3, col4]

            # Determine required height for this row based on wrapped lines in each column
            required_heights = []
            for ci in range(columns):
                lines = _estimate_lines(values[ci], col_widths[ci])
                required_heights.append(max(min_row_h, int(lines * line_h) + 2))
            row_h = max(required_heights)

            # alternating very light background
            if index % 2 == 0:
                self.set_fill_color(250, 250, 250)
            else:
                self.set_fill_color(255, 255, 255)

            cur_x = inner_left
            # Draw each cell then write text using multi_cell with computed line_h
            for col_idx in range(columns):
                w_col = col_widths[col_idx]
                self.set_draw_color(230, 230, 230)
                self.set_line_width(0.08)
                # draw rect (fill then stroke) using computed row height
                self.rect(cur_x, cur_y, w_col, row_h, style='DF')

                self.set_xy(cur_x + 2, cur_y + 1.6)
                self.set_font("Helvetica", "", 8)
                self.set_text_color(30, 30, 30)
                text_val = values[col_idx]
                if text_val:
                    # allow wrapping across multiple lines without truncation
                    self.multi_cell(w_col - 4, line_h, text_val, border=0, align="L")

                cur_x += w_col

            cur_y += row_h

    def _draw_special_note_box(self, x: float, y: float, w: float, h: float, note: str) -> None:
        # Render special note without an outer border to match left-column feel
        self._draw_note_box("Special Note", note, x, y, w, h, guide_lines=4, draw_border=False)

    def _extract_medicines(self, payload: dict):
        medicines = payload.get("medicines") or []
        if medicines:
            return medicines
        rx_text = self._value_text(payload.get("rx"))
        if not rx_text:
            return []
        lines = [line.strip() for line in rx_text.splitlines() if line.strip()]
        return [{"medicine_name": line, "dosage": "", "quantity": "", "duration": ""} for line in lines]

    def header(self):
        left_x = self.l_margin
        right_x = self.w - self.r_margin - 72
        top_y = 6

        try:
            logo_path = _grayscale_logo_path() or Path(resource_path("static/logopdf.png"))
            if logo_path and logo_path.exists():
                logo_w = 16
                logo_x = (self.w - logo_w) / 2
                self.image(str(logo_path), x=logo_x, y=6, w=logo_w)
                top_y = 22
            else:
                top_y = 20
        except Exception:
            top_y = 24

        self.set_y(top_y)
        self.set_text_color(0, 0, 0)

        self.set_xy(left_x, top_y)
        self.set_font("Helvetica", "B", 16)
        self.cell(72, 8, "DR. SHEHRAM KHAN", border=0, ln=1)
        self.set_x(left_x)
        self.set_font("Helvetica", "", 9)
        self.cell(72, 5, "MBBS, RMP", border=0, ln=1)
        self.set_x(left_x)
        self.cell(72, 5, "Family Physician", border=0, ln=1)
        self.set_x(left_x)
        self.set_font("Helvetica", "", 8)
        self.cell(72, 4, "EX House Physician & Surgeon Aziz Bhatti Shaheed", border=0, ln=1)

        self.set_xy(right_x, top_y)
        self.set_font("Helvetica", "B", 16)
        self.cell(72, 8, "DR KHAN CLINIC", border=0, ln=1, align="R")
        self.set_x(right_x)
        self.set_font("Helvetica", "", 9)
        self.cell(72, 5, "QUALITY HEALTHCARE FOR EVERY AGE", border=0, ln=1, align="R")
        self.set_x(right_x)
        self.cell(72, 5, "Ph: 0304 7501095", border=0, ln=1, align="R")
        self.set_x(right_x)
        self.cell(72, 5, "khanshehram000@gmail.com", border=0, ln=1, align="R")

        self.ln(1)
        self.set_draw_color(165, 165, 165)
        self.set_line_width(0.15)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "", 9)
        left_text = "Chak R.S Main Shujabad Road. Shujabad Pir Mubeen Town"
        right_text = "NOT VALID IN COURT"
        total_w = self.w - self.l_margin - self.r_margin
        half_w = total_w / 2
        # left-aligned address
        self.set_x(self.l_margin)
        self.cell(half_w, 5, left_text, align="L", border=0)
        # right-aligned notice
        self.set_x(self.l_margin + half_w)
        self.cell(half_w, 5, right_text, align="R", border=0)

    def render_prescription_sheet(self, payload: dict) -> None:
        # Main renderer: lays out patient info, vitals, clinical notes and RX
        self.add_page()

        patient_id = payload.get("patient_id", "")
        pt_name = payload.get("pt_name", "")
        age = payload.get("age", "")
        sex = payload.get("sex", "")
        contact = payload.get("contact", "")
        visit_date = payload.get("date", "")

        bp = payload.get("bp", "")
        hr = payload.get("hr", "")
        so2 = payload.get("so2", "")
        rr = payload.get("rr", "")
        temp = payload.get("temp", "")

        height_cm = payload.get("height_cm", "")
        weight_kg = payload.get("weight_kg", "")
        ht_wt = payload.get("ht_wt", "")
        bmi = payload.get("bmi", "")
        rbs = payload.get("rbs", "")
        bsr = payload.get("bsr", "") or rbs
        special_note = payload.get("special_note", "")

        # Accept multiple possible keys for backwards compatibility with templates/backend
        presenting_complaint = payload.get("presenting_complaint") or payload.get("presenting_complain") or payload.get("complaint") or ""
        medical_examination = payload.get("medical_examination") or payload.get("examination") or payload.get("medical_exam") or ""
        investigation_advised = payload.get("investigation_advised") or payload.get("treatment_plan") or payload.get("investigation") or ""
        provisional_diagnosis = payload.get("provisional_diagnosis") or payload.get("differentials") or payload.get("provisional") or ""

        medicines = self._extract_medicines(payload)

        # Patient info and vitals
        self._draw_grid(
            "Patient Information",
            [
                ("Patient ID", patient_id),
                ("Pt. Name", pt_name),
                ("Age", age),
                ("Sex", sex),
                ("Contact", contact),
                ("Date", visit_date),
            ],
            columns=3,
                cell_height=12,
        )

        self._draw_grid(
            "Vitals",
            [
                ("BP (mmHg)", bp),
                ("HR (bpm)", hr),
                ("SPO2 (%)", so2),
                ("Temp (F)", temp),
                ("Height (cm)", height_cm or payload.get("height", "") or (ht_wt.split(" cm /")[0] if " cm /" in ht_wt else "")),
                ("Weight (kg)", weight_kg or payload.get("weight", "") or (ht_wt.split("/ ")[-1].replace(" kg", "") if "/" in ht_wt else "")),
                ("BMI", bmi),
                ("BSR (mg/dL)", bsr),
            ],
            columns=4,
                cell_height=12,
        )

        # Columns: left clinical, right RX
        self.set_y(self.get_y() + 2)
        usable_width = self.w - self.l_margin - self.r_margin
        gap = 6
        # Always reserve a right column for RX and special note
        left_width = usable_width * 0.40
        right_width = usable_width - left_width - gap
        start_x = self.l_margin
        start_y = self.get_y()
        available_height = self.h - self.b_margin - start_y
        section_gap = 4
        section_height = (available_height - (3 * section_gap)) / 4
        section_height = max(section_height, 20)

        left_sections = [
            ("Presenting Complaint", presenting_complaint),
            ("Medical Examination", medical_examination),
            ("Investigation Advised", investigation_advised),
            ("Provisional Diagnosis", provisional_diagnosis),
        ]

        current_y = start_y
        for title, content in left_sections:
            # draw without individual borders
            # add a very subtle light-grey bounding box for visual balance
            self._draw_note_box(title, content, start_x, current_y, left_width, section_height, guide_lines=3, draw_border=True)
            current_y += section_height + section_gap

        # RX area and special note are always shown (RX table will show empty rows if no medicines)
        rx_height = max(available_height * 0.62, 60)
        note_y = start_y + rx_height + section_gap
        note_height = max(available_height - rx_height - section_gap, 18)
        # make Special Note box smaller (half of available note height)
        special_note_height = max(int(note_height / 2), 10)
        self._draw_rx_table(start_x + left_width + gap, start_y, right_width, rx_height, medicines)
        self._draw_special_note_box(start_x + left_width + gap, note_y, right_width, special_note_height, special_note)


def generate_form_prescription_pdf(payload: dict) -> str:
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
    return generate_form_prescription_pdf(payload)


# Minimal patient history generator kept for compatibility
def generate_patient_history_pdf(patient_id: int) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        raise ValueError(f"Patient {patient_id} not found")
    patient = dict(patient)

    # fetch visits for this patient
    cursor.execute(
        "SELECT id, date, presenting_complaint, examination, treatment_plan, differentials, vitals_bp, vitals_temp, vitals_spo2, vitals_heart_rate, vitals_weight FROM visits WHERE patient_id = ? ORDER BY date DESC",
        (patient_id,)
    )
    visits = [dict(r) for r in cursor.fetchall()]

    # fetch prescriptions per visit
    visit_prescriptions = {}
    for v in visits:
        cursor.execute(
            "SELECT medicine_name, dosage, duration, quantity FROM prescriptions WHERE visit_id = ? ORDER BY id",
            (v.get('id'),)
        )
        visit_prescriptions[v.get('id')] = [dict(r) for r in cursor.fetchall()]

    conn.close()

    output_dir = get_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _slugify(str(patient.get('name') or f'patient_{patient_id}'))
    output_file = output_dir / f"patient_history_{safe_name}_{timestamp}.pdf"

    # Render PDF
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(12, 12, 12)

    # Header helper
    def _draw_header():
        pdf.set_fill_color(255, 255, 255)
        # Prefer the colored logo for history PDFs; the black PDF logo is too heavy here.
        logo = Path(resource_path('static/logo.png'))
        y0 = 10
        try:
            if logo and Path(logo).exists():
                # smaller logo to avoid overlap and create breathing room
                pdf.image(str(logo), x=12, y=y0, w=14)
        except Exception:
            pass
        pdf.set_xy(32, y0 + 1)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 6, 'DR KHAN CLINIC', ln=1)
        pdf.set_x(32)
        pdf.set_font('Helvetica', '', 8.5)
        pdf.cell(0, 5, 'QUALITY HEALTHCARE FOR EVERY AGE', ln=1)
        # tighten spacing a bit
        pdf.ln(1.5)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.12)
        # place divider below the logo and header text to avoid overlapping the logo
        divider_y = max(pdf.get_y(), y0 + 18)
        try:
            pdf.line(pdf.l_margin, divider_y, pdf.w - pdf.r_margin, divider_y)
        except Exception:
            # fallback to current y if something unexpected happens
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        # move cursor a bit below the divider
        pdf.set_y(divider_y + 3)

    # Patient info box
    def _draw_patient_info():
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, 'Patient Summary', ln=1)
        pdf.set_font('Helvetica', '', 9)
        avail_w = pdf.w - pdf.l_margin - pdf.r_margin
        gap = 4
        left_w = (avail_w - gap) * 0.62
        right_w = avail_w - gap - left_w
        x = pdf.l_margin
        y = pdf.get_y()
        # compute required height dynamically based on content lines to avoid excessive whitespace
        left_lines = 1  # name
        left_lines += 1  # age/gender
        left_lines += 1  # contact
        right_lines = 3  # id, height, weight
        line_h = 4.2
        padding_v = 6
        content_h = max(left_lines, right_lines) * line_h
        box_h = max(22, int(content_h + padding_v))

        pdf.set_draw_color(220, 220, 220)
        pdf.rect(x, y, avail_w, box_h)
        pdf.line(x + left_w + (gap / 2), y, x + left_w + (gap / 2), y + box_h)

        pdf.set_xy(x + 3, y + 3)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.multi_cell(left_w - 6, 4.2, f"Name: {patient.get('name', '')}")
        pdf.set_x(x + 3)
        pdf.set_font('Helvetica', '', 9)
        pdf.multi_cell(left_w - 6, 4.2, f"Age: {patient.get('age', '')}    Gender: {patient.get('gender', '')}")
        pdf.set_x(x + 3)
        pdf.multi_cell(left_w - 6, 4.2, f"Contact: {patient.get('contact', '')}")

        pdf.set_xy(x + left_w + gap + 3, y + 3)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.multi_cell(right_w - 6, 4.2, f"Patient ID: {patient.get('id')}")
        pdf.set_x(x + left_w + gap + 3)
        pdf.set_font('Helvetica', '', 9)
        pdf.multi_cell(right_w - 6, 4.2, f"Height: {patient.get('height_cm','-')} cm")
        pdf.set_x(x + left_w + gap + 3)
        pdf.multi_cell(right_w - 6, 4.2, f"Weight: {patient.get('weight_kg','-')} kg")
        # move cursor to just below the box with a small gap
        pdf.set_y(y + box_h + 4)

    # Draw a visit block
    def _draw_visit(v: dict, prescriptions: list):
        pdf.set_font('Helvetica', 'B', 10)
        date_str = v.get('date') or ''
        pdf.cell(0, 6, f"Visit: {date_str}", ln=1)
        pdf.set_font('Helvetica', '', 9)
        avail_w = pdf.w - pdf.l_margin - pdf.r_margin
        if v.get('presenting_complaint'):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(avail_w, 4.5, f"Presenting Complaint: {v.get('presenting_complaint')}")
        if v.get('examination'):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(avail_w, 4.5, f"Medical Examination: {v.get('examination')}")
        if v.get('treatment_plan'):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(avail_w, 4.5, f"Investigation / Treatment: {v.get('treatment_plan')}")
        if v.get('differentials'):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(avail_w, 4.5, f"Provisional Diagnosis: {v.get('differentials')}")

        # Vitals summary line
        vitals = []
        if v.get('vitals_bp'):
            vitals.append(f"BP: {v.get('vitals_bp')}")
        if v.get('vitals_temp'):
            vitals.append(f"Temp: {v.get('vitals_temp')}")
        if v.get('vitals_spo2'):
            vitals.append(f"SPO2: {v.get('vitals_spo2')}")
        if v.get('vitals_heart_rate'):
            vitals.append(f"HR: {v.get('vitals_heart_rate')}")
        if v.get('vitals_weight'):
            vitals.append(f"Wt: {v.get('vitals_weight')}kg")
        if vitals:
            pdf.set_font('Helvetica', 'I', 9)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(avail_w, 4.2, ' | '.join(vitals))

        # Prescriptions table
        if prescriptions:
            pdf.ln(2)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(0, 5, 'Medicines:', ln=1)
            pdf.set_font('Helvetica', '', 9)
            col_w = (pdf.w - pdf.l_margin - pdf.r_margin)
            pdf.set_fill_color(245, 245, 245)

            # helper to estimate wrapped lines for a given width
            def _estimate_lines(text: str, width: float, line_h: float = 4.8) -> int:
                if not text:
                    return 1
                pdf.set_font('Helvetica', '', 9)
                words = str(text).split()
                if not words:
                    return 1
                content_w = max(width - 6, 10)
                space_w = pdf.get_string_width(' ')
                lines = 0
                cur_w = 0.0
                for word in words:
                    w = pdf.get_string_width(word)
                    if cur_w == 0:
                        cur_w = w
                    else:
                        if cur_w + space_w + w <= content_w:
                            cur_w += space_w + w
                        else:
                            lines += 1
                            cur_w = w
                    if cur_w > content_w:
                        approx = int(cur_w / content_w) + 1
                        lines += approx
                        cur_w = 0
                if cur_w > 0:
                    lines += 1
                return max(1, lines)

            line_h = 4.8
            for p in prescriptions:
                name = p.get('medicine_name', '') or ''
                if not name:
                    continue
                entry_text = f"- {name}"
                x0 = pdf.l_margin
                y0 = pdf.get_y()
                lines = _estimate_lines(entry_text, col_w, line_h)
                h_box = (lines * line_h) + 6
                # draw box and then text inside with padding
                pdf.set_draw_color(230, 230, 230)
                pdf.rect(x0, y0, col_w, h_box)
                pdf.set_xy(x0 + 3, y0 + 2)
                pdf.multi_cell(col_w - 6, line_h, entry_text, border=0)
                # advance to below box
                pdf.set_y(y0 + h_box + 2)

        # slightly reduced gap after each visit to keep history compact
        pdf.ln(4)

    # Compose document
    pdf.add_page()
    _draw_header()
    _draw_patient_info()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(40, 40, 40)

    if not visits:
        pdf.cell(0, 6, 'No visits recorded for this patient.', ln=1)
    else:
        for v in visits:
            # page break if needed
            if pdf.get_y() > pdf.h - pdf.b_margin - 60:
                pdf.add_page()
                _draw_header()
            _draw_visit(v, visit_prescriptions.get(v.get('id', 0), []))

    # Footer
    pdf.set_y(-20)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, 'Generated by Dr Khan Clinic', ln=1)

    pdf.output(str(output_file))
    return str(output_file)


def open_pdf(file_path: str):
    try:
        if platform.system() == 'Windows':
            os.startfile(file_path)
        elif platform.system() == 'Darwin':
            subprocess.run(['open', file_path], check=True)
        else:
            subprocess.run(['xdg-open', file_path], check=True)
    except Exception as e:
        print(f"Could not open PDF: {e}")
