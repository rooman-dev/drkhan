"""
DrKhan Hospital Management System
Main Application Entry Point
"""

import uvicorn
import webview
import threading
import shutil
import os
import json
import socket
from datetime import date, datetime, timezone
from pathlib import Path
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

from database import init_database, get_connection, hash_password
from database import add_test_data
from prescription import generate_prescription_form_pdf, generate_patient_history_pdf
from utils import resource_path, ensure_windows_icon_path

# Initialize FastAPI app
app = FastAPI(title="DrKhan Clinic", version="1.0.0")

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Simple session storage (in-memory for single user)
session = {"logged_in": False, "user": None}

# Configure simple logging for debugging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')


# ============ Pydantic Models ============
class LoginRequest(BaseModel):
    username: str
    password: str


class PatientCreate(BaseModel):
    name: str
    age: int
    contact: Optional[str] = None
    gender: Optional[str] = None
    bsr: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    # If provided, backend will create an initial visit for this patient
    create_visit: Optional[bool] = False
    initial_visit: Optional[dict] = None


class MedicineItem(BaseModel):
    inventory_id: Optional[int] = None
    medicine_name: Optional[str] = None
    quantity: int = 1
    dosage: Optional[str] = None
    price: float = 0.0
    # Extended fields to carry prescription metadata from client
    freq_times: Optional[int] = None
    freq_days: Optional[int] = None
    duration: Optional[str] = None
    base_quantity: Optional[int] = None


class VisitCreate(BaseModel):
    patient_id: int
    vitals_bp: Optional[str] = None
    vitals_weight: Optional[float] = None
    vitals_temp: Optional[float] = None
    vitals_bsr: Optional[str] = None
    vitals_spo2: Optional[str] = None
    vitals_heart_rate: Optional[str] = None
    presenting_complaint: Optional[str] = None
    signs_symptoms: Optional[str] = None
    history_presenting_illness: Optional[str] = None
    past_medical_hx: Optional[str] = None
    family_history: Optional[str] = None
    examination: Optional[str] = None
    differentials: Optional[str] = None
    treatment_plan: Optional[str] = None
    consultation_fee: float = 0
    medicines: List[MedicineItem] = []
    lab_report_path: Optional[str] = None


class VisitUpdate(BaseModel):
    vitals_bp: Optional[str] = None
    vitals_weight: Optional[float] = None
    vitals_temp: Optional[float] = None
    vitals_bsr: Optional[str] = None
    vitals_spo2: Optional[str] = None
    vitals_heart_rate: Optional[str] = None
    vitals_height_cm: Optional[float] = None
    vitals_bmi: Optional[float] = None
    presenting_complaint: Optional[str] = None
    signs_symptoms: Optional[str] = None
    history_presenting_illness: Optional[str] = None
    past_medical_hx: Optional[str] = None
    family_history: Optional[str] = None
    examination: Optional[str] = None
    differentials: Optional[str] = None
    treatment_plan: Optional[str] = None
    lab_report_path: Optional[str] = None
    medicines: List[MedicineItem] = []


class PrescriptionPrintRequest(BaseModel):
    patient_id: Optional[int] = None
    pt_name: str
    age: str
    sex: Optional[str] = None
    contact: str
    date: str
    bp: Optional[str] = None
    hr: Optional[str] = None
    so2: Optional[str] = None
    rr: Optional[str] = None
    temp: Optional[str] = None
    height_cm: Optional[str] = None
    weight_kg: Optional[str] = None
    ht_wt: Optional[str] = None
    bmi: Optional[str] = None
    rbs: Optional[str] = None
    comorbs: Optional[str] = None
    presenting_complaint: Optional[str] = None
    medical_examination: Optional[str] = None
    investigation_advised: Optional[str] = None
    provisional_diagnosis: Optional[str] = None
    special_note: Optional[str] = None
    pc_dx: Optional[str] = None
    rx: Optional[str] = None
    advice: Optional[str] = None
    medicines: List[MedicineItem] = []


# ============ Auth Helpers ============
def check_auth():
    """Check if user is logged in."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session["user"]


def get_current_user():
    """Get current logged in user or None."""
    if session.get("logged_in"):
        return session["user"]
    return None


# ============ Routes ============

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    # If already logged in, redirect to dashboard
    if session.get("logged_in"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.post("/login")
async def login(credentials: LoginRequest):
    """Verify login credentials."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Hash the provided password
    password_hash = hash_password(credentials.password)
    
    # Check credentials
    cursor.execute(
        "SELECT id, username, full_name FROM users WHERE username = ? AND password_hash = ?",
        (credentials.username, password_hash)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user:
        # Set session
        session["logged_in"] = True
        session["user"] = {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"]
        }
        return JSONResponse({
            "success": True,
            "message": "Login successful",
            "user": session["user"]
        })
    else:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Access Denied"}
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the dashboard page (protected)."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "user": session["user"]
    })


@app.get("/api/dashboard")
async def get_dashboard_stats():
    """Return dashboard statistics."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    
    # Get today's patient/visit count
    cursor.execute(
        "SELECT COUNT(*) as count FROM visits WHERE date = ?",
        (today,)
    )
    patients_today = cursor.fetchone()["count"]
    
    # Get today's revenue
    cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM finance WHERE date = ? AND type = 'Income'",
        (today,)
    )
    revenue = cursor.fetchone()["total"]
    
    # Get low stock count (items with stock < 10)
    cursor.execute("SELECT COUNT(*) as count FROM inventory WHERE stock < 10")
    low_stock = cursor.fetchone()["count"]
    
    # Get today's visits with patient names
    cursor.execute("""
        SELECT 
            v.id,
            v.date,
            v.presenting_complaint,
            p.name as patient_name
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.date = ?
        ORDER BY v.id DESC
        LIMIT 10
    """, (today,))
    visits = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "patients_today": patients_today,
        "revenue": revenue,
        "low_stock": low_stock,
        "visits": visits
    }


@app.get("/api/stats")
async def get_stats():
    """Return today's patient count and revenue for dashboard widgets."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    
    # Get today's patient/visit count
    cursor.execute(
        "SELECT COUNT(*) as count FROM visits WHERE date = ?",
        (today,)
    )
    patients_today = cursor.fetchone()["count"]
    
    # Get today's revenue
    cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM finance WHERE date = ? AND type = 'Income'",
        (today,)
    )
    revenue = cursor.fetchone()["total"]
    
    conn.close()
    
    return {
        "patients_today": patients_today,
        "revenue": revenue
    }


@app.post("/logout")
async def logout():
    """Log out the user."""
    session["logged_in"] = False
    session["user"] = None
    return JSONResponse({"success": True, "message": "Logged out"})


@app.get("/logout")
async def logout_redirect():
    """Log out and redirect to login page."""
    session["logged_in"] = False
    session["user"] = None
    return RedirectResponse(url="/", status_code=302)


# ============ Visit Management Routes ============

@app.get("/visits", response_class=HTMLResponse)
async def visits_page(request: Request):
    """Serve the visit management page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM visits LIMIT 1")
    has_visits = cursor.fetchone() is not None
    conn.close()

    return templates.TemplateResponse(request, "visits.html", {
        "request": request,
        "user": session["user"],
        "visits": [1] if has_visits else []
    })


@app.get("/api/visits/all")
async def get_all_visits(search: str = "", date_filter: str = "", page: int = 1, page_size: int = 20):
    """Get all visits with search and pagination."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build date filter
    date_condition = ""
    today = date.today().isoformat()
    
    if date_filter == "today":
        date_condition = f"AND v.date = '{today}'"
    elif date_filter == "week":
        from datetime import timedelta
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        date_condition = f"AND v.date >= '{week_ago}'"
    elif date_filter == "month":
        from datetime import timedelta
        month_ago = (date.today() - timedelta(days=30)).isoformat()
        date_condition = f"AND v.date >= '{month_ago}'"
    
    # Build search condition
    if search:
        search_condition = f"""
            AND (p.name LIKE '%{search}%' 
            OR v.presenting_complaint LIKE '%{search}%' 
            OR CAST(v.id AS TEXT) LIKE '%{search}%')
        """
    else:
        search_condition = ""
    
    # Get total count
    cursor.execute(f"""
        SELECT COUNT(*) as count 
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE 1=1 {date_condition} {search_condition}
    """)
    total = cursor.fetchone()["count"]
    total_pages = max(1, (total + page_size - 1) // page_size)
    
    # Get paginated results
    offset = (page - 1) * page_size
    cursor.execute(f"""
        SELECT 
            v.id,
            v.date,
            v.presenting_complaint,
            p.name as patient_name
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE 1=1 {date_condition} {search_condition}
        ORDER BY v.id DESC
        LIMIT ? OFFSET ?
    """, (page_size, offset))
    
    visits = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "visits": visits,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@app.get("/api/visits/stats")
async def get_visits_stats():
    """Get visit statistics."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    from datetime import timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    
    # Total visits
    cursor.execute("SELECT COUNT(*) as count FROM visits")
    total = cursor.fetchone()["count"]
    
    # Today's visits
    cursor.execute("SELECT COUNT(*) as count FROM visits WHERE date = ?", (today,))
    today_count = cursor.fetchone()["count"]
    
    # This week's visits
    cursor.execute("SELECT COUNT(*) as count FROM visits WHERE date >= ?", (week_ago,))
    week_count = cursor.fetchone()["count"]
    
    conn.close()
    
    return {
        "total": total,
        "today": today_count,
        "week": week_count
    }


# ============ Patient Management Routes ============

@app.get("/patients", response_class=HTMLResponse)
async def patients_page(request: Request):
    """Serve the patients management page."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM patients LIMIT 1")
    has_patients = cursor.fetchone() is not None
    conn.close()

    return templates.TemplateResponse(request, "patients.html", {
        "request": request,
        "user": session["user"],
        "patients": [1] if has_patients else []
    })


@app.get("/api/patients")
async def get_patients(search: str = ""):
    """Get all patients with optional search."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if search:
        cursor.execute("""
            SELECT 
                p.id, p.name, p.age, p.contact, p.gender, p.address,
                (SELECT MAX(date) FROM visits WHERE patient_id = p.id) as last_visit,
                p.created_at as date_added,
                p.modified_at as date_modified
            FROM patients p
            WHERE p.name LIKE ? OR p.contact LIKE ? OR CAST(p.id AS TEXT) LIKE ? OR p.address LIKE ?
            ORDER BY p.name
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
            SELECT 
                p.id, p.name, p.age, p.contact, p.gender, p.address,
                (SELECT MAX(date) FROM visits WHERE patient_id = p.id) as last_visit,
                p.created_at as date_added,
                p.modified_at as date_modified
            FROM patients p
            ORDER BY p.id DESC
        """)
    
    patients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return patients


@app.post("/api/patients")
async def create_patient(patient: PatientCreate):
    """Create a new patient."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO patients (name, age, height_cm, weight_kg, bmi, bsr, contact, gender, created_at, modified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (
        patient.name,
        patient.age,
        getattr(patient, 'height_cm', None),
        getattr(patient, 'weight_kg', None),
        getattr(patient, 'bmi', None),
        getattr(patient, 'bsr', None),
        patient.contact,
        patient.gender
    ))
    
    patient_id = cursor.lastrowid
    visit_id = None

    try:
        # If client requested an initial visit, create it atomically
        if getattr(patient, 'create_visit', False) or getattr(patient, 'initial_visit', None):
            from datetime import date
            today = date.today().isoformat()
            iv = patient.initial_visit or {}

            cursor.execute("""
                INSERT INTO visits (patient_id, date, vitals_bp, vitals_weight, vitals_temp, vitals_bsr, 
                    vitals_spo2, vitals_heart_rate, presenting_complaint, signs_symptoms, 
                    history_presenting_illness, past_medical_hx, family_history, examination, 
                    differentials, treatment_plan, lab_report_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                patient_id,
                today,
                iv.get('vitals_bp'),
                iv.get('vitals_weight'),
                iv.get('vitals_temp'),
                iv.get('vitals_bsr'),
                iv.get('vitals_spo2'),
                iv.get('vitals_heart_rate'),
                iv.get('presenting_complaint'),
                iv.get('signs_symptoms'),
                iv.get('history_presenting_illness'),
                iv.get('past_medical_hx'),
                iv.get('family_history'),
                iv.get('examination'),
                iv.get('differentials'),
                iv.get('treatment_plan'),
                iv.get('lab_report_path')
            ))

            visit_id = cursor.lastrowid

            # Process medicines if any were provided
            meds = iv.get('medicines') or []
            for med in meds:
                item = None
                if med.get('inventory_id') is not None:
                    cursor.execute("SELECT stock, brand_name FROM inventory WHERE id = ?", (med.get('inventory_id'),))
                    item = cursor.fetchone()
                    if item:
                        cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (med.get('quantity', 0), med.get('inventory_id')))

                medicine_name = (med.get('medicine_name') or (item['brand_name'] if item else None) or f"Medicine {med.get('inventory_id') or ''}").strip()
                if not medicine_name:
                    medicine_name = 'Medicine'

                duration_val = med.get('duration') or (f"{int(med.get('freq_days'))} days" if med.get('freq_days') else '7 days')

                cursor.execute("""
                    INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price, inventory_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (visit_id, med.get('dosage') or 'As directed', med.get('dosage') or 'As directed', duration_val, med.get('quantity', 1), med.get('price', 0), med.get('inventory_id')))

            # Update patient's modified timestamp
            cursor.execute("UPDATE patients SET modified_at = datetime('now') WHERE id = ?", (patient_id,))

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()

    resp = {"success": True, "patient_id": patient_id, "message": "Patient created successfully"}
    if visit_id:
        resp['visit_id'] = visit_id

    return resp


@app.post('/api/log_client_error')
async def log_client_error(request: Request):
    """Receive client-side error reports for debugging (writes to logs/client_errors.log)."""
    try:
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": (await request.body()).decode('utf-8', errors='replace')}

        os.makedirs('logs', exist_ok=True)
        with open(os.path.join('logs', 'client_errors.log'), 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {request.client.host if request.client else 'unknown'} | {json.dumps(payload, ensure_ascii=False)}\n")
    except Exception as e:
        logging.exception('Failed to log client error')

    return JSONResponse({"ok": True})


@app.get('/api/debug/patients_count')
async def debug_patients_count():
    """Return a quick count of patients for debugging."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM patients')
        cnt = cursor.fetchone()[0]
        conn.close()
        return {"count": cnt}
    except Exception as e:
        logging.exception('Failed debug count')
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: int):
    """Get a single patient by ID."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    conn.close()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    return dict(patient)


@app.delete("/api/patients/{patient_id}")
async def delete_patient(patient_id: int):
    """Delete a patient and all their associated visits and prescriptions."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if patient exists
    cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Get all visit IDs for this patient to delete prescriptions
    cursor.execute("SELECT id FROM visits WHERE patient_id = ?", (patient_id,))
    visit_ids = [row['id'] for row in cursor.fetchall()]
    
    # Delete prescriptions for all visits
    if visit_ids:
        placeholders = ','.join('?' * len(visit_ids))
        cursor.execute(f"DELETE FROM prescriptions WHERE visit_id IN ({placeholders})", visit_ids)
    
    # Delete all visits for this patient
    cursor.execute("DELETE FROM visits WHERE patient_id = ?", (patient_id,))
    
    # Delete the patient
    cursor.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Patient and all associated records deleted successfully"}


@app.get("/api/patients/{patient_id}/history")
async def get_patient_history(patient_id: int):
    """Get visit history for a patient."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, date, vitals_bp, vitals_weight, vitals_temp, vitals_bsr,
            vitals_spo2, vitals_heart_rate, presenting_complaint, signs_symptoms, 
            differentials, treatment_plan
        FROM visits
        WHERE patient_id = ?
        ORDER BY date DESC
    """, (patient_id,))
    
    visits = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return visits


@app.get("/api/patients/{patient_id}/full-record")
async def get_patient_full_record(patient_id: int):
    """Get complete patient record including demographics, visits, and prescriptions."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get patient details
    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    
    if not patient:
        conn.close()
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient_data = dict(patient)
    
    # Get all visits with their prescriptions
    cursor.execute("""
        SELECT id, date, vitals_bp, vitals_weight, vitals_temp, vitals_bsr,
            vitals_spo2, vitals_heart_rate, presenting_complaint, signs_symptoms,
            history_presenting_illness, past_medical_hx, family_history,
            examination, differentials, treatment_plan, lab_report_path
        FROM visits
        WHERE patient_id = ?
        ORDER BY date DESC
    """, (patient_id,))
    
    visits = []
    for visit_row in cursor.fetchall():
        visit = dict(visit_row)
        # Get prescriptions for this visit
        cursor.execute("""
            SELECT medicine_name, dosage, duration, quantity, price, inventory_id
            FROM prescriptions
            WHERE visit_id = ?
        """, (visit['id'],))
        visit['prescriptions'] = [dict(p) for p in cursor.fetchall()]
        visits.append(visit)
    
    conn.close()
    
    return {
        "patient": patient_data,
        "visits": visits
    }


# ============ Visit Management Routes ============

@app.post("/api/visits")
async def create_visit(visit: VisitCreate):
    """Create a new visit with prescription and auto-billing."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    
    try:
        # 1. Create the visit record
        cursor.execute("""
            INSERT INTO visits (patient_id, date, vitals_bp, vitals_weight, vitals_temp, vitals_bsr, 
                vitals_spo2, vitals_heart_rate, presenting_complaint, signs_symptoms, 
                history_presenting_illness, past_medical_hx, family_history, examination, 
                differentials, treatment_plan, lab_report_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            visit.patient_id,
            today,
            visit.vitals_bp,
            visit.vitals_weight,
            visit.vitals_temp,
            visit.vitals_bsr,
            visit.vitals_spo2,
            visit.vitals_heart_rate,
            visit.presenting_complaint,
            visit.signs_symptoms,
            visit.history_presenting_illness,
            visit.past_medical_hx,
            visit.family_history,
            visit.examination,
            visit.differentials,
            visit.treatment_plan,
            visit.lab_report_path
        ))
        visit_id = cursor.lastrowid
        
        # 2. Process medicines - deduct from inventory and save prescriptions
        medicine_total = 0
        for med in visit.medicines:
            item = None
            if med.inventory_id is not None:
                cursor.execute("SELECT stock, brand_name FROM inventory WHERE id = ?", (med.inventory_id,))
                item = cursor.fetchone()

                if item:
                    cursor.execute("""
                        UPDATE inventory SET stock = stock - ? WHERE id = ?
                    """, (med.quantity, med.inventory_id))

            medicine_name = (med.medicine_name or (item["brand_name"] if item else None) or f"Medicine {med.inventory_id or ''}").strip()
            if not medicine_name:
                medicine_name = "Medicine"

            # Save to prescriptions table
            duration_val = None
            # Accept either numeric days or a duration string sent by client
            if getattr(med, 'duration', None):
                duration_val = med.duration
            elif getattr(med, 'freq_days', None):
                try:
                    duration_val = f"{int(med.freq_days)} days"
                except Exception:
                    duration_val = str(med.freq_days)
            else:
                duration_val = "7 days"

            cursor.execute("""
                INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price, inventory_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (visit_id, medicine_name, med.dosage or "As directed", duration_val, med.quantity, med.price, getattr(med, 'inventory_id', None)))
            
            medicine_total += med.price * med.quantity
        
        # 3. Calculate total bill (for display only, not added to finance)
        total_bill = medicine_total

        # 4. Touch patient modification timestamp for date-modified sorting
        # If weight or bsr provided on visit, update patient's vitals
        try:
            if visit.vitals_weight is not None or visit.vitals_bsr is not None:
                # Fetch current patient height to compute BMI if possible
                cursor.execute("SELECT height_cm FROM patients WHERE id = ?", (visit.patient_id,))
                row = cursor.fetchone()
                height_cm = row['height_cm'] if row else None
                new_bmi = None
                if visit.vitals_weight is not None and height_cm:
                    try:
                        h_m = float(height_cm) / 100.0
                        if h_m > 0:
                            new_bmi = round(float(visit.vitals_weight) / (h_m * h_m), 2)
                    except Exception:
                        new_bmi = None

                cursor.execute(
                    "UPDATE patients SET weight_kg = COALESCE(?, weight_kg), bmi = COALESCE(?, bmi), bsr = COALESCE(?, bsr), modified_at = datetime('now') WHERE id = ?",
                    (visit.vitals_weight, new_bmi, visit.vitals_bsr, visit.patient_id)
                )
            else:
                cursor.execute("UPDATE patients SET modified_at = datetime('now') WHERE id = ?", (visit.patient_id,))
        except Exception:
            # ensure timestamp is touched even if vitals update fails
            cursor.execute("UPDATE patients SET modified_at = datetime('now') WHERE id = ?", (visit.patient_id,))
        
        # Note: Medicine costs are NOT added to finance
        # Finance entries should be added manually via the Add Income button
        
        conn.commit()
        
        return {
            "success": True,
            "visit_id": visit_id,
            "total_bill": total_bill,
            "message": "Visit saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============ Inventory Routes ============

@app.get("/api/inventory")
async def get_inventory():
    """Get all inventory items."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, brand_name, formula, stock, price
        FROM inventory
        ORDER BY brand_name
    """)
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return items


@app.get("/api/inventory/search")
async def search_inventory(q: str = ""):
    """Search inventory by brand name or formula."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if q:
        cursor.execute("""
            SELECT id, brand_name, formula, stock, price
            FROM inventory
            WHERE brand_name LIKE ? OR formula LIKE ?
            ORDER BY brand_name
        """, (f"%{q}%", f"%{q}%"))
    else:
        cursor.execute("""
            SELECT id, brand_name, formula, stock, price
            FROM inventory
            ORDER BY brand_name
        """)
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return items


@app.post("/api/inventory")
async def create_inventory_item(request: Request):
    """Add a new medicine to inventory."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO inventory (brand_name, formula, stock, price)
        VALUES (?, ?, ?, ?)
    """, (
        data.get("brand_name"),
        data.get("formula"),
        data.get("stock", 0),
        data.get("price", 0)
    ))
    
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"success": True, "id": item_id, "message": "Medicine added successfully"}


@app.put("/api/inventory/{item_id}")
async def update_inventory_item(item_id: int, request: Request):
    """Update a medicine in inventory."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE inventory 
        SET brand_name = ?, formula = ?, price = ?
        WHERE id = ?
    """, (
        data.get("brand_name"),
        data.get("formula"),
        data.get("price", 0),
        item_id
    ))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Medicine updated successfully"}


@app.post("/api/inventory/{item_id}/stock")
async def add_stock(item_id: int, request: Request):
    """Add stock to an inventory item and record expense."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    quantity = data.get("quantity", 0)
    cost = data.get("cost", 0)
    notes = data.get("notes", "")
    
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    
    try:
        # Get medicine name
        cursor.execute("SELECT brand_name FROM inventory WHERE id = ?", (item_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Medicine not found")
        
        medicine_name = item["brand_name"]
        
        # Update stock
        cursor.execute("""
            UPDATE inventory SET stock = stock + ? WHERE id = ?
        """, (quantity, item_id))
        
        # Add expense record to finance
        if cost > 0:
            expense_notes = f"Stock In: {medicine_name} x{quantity}"
            if notes:
                expense_notes += f" - {notes}"
            
            cursor.execute("""
                INSERT INTO finance (date, type, amount, notes)
                VALUES (?, 'Expense', ?, ?)
            """, (today, cost, expense_notes))
        
        conn.commit()
        return {"success": True, "message": "Stock added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/inventory/{item_id}/stock-out")
async def subtract_stock(item_id: int, request: Request):
    """Subtract stock from an inventory item."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    quantity = data.get("quantity", 0)
    notes = data.get("notes", "")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get current stock
        cursor.execute("SELECT brand_name, stock FROM inventory WHERE id = ?", (item_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Medicine not found")
        
        if item["stock"] < quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        
        # Update stock
        cursor.execute("""
            UPDATE inventory SET stock = stock - ? WHERE id = ?
        """, (quantity, item_id))
        
        conn.commit()
        return {"success": True, "message": "Stock subtracted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/inventory/{item_id}")
async def delete_inventory_item(item_id: int):
    """Delete a medicine from inventory."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if medicine exists
        cursor.execute("SELECT id FROM inventory WHERE id = ?", (item_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Medicine not found")
        
        # Delete the medicine
        cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        
        conn.commit()
        return {"success": True, "message": "Medicine deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/search_medicine")
async def search_medicine_with_alternatives(q: str = ""):
    """Search medicine and find alternatives with same formula if out of stock."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not q:
        return {"searched_medicine": None, "alternatives": []}
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Search for the medicine by brand name or formula
    cursor.execute("""
        SELECT id, brand_name, formula, stock, price
        FROM inventory
        WHERE brand_name LIKE ? OR formula LIKE ?
        ORDER BY 
            CASE WHEN brand_name LIKE ? THEN 0 ELSE 1 END,
            brand_name
        LIMIT 1
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    
    searched = cursor.fetchone()
    
    if not searched:
        conn.close()
        return {"searched_medicine": None, "alternatives": []}
    
    searched_medicine = dict(searched)
    alternatives = []
    
    # If out of stock or low stock, find alternatives with same formula
    if searched_medicine["stock"] < 10 and searched_medicine["formula"]:
        cursor.execute("""
            SELECT id, brand_name, formula, stock, price
            FROM inventory
            WHERE formula = ? AND id != ? AND stock > 0
            ORDER BY stock DESC
        """, (searched_medicine["formula"], searched_medicine["id"]))
        
        alternatives = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "searched_medicine": searched_medicine,
        "alternatives": alternatives
    }


@app.get("/patients/new", response_class=HTMLResponse)
async def new_patient_page(request: Request):
    """Redirect to patients page (modal handles new patient)."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url="/patients", status_code=302)


@app.get("/visits/new", response_class=HTMLResponse)
async def new_visit_page(request: Request):
    """Redirect to patients page (modal handles new visit)."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url="/patients", status_code=302)


# ============ Pharmacy Page Route ============

@app.get("/pharmacy", response_class=HTMLResponse)
async def pharmacy_page(request: Request):
    """Serve the pharmacy/inventory management page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "pharmacy.html", {
        "request": request,
        "user": session["user"]
    })


# ============ Finance Page & API Routes ============

@app.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request):
    """Serve the finance management page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "finance.html", {
        "request": request,
        "user": session["user"]
    })


@app.get("/api/finance/summary")
async def get_finance_summary():
    """Get total income, expenses, and net profit."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get total income
    cursor.execute("SELECT COALESCE(SUM(amount), 0) as total FROM finance WHERE type = 'Income'")
    total_income = cursor.fetchone()["total"]
    
    # Get total expenses
    cursor.execute("SELECT COALESCE(SUM(amount), 0) as total FROM finance WHERE type = 'Expense'")
    total_expense = cursor.fetchone()["total"]
    
    conn.close()
    
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": total_income - total_expense
    }


@app.get("/api/finance")
async def get_finance_transactions(type: str = "", date: str = "", month: str = ""):
    """Get all finance transactions with optional filters."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build query with filters
    query = "SELECT id, date, type, amount, notes FROM finance WHERE 1=1"
    params = []
    
    if type:
        query += " AND type = ?"
        params.append(type)
    
    if date:
        query += " AND date = ?"
        params.append(date)
    elif month:
        # Filter by month (YYYY-MM format)
        query += " AND strftime('%Y-%m', date) = ?"
        params.append(month)
    
    query += " ORDER BY date DESC, id DESC"
    
    cursor.execute(query, params)
    transactions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return transactions


@app.post("/api/finance")
async def create_finance_transaction(request: Request):
    """Add a manual finance transaction."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()

    transaction_type = data.get("type")
    if transaction_type not in ["Income", "Expense"]:
        raise HTTPException(status_code=400, detail="Type must be 'Income' or 'Expense'")

    # Robustly coerce amount to float and validate
    raw_amount = data.get("amount", 0)
    try:
        amount = float(raw_amount)
    except Exception:
        raise HTTPException(status_code=400, detail="Amount must be a numeric value")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    conn = get_connection()
    cursor = conn.cursor()
    transaction_date = data.get("date") or date.today().isoformat()

    try:
        cursor.execute("""
            INSERT INTO finance (date, type, amount, notes)
            VALUES (?, ?, ?, ?)
        """, (
            transaction_date,
            transaction_type,
            amount,
            data.get("notes", "")
        ))

        transaction_id = cursor.lastrowid
        conn.commit()
        return {"success": True, "id": transaction_id, "message": "Transaction added successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.delete("/api/finance/{transaction_id}")
async def delete_finance_transaction(transaction_id: int):
    """Delete a finance transaction."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if transaction exists
    cursor.execute("SELECT id FROM finance WHERE id = ?", (transaction_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    cursor.execute("DELETE FROM finance WHERE id = ?", (transaction_id,))
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Transaction deleted successfully"}


# ============ Settings Page & Backup Routes ============

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Serve the settings page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "settings.html", {
        "request": request,
        "user": session["user"]
    })


@app.get("/api/settings/info")
async def get_system_info():
    """Get system information for settings page."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get counts
    cursor.execute("SELECT COUNT(*) as count FROM patients")
    total_patients = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM visits")
    total_visits = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM inventory")
    inventory_count = cursor.fetchone()["count"]
    
    conn.close()
    
    # Get database size
    from database import DB_PATH
    db_size = "--"
    if DB_PATH.exists():
        size_bytes = DB_PATH.stat().st_size
        if size_bytes < 1024:
            db_size = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            db_size = f"{size_bytes / 1024:.1f} KB"
        else:
            db_size = f"{size_bytes / (1024 * 1024):.1f} MB"
    
    # Check for last backup
    last_backup = None
    desktop = Path.home() / "Desktop" / "Backups"
    if desktop.exists():
        backups = list(desktop.glob("backup_clinic_*.db"))
        if backups:
            latest = max(backups, key=lambda p: p.stat().st_mtime)
            last_backup = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    
    return {
        "db_size": db_size,
        "total_patients": total_patients,
        "total_visits": total_visits,
        "inventory_count": inventory_count,
        "last_backup": last_backup
    }


@app.post("/api/settings/backup")
async def create_backup():
    """Create a backup of the database."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from database import DB_PATH
    
    try:
        # Create Backups folder on Desktop
        desktop = Path.home() / "Desktop"
        backup_folder = desktop / "Backups"
        backup_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with current date
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backup_clinic_{current_date}.db"
        backup_path = backup_folder / backup_filename
        
        # Copy the database file
        if not DB_PATH.exists():
            raise HTTPException(status_code=404, detail="Database file not found")
        
        shutil.copy2(DB_PATH, backup_path)
        
        return {
            "success": True,
            "message": "Data safely backed up!",
            "backup_path": str(backup_path)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@app.get("/api/settings/backups")
async def list_backups():
    """List available backup files."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    desktop = Path.home() / "Desktop" / "Backups"
    backups = []
    
    if desktop.exists():
        for backup_file in sorted(desktop.glob("backup_clinic_*.db"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": f"{stat.st_size / 1024:.1f} KB",
                "date": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    
    return backups


@app.post("/api/settings/restore")
async def restore_backup(request: Request):
    """Restore database from a backup file."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from database import DB_PATH
    
    data = await request.json()
    backup_path = data.get("backup_path")
    
    if not backup_path:
        raise HTTPException(status_code=400, detail="No backup file specified")
    
    backup_file = Path(backup_path)
    
    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")
    
    try:
        # Create a safety backup before restoring
        safety_backup = DB_PATH.parent / f"pre_restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, safety_backup)
        
        # Restore the backup
        shutil.copy2(backup_file, DB_PATH)
        
        return {
            "success": True,
            "message": "Database restored successfully! Please restart the app.",
            "safety_backup": str(safety_backup)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@app.get("/api/settings/restore-prompt")
async def prompt_restore_dialog():
    """Open a native file dialog (desktop mode) to pick a backup file and return its path.
    This is intended for desktop/wrapped deployments (pywebview/tkinter)."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Use tkinter filedialog to prompt user for a file path
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        filetypes = [("Database files", "*.db *.sqlite *.sql"), ("All files", "*")]
        path = filedialog.askopenfilename(title="Select backup file to restore", filetypes=filetypes)
        root.destroy()

        if not path:
            return {"selected": False, "path": ""}

        return {"selected": True, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file dialog: {str(e)}")


# ============ Prescription Routes ============


@app.get("/prescription-form", response_class=HTMLResponse)
async def prescription_form_page(request: Request):
    """Serve the prescription capture form."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "prescription_form.html", {
        "request": request,
        "user": session.get("user")
    })


@app.post("/api/print_prescription")
async def print_prescription_form(request: Request):
    """Generate a formatted prescription PDF from captured form data."""
    try:
        content_type = request.headers.get("content-type", "")
        logging.debug(f"/api/print_prescription called. Content-Type: {content_type}")

        if "application/json" in content_type:
            raw_data = await request.json()
            logging.debug(f"Received JSON payload: {raw_data}")
        else:
            form_data = await request.form()
            logging.debug(f"Received form payload keys: {list(form_data.keys())}")
            if "payload" in form_data:
                try:
                    raw_data = json.loads(form_data["payload"])
                except Exception:
                    raw_data = dict(form_data)
            else:
                raw_data = dict(form_data)
            logging.debug(f"Parsed raw_data: {raw_data}")

        # Validate payload
        payload = PrescriptionPrintRequest.model_validate(raw_data)
        logging.info(f"Generating prescription PDF for: {payload.pt_name if hasattr(payload, 'pt_name') else payload}")

        file_path = generate_prescription_form_pdf(payload.model_dump())
        logging.info(f"Prescription PDF generated at: {file_path}")
        # If running on Windows locally, try to open the PDF using the default system viewer
        try:
            if os.name == 'nt' and Path(file_path).exists():
                logging.debug(f"Opening PDF with os.startfile: {file_path}")
                try:
                    os.startfile(file_path)
                except Exception as _e:
                    logging.exception("os.startfile failed to open PDF")
        except Exception:
            # Protect against any unexpected errors here
            logging.exception('Error while attempting to auto-open PDF')

        return FileResponse(file_path, media_type="application/pdf", filename=Path(file_path).name)
    except Exception as e:
        logging.exception("Failed to generate prescription PDF")
        return JSONResponse(status_code=500, content={"success": False, "detail": f"Failed to generate prescription PDF: {str(e)}"})

@app.get("/prescription/{visit_id}/print")
async def print_prescription(visit_id: int):
    """Generate the prescription form PDF from a visit."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                v.id, v.date, v.vitals_bp, v.vitals_weight, v.vitals_temp, v.vitals_bsr,
                v.vitals_spo2, v.vitals_heart_rate, v.presenting_complaint, v.differentials,
                v.treatment_plan,
                p.id as patient_id, p.name as patient_name, p.age, p.gender, p.contact, p.height_cm, p.weight_kg, p.bmi
            FROM visits v
            JOIN patients p ON v.patient_id = p.id
            WHERE v.id = ?
        """, (visit_id,))
        visit = cursor.fetchone()

        if not visit:
            conn.close()
            raise HTTPException(status_code=404, detail="Visit not found")

        # Convert sqlite Row to dict for .get() access
        visit = dict(visit)

        cursor.execute("""
            SELECT medicine_name, dosage, duration, quantity, price, inventory_id
            FROM prescriptions
            WHERE visit_id = ?
            ORDER BY id
        """, (visit_id,))
        medicines = [dict(row) for row in cursor.fetchall()]
        conn.close()

        vitals_weight = visit.get("vitals_weight")
        patient_height = visit.get("height_cm")
        patient_weight = visit.get("weight_kg")
        patient_bmi = visit.get("bmi")

        # Build ht/wt string preferring visit vitals, then patient defaults
        if vitals_weight:
            ht_wt_str = f"Weight: {vitals_weight} kg"
        elif patient_height or patient_weight:
            ht_wt_str = f"{patient_height or '-'} cm / {patient_weight or '-'} kg"
        else:
            ht_wt_str = ""

        # Determine BMI: prefer patient stored BMI; if missing compute from patient height/weight when possible
        bmi_str = ""
        try:
            if patient_bmi:
                bmi_str = str(patient_bmi)
            elif patient_height and patient_weight:
                h_m = float(patient_height) / 100.0
                bmi_calc = float(patient_weight) / (h_m * h_m) if h_m > 0 else None
                bmi_str = f"{bmi_calc:.1f}" if bmi_calc else ""
        except Exception:
            bmi_str = ""

        payload = {
            "patient_id": visit.get("patient_id", None),
            "pt_name": visit.get("patient_name", ""),
            "age": str(visit.get("age", "")),
            "sex": visit.get("gender", "") or "",
            "contact": visit.get("contact", "") or "",
            "date": str(visit.get("date", "") or ""),
            "bp": visit.get("vitals_bp", "") or "",
            "hr": visit.get("vitals_heart_rate", "") or "",
            "so2": visit.get("vitals_spo2", "") or "",
            "rr": "",
            "temp": str(visit.get("vitals_temp", "") or ""),
            "height_cm": str(patient_height or "") if patient_height else "",
            "weight_kg": str(vitals_weight or patient_weight or "") if (vitals_weight or patient_weight) else "",
            "ht_wt": ht_wt_str,
            "bmi": bmi_str,
            "rbs": visit.get("vitals_bsr", "") or "",
            "comorbs": visit.get("past_medical_hx", "") or "",
            "presenting_complaint": visit.get("presenting_complaint", "") or "",
            "medical_examination": visit.get("examination", "") or "",
            "investigation_advised": visit.get("treatment_plan", "") or "",
            "provisional_diagnosis": visit.get("differentials", "") or "",
            "special_note": "",
            "medicines": medicines,
            "rx": "\n".join(
                f"{index + 1}. {med.get('medicine_name', '')} - {med.get('dosage', '')} ({med.get('quantity', '')}) {med.get('duration', '')}".strip()
                for index, med in enumerate(medicines)
            ),
            "advice": visit.get("treatment_plan", "") or "",
            "include_clinical_sections": True,
        }

        file_path = generate_prescription_form_pdf(payload)
        if os.name == 'nt' and Path(file_path).exists():
            try:
                os.startfile(file_path)
            except Exception:
                logging.exception("os.startfile failed to open PDF")

        return {
            "success": True,
            "message": "Prescription form opened for printing",
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate prescription form: {str(e)}")


@app.post("/api/send-whatsapp")
async def send_whatsapp_message(request: Request):
    """Open WhatsApp with pre-filled message in system browser."""
    import webbrowser
    
    data = await request.json()
    phone = data.get("phone", "")
    message = data.get("message", "")
    
    if not phone:
        return {"success": False, "error": "No phone number provided"}
    
    # Clean phone number
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Handle Pakistan number format
    if phone.startswith("0"):
        phone = "92" + phone[1:]
    if not phone.startswith("92") and not phone.startswith("+92"):
        phone = "92" + phone
    phone = phone.replace("+", "")
    
    # Create WhatsApp URL
    from urllib.parse import quote
    encoded_message = quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
    
    # Open in system browser
    try:
        webbrowser.open(whatsapp_url)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/visits/{visit_id}/prescriptions")
async def get_visit_prescriptions(visit_id: int):
    """Get prescriptions for a specific visit."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT medicine_name, dosage, duration, quantity, price, inventory_id
        FROM prescriptions
        WHERE visit_id = ?
    """, (visit_id,))
    
    prescriptions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return prescriptions


@app.get("/api/prescription/{visit_id}")
async def get_prescription_data(visit_id: int):
    """Get prescription data for a visit."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            v.id, v.date, v.presenting_complaint, v.differentials, 
            v.vitals_bp, v.vitals_weight, v.vitals_temp, v.vitals_bsr, v.vitals_spo2, v.vitals_heart_rate,
            v.signs_symptoms, v.history_presenting_illness, v.past_medical_hx, v.family_history,
            v.examination, v.treatment_plan, v.lab_report_path,
            p.id as patient_id, p.name as patient_name, p.age, p.contact,
            p.height_cm as height_cm, p.weight_kg as patient_weight_kg, p.bmi as patient_bmi
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
    """, (visit_id,))
    
    visit = cursor.fetchone()
    conn.close()
    
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    
    return dict(visit)


@app.put("/api/visits/{visit_id}")
async def update_visit(visit_id: int, visit: VisitUpdate):
    """Update an existing visit."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, patient_id, date FROM visits WHERE id = ?", (visit_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Visit not found")

    try:
        cursor.execute("""
            UPDATE visits
            SET vitals_bp = ?, vitals_weight = ?, vitals_temp = ?, vitals_bsr = ?,
                vitals_spo2 = ?, vitals_heart_rate = ?, presenting_complaint = ?, signs_symptoms = ?,
                history_presenting_illness = ?, past_medical_hx = ?, family_history = ?, examination = ?,
                differentials = ?, treatment_plan = ?, lab_report_path = ?
            WHERE id = ?
        """, (
            visit.vitals_bp,
            visit.vitals_weight,
            visit.vitals_temp,
            visit.vitals_bsr,
            visit.vitals_spo2,
            visit.vitals_heart_rate,
            visit.presenting_complaint,
            visit.signs_symptoms,
            visit.history_presenting_illness,
            visit.past_medical_hx,
            visit.family_history,
            visit.examination,
            visit.differentials,
            visit.treatment_plan,
            visit.lab_report_path,
            visit_id,
        ))

        # If weight/bsr/height/bmi provided on edit, update patient's stored vitals as well
        try:
            if visit.vitals_weight is not None or visit.vitals_bsr is not None or getattr(visit, 'vitals_height_cm', None) is not None or getattr(visit, 'vitals_bmi', None) is not None:
                cursor.execute("SELECT height_cm FROM patients WHERE id = ?", (existing["patient_id"],))
                row = cursor.fetchone()
                # Use COALESCE to preserve existing values when None is provided
                cursor.execute(
                    "UPDATE patients SET height_cm = COALESCE(?, height_cm), weight_kg = COALESCE(?, weight_kg), bmi = COALESCE(?, bmi), bsr = COALESCE(?, bsr), modified_at = datetime('now') WHERE id = ?",
                    (getattr(visit, 'vitals_height_cm', None), visit.vitals_weight, getattr(visit, 'vitals_bmi', None), visit.vitals_bsr, existing["patient_id"])
                )
            else:
                cursor.execute("UPDATE patients SET modified_at = datetime('now') WHERE id = ?", (existing["patient_id"],))
        except Exception:
            cursor.execute("UPDATE patients SET modified_at = datetime('now') WHERE id = ?", (existing["patient_id"],))
        # If medicines provided in update, replace prescriptions for this visit
        if getattr(visit, 'medicines', None):
            try:
                # 1) Restock inventory from previous prescriptions (if any)
                cursor.execute("SELECT inventory_id, quantity FROM prescriptions WHERE visit_id = ?", (visit_id,))
                old_pres = cursor.fetchall()
                for op in old_pres:
                    inv_id = op["inventory_id"] if "inventory_id" in op.keys() else op[0]
                    qty = op["quantity"] if "quantity" in op.keys() else op[1]
                    if inv_id:
                        cursor.execute("UPDATE inventory SET stock = stock + ? WHERE id = ?", (qty, inv_id))

                # 2) Remove old prescriptions
                cursor.execute("DELETE FROM prescriptions WHERE visit_id = ?", (visit_id,))

                # 3) Insert new prescriptions and deduct inventory where applicable
                for med in visit.medicines:
                    inv_id = getattr(med, 'inventory_id', None)
                    item = None
                    if inv_id is not None:
                        cursor.execute("SELECT stock, brand_name FROM inventory WHERE id = ?", (inv_id,))
                        item = cursor.fetchone()
                        if not item:
                            conn.rollback()
                            raise HTTPException(status_code=400, detail=f"Inventory item {inv_id} not found")
                        cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (med.quantity, inv_id))

                    med_name = (med.medicine_name or (item["brand_name"] if item else None) or f"Medicine {inv_id or ''}").strip() or 'Medicine'
                    dosage = med.dosage or 'As directed'
                    qty = med.quantity or 1
                    price = med.price or 0.0
                    duration_val = getattr(med, 'duration', None) or (f"{getattr(med, 'freq_days', '')} days" if getattr(med, 'freq_days', None) else '7 days')

                    cursor.execute("""
                        INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price, inventory_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (visit_id, med_name, dosage, duration_val, qty, price, inv_id))
            except HTTPException:
                raise
            except Exception:
                conn.rollback()
                raise

        conn.commit()
        return {"success": True, "message": "Visit updated successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/visits/{visit_id}/lab-report")
async def upload_visit_lab_report(visit_id: int, file: UploadFile = File(...)):
    """Upload lab report image for a visit. Useful during registration and editing."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, date FROM visits WHERE id = ?", (visit_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Visit not found")

    allowed_ext = {".png", ".jpg", ".jpeg", ".webp"}
    original_name = file.filename or "lab_report"
    ext = Path(original_name).suffix.lower()
    if ext not in allowed_ext:
        conn.close()
        raise HTTPException(status_code=400, detail="Only PNG/JPG/JPEG/WEBP files are allowed")

    upload_dir = STATIC_DIR / "uploads" / "lab_reports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"visit_{visit_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    target = upload_dir / safe_name

    try:
        content = await file.read()
        with open(target, "wb") as out:
            out.write(content)

        relative_path = f"/static/uploads/lab_reports/{safe_name}"
        cursor.execute("UPDATE visits SET lab_report_path = ? WHERE id = ?", (relative_path, visit_id))
        conn.commit()

        return {"success": True, "path": relative_path}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload report: {str(e)}")
    finally:
        conn.close()


@app.get("/api/patients/{patient_id}/pdf")
async def generate_patient_record_pdf(patient_id: int):
    """Generate and open complete patient history PDF."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        file_path = generate_patient_history_pdf(patient_id)

        if os.name == 'nt' and Path(file_path).exists():
            try:
                os.startfile(file_path)
            except Exception:
                logging.exception("os.startfile failed to open patient history PDF")

        return {
            "success": True,
            "message": "Patient history PDF opened",
            "file_path": str(file_path)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


# ============ PyWebView Desktop Launcher ============


def get_free_port() -> int:
    """Ask the OS for a free localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def start_server(port: int):
    """Start the FastAPI server."""
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def wait_for_server(url: str, timeout_seconds: float = 10.0) -> None:
    """Wait until the HTTP server responds or time out."""
    from urllib.request import urlopen
    from urllib.error import URLError

    deadline = datetime.now().timestamp() + timeout_seconds
    while datetime.now().timestamp() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except URLError:
            pass
        except Exception:
            pass

    raise RuntimeError(f"Server did not become ready at {url}")


if __name__ == "__main__":
    # Initialize database
    init_database()

    port = get_free_port()
    server_url = f"http://127.0.0.1:{port}"
    # Write the chosen port to a file so external helpers can locate the server
    try:
        with open('server_port.txt', 'w', encoding='utf-8') as pf:
            pf.write(str(port))
    except Exception:
        pass
    
    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()
    
    # Wait until the server is actually reachable before opening the desktop window
    wait_for_server(server_url)

    icon_path = ensure_windows_icon_path()
    
    # Create and start PyWebView window with native OS controls
    window = webview.create_window(
        title="DrKhan System",
        url=server_url,
        background_color="#121212",
        fullscreen=False,
        frameless=False,
        resizable=True,
        min_size=(1100, 720)
    )

    def focus_window():
        try:
            # Some pywebview builds expose focus as a boolean/property instead of a callable.
            # Guard the call and fallback to bring_to_front on the first window if available.
            focus_fn = getattr(window, 'focus', None)
            if callable(focus_fn):
                focus_fn()
                return

            # Fallback: try bring_to_front on webview.windows[0]
            try:
                w0 = None
                if hasattr(webview, 'windows') and webview.windows:
                    w0 = webview.windows[0]
                elif hasattr(webview, 'get_windows'):
                    wlist = webview.get_windows()
                    if wlist:
                        w0 = wlist[0]

                if w0:
                    b = getattr(w0, 'bring_to_front', None)
                    if callable(b):
                        b()
            except Exception:
                # swallow fallback errors
                pass

        except Exception:
            logging.exception("Failed to focus PyWebView window")

    if icon_path:
        webview.start(focus_window, icon=icon_path)
    else:
        webview.start(focus_window)


@app.post("/api/dev/add-test-data")
async def api_add_test_data():
    """Developer-only endpoint to populate random test data. Requires login."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        add_test_data()
        return {"success": True, "message": "Test data added (or already exists)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
