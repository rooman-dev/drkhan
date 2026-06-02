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

        # Make medicine name column wider, remaining columns share the rest
        col1_width = inner_width * 0.50
        other_width = (inner_width - col1_width) / 3.0
        col_widths = [col1_width, other_width, other_width, other_width]

        header_labels = ["Medicine Name", "Dosage", "Quantity", "Frequency"]
        header_h = 7
        cur_y = inner_top

        self.set_fill_color(240, 240, 240)
        self.set_draw_color(210, 210, 210)
        self.set_line_width(0.12)
        cur_x = inner_left
        for col_idx, label in enumerate(header_labels):
            w_col = col_widths[col_idx]
            self.rect(cur_x, cur_y, w_col, header_h, style='DF')
            self.set_xy(cur_x + 2, cur_y + 1.6)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(0, 0, 0)
            self.cell(w_col - 4, 4, label, border=0, align="C")
            cur_x += w_col

        rows = list(medicines or [])
        visible_rows = max(6, len(rows))
        body_top = inner_top + header_h

        # Base row height constraints
        min_row_h = 9
        max_row_h = 28
        line_h = 3.8

        cur_y = body_top
        for index in range(visible_rows):
            item = rows[index] if index < len(rows) else {}

            # Prepare values
            medicine_name = self._value_text(item.get("medicine_name") if isinstance(item, dict) else getattr(item, "medicine_name", ""))
            dosage = self._value_text(item.get("dosage") if isinstance(item, dict) else getattr(item, "dosage", ""))
            quantity = self._value_text(item.get("quantity") if isinstance(item, dict) else getattr(item, "quantity", ""))
            freq_times = self._value_text(item.get("freq_times") if isinstance(item, dict) else getattr(item, "freq_times", ""))
            freq_days = self._value_text(item.get("freq_days") if isinstance(item, dict) else getattr(item, "freq_days", ""))
            duration = self._value_text(item.get("duration") if isinstance(item, dict) else getattr(item, "duration", ""))
            if freq_times and freq_days:
                frequency = f"{freq_times}×{freq_days}"
            elif freq_times:
                frequency = freq_times
            else:
                frequency = duration

            values = [medicine_name, dosage, quantity, frequency]

            # Estimate required height based on medicine name wrapping
            name_width = col_widths[0] - 4
            if medicine_name:
                name_lines = max(1, int(ceil(self.get_string_width(medicine_name) / max(1.0, name_width))))
            else:
                name_lines = 1
            required_h = max_row_h
            try:
                required_h = max(min_row_h, min(max_row_h, int(name_lines * line_h) + 4))
            except Exception:
                required_h = min_row_h

            row_h = required_h

            # alternating very light background
            if index % 2 == 0:
                self.set_fill_color(250, 250, 250)
            else:
                self.set_fill_color(255, 255, 255)

            cur_x = inner_left

            for col_idx in range(4):
                w_col = col_widths[col_idx]
                self.set_draw_color(230, 230, 230)
                self.set_line_width(0.08)
                # draw rect (fill then stroke)
                self.rect(cur_x, cur_y, w_col, row_h, style='DF')

                self.set_xy(cur_x + 2, cur_y + 1.6)
                self.set_font("Helvetica", "", 8)
                self.set_text_color(30, 30, 30)
                # For medicine name allow wrapping (no truncation)
                text_val = values[col_idx]
                if text_val:
                    if col_idx == 0:
                        self.multi_cell(w_col - 4, line_h, text_val, border=0, align="L")
                    else:
                        self.multi_cell(w_col - 4, line_h, self._fit_text(text_val, w_col - 4), border=0, align="L")
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

        presenting_complaint = payload.get("presenting_complaint") or ""
        medical_examination = payload.get("medical_examination") or ""
        investigation_advised = payload.get("investigation_advised") or ""
        provisional_diagnosis = payload.get("provisional_diagnosis") or ""

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
    conn.close()
    output_dir = get_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"patient_history_{patient_id}_{timestamp}.pdf"
    # stub: create an empty PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', '', 12)
    pdf.cell(0, 10, f"Patient history for {patient.get('name', patient_id)}")
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
