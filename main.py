"""
DrKhan Hospital Management System
Main Application Entry Point
"""

import uvicorn
import webview
import threading
import shutil
import os
from datetime import date, datetime
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

from database import init_database, get_connection, hash_password
from prescription import generate_prescription_pdf, generate_and_open_prescription

# Initialize FastAPI app
app = FastAPI(title="DrKhan Clinic", version="1.0.0")

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Simple session storage (in-memory for single user)
session = {"logged_in": False, "user": None}


# ============ Pydantic Models ============
class LoginRequest(BaseModel):
    username: str
    password: str


class PatientCreate(BaseModel):
    name: str
    age: int
    contact: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    marital_status: Optional[str] = None
    address: Optional[str] = None


class MedicineItem(BaseModel):
    inventory_id: int
    quantity: int
    dosage: Optional[str] = None
    price: float


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
    return templates.TemplateResponse("login.html", {"request": request})


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
    return templates.TemplateResponse("dashboard.html", {
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
            TIME(v.date) as time,
            v.presenting_complaint,
            p.name as patient_name
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE DATE(v.date) = ?
        ORDER BY v.date DESC
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


# ============ Patient Management Routes ============

@app.get("/patients", response_class=HTMLResponse)
async def patients_page(request: Request):
    """Serve the patients management page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "user": session["user"]
    })


@app.get("/api/patients")
async def get_patients(search: str = ""):
    """Get all patients with optional search."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if search:
        cursor.execute("""
            SELECT 
                p.id, p.name, p.age, p.contact, p.gender, p.address,
                (SELECT MAX(date) FROM visits WHERE patient_id = p.id) as last_visit
            FROM patients p
            WHERE p.name LIKE ? OR p.contact LIKE ? OR CAST(p.id AS TEXT) LIKE ? OR p.address LIKE ?
            ORDER BY p.name
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
            SELECT 
                p.id, p.name, p.age, p.contact, p.gender, p.address,
                (SELECT MAX(date) FROM visits WHERE patient_id = p.id) as last_visit
            FROM patients p
            ORDER BY p.id DESC
        """)
    
    patients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return patients


@app.post("/api/patients")
async def create_patient(patient: PatientCreate):
    """Create a new patient."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO patients (name, age, contact, gender, occupation, marital_status, address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (patient.name, patient.age, patient.contact, patient.gender, patient.occupation, patient.marital_status, patient.address))
    
    patient_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"success": True, "patient_id": patient_id, "message": "Patient created successfully"}


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
            examination, differentials, treatment_plan
        FROM visits
        WHERE patient_id = ?
        ORDER BY date DESC
    """, (patient_id,))
    
    visits = []
    for visit_row in cursor.fetchall():
        visit = dict(visit_row)
        # Get prescriptions for this visit
        cursor.execute("""
            SELECT medicine_name, dosage, duration, quantity, price
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
                differentials, treatment_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            visit.treatment_plan
        ))
        visit_id = cursor.lastrowid
        
        # 2. Process medicines - deduct from inventory and save prescriptions
        medicine_total = 0
        for med in visit.medicines:
            # Check stock availability
            cursor.execute("SELECT stock, brand_name FROM inventory WHERE id = ?", (med.inventory_id,))
            item = cursor.fetchone()
            
            if not item:
                conn.rollback()
                raise HTTPException(status_code=400, detail=f"Medicine not found: ID {med.inventory_id}")
            
            if item["stock"] < med.quantity:
                conn.rollback()
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient stock for {item['brand_name']}. Available: {item['stock']}"
                )
            
            # Deduct from inventory
            cursor.execute("""
                UPDATE inventory SET stock = stock - ? WHERE id = ?
            """, (med.quantity, med.inventory_id))
            
            # Save to prescriptions table
            cursor.execute("""
                INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (visit_id, item["brand_name"], med.dosage or "As directed", "7 days", med.quantity, med.price))
            
            medicine_total += med.price * med.quantity
        
        # 3. Calculate total bill (for display only, not added to finance)
        total_bill = medicine_total
        
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
    return templates.TemplateResponse("pharmacy.html", {
        "request": request,
        "user": session["user"]
    })


# ============ Finance Page & API Routes ============

@app.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request):
    """Serve the finance management page."""
    if not session.get("logged_in"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("finance.html", {
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
    
    amount = data.get("amount", 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO finance (date, type, amount, notes)
        VALUES (?, ?, ?, ?)
    """, (
        data.get("date"),
        transaction_type,
        amount,
        data.get("notes", "")
    ))
    
    transaction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"success": True, "id": transaction_id, "message": "Transaction added successfully"}


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
    return templates.TemplateResponse("settings.html", {
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


# ============ Prescription Routes ============

@app.get("/prescription/{visit_id}/print")
async def print_prescription(visit_id: int):
    """Generate and open prescription PDF for printing."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Generate and open PDF
        file_path = generate_and_open_prescription(visit_id)
        
        return {
            "success": True,
            "message": "Prescription opened for printing",
            "file_path": file_path
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate prescription: {str(e)}")


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
        SELECT medicine_name, dosage, duration, quantity, price
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
            v.vitals_bp, v.vitals_weight,
            p.id as patient_id, p.name as patient_name, p.age, p.contact
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
    """, (visit_id,))
    
    visit = cursor.fetchone()
    conn.close()
    
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    
    return dict(visit)


@app.get("/api/patients/{patient_id}/pdf")
async def generate_patient_record_pdf(patient_id: int):
    """Generate and open complete patient record PDF."""
    if not session.get("logged_in"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        from fpdf import FPDF
        import subprocess
        import platform
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get patient details
        cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        patient = cursor.fetchone()
        
        if not patient:
            conn.close()
            raise HTTPException(status_code=404, detail="Patient not found")
        
        patient = dict(patient)
        
        # Get all visits with prescriptions
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
            visit['prescriptions'] = [dict(p) for p in cursor.fetchall()]
            visits.append(visit)
        
        conn.close()
        
        # Create PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Header
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_text_color(0, 31, 63)
        pdf.cell(0, 12, 'DR.Khan Clinic', new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, 'Complete Patient Record', new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.ln(5)
        
        # Patient Information Section
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
        
        # Medical Records Section
        pdf.set_fill_color(0, 31, 63)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 10, f' Medical Records ({len(visits)} visits)', new_x='LMARGIN', new_y='NEXT', align='L', fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)
        
        for i, visit in enumerate(visits):
            # Check if we need a new page
            if pdf.get_y() > 230:
                pdf.add_page()
            
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(0, 31, 63)
            pdf.cell(0, 8, f"Visit {len(visits) - i}: {visit['date']}", new_x='LMARGIN', new_y='NEXT')
            
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(0, 0, 0)
            
            # Vitals
            vitals = []
            if visit.get('vitals_bp'): vitals.append(f"BP: {visit['vitals_bp']}")
            if visit.get('vitals_weight'): vitals.append(f"Weight: {visit['vitals_weight']}kg")
            if visit.get('vitals_temp'): vitals.append(f"Temp: {visit['vitals_temp']}F")
            if visit.get('vitals_bsr'): vitals.append(f"BSR: {visit['vitals_bsr']}")
            if visit.get('vitals_spo2'): vitals.append(f"SPO2: {visit['vitals_spo2']}")
            if visit.get('vitals_heart_rate'): vitals.append(f"HR: {visit['vitals_heart_rate']}")
            
            if vitals:
                pdf.cell(0, 6, "Vitals: " + " | ".join(vitals), new_x='LMARGIN', new_y='NEXT')
            
            if visit.get('presenting_complaint'):
                pdf.multi_cell(0, 5, f"Complaint: {visit['presenting_complaint']}")
            if visit.get('signs_symptoms'):
                pdf.multi_cell(0, 5, f"Signs & Symptoms: {visit['signs_symptoms']}")
            if visit.get('differentials'):
                pdf.multi_cell(0, 5, f"Differential Diagnosis: {visit['differentials']}")
            if visit.get('treatment_plan'):
                pdf.multi_cell(0, 5, f"Treatment Plan: {visit['treatment_plan']}")
            
            # Prescriptions
            if visit.get('prescriptions'):
                pdf.set_font('Helvetica', 'I', 10)
                pdf.cell(0, 6, "Prescription:", new_x='LMARGIN', new_y='NEXT')
                for rx in visit['prescriptions']:
                    rx_text = f"  - {rx['medicine_name']} (Qty: {rx['quantity']}) {rx.get('dosage', '')} {rx.get('duration', '')}"
                    pdf.cell(0, 5, rx_text, new_x='LMARGIN', new_y='NEXT')
                pdf.set_font('Helvetica', '', 10)
            
            pdf.ln(3)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
        
        # Save PDF
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        filename = f"patient_{patient_id}_record_{date.today().isoformat()}.pdf"
        file_path = output_dir / filename
        pdf.output(str(file_path))
        
        # Open PDF
        if platform.system() == 'Darwin':
            subprocess.run(['open', str(file_path)])
        elif platform.system() == 'Windows':
            os.startfile(str(file_path))
        else:
            subprocess.run(['xdg-open', str(file_path)])
        
        return {
            "success": True,
            "message": "Patient record PDF opened",
            "file_path": str(file_path)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


# ============ PyWebView Desktop Launcher ============

def start_server():
    """Start the FastAPI server."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    # Initialize database
    init_database()
    
    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Give the server a moment to start
    import time
    time.sleep(1)
    
    # Create and start PyWebView window in fullscreen
    webview.create_window(
        title="DrKhan System",
        url="http://127.0.0.1:8000",
        fullscreen=True,
        resizable=True,
        min_size=(800, 600)
    )
    webview.start()
