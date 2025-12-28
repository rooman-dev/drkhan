"""
DrKhan Hospital Management System
Database Initialization Module
"""

import sqlite3
import hashlib
import sys
import os
from pathlib import Path


def get_app_data_path():
    """Get persistent path for app data that works with PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if sys.platform == 'win32':
            # Windows: Use AppData/Local
            app_data = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
            data_dir = app_data / 'DrKhan'
        else:
            # Linux/Mac: Use home directory
            data_dir = Path.home() / '.drkhan'
        
        # Create directory if it doesn't exist
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "clinic.db"
    else:
        # Running from source - use current directory
        return Path(__file__).parent / "clinic.db"


# Database file path
DB_PATH = get_app_data_path()


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_connection():
    """Get optimized database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")
    # Optimize for speed
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_database():
    """Initialize the database with all required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL
        )
    """)

    # Create patients table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            contact TEXT,
            gender TEXT,
            occupation TEXT,
            marital_status TEXT,
            address TEXT
        )
    """)

    # Create visits table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            vitals_bp TEXT,
            vitals_weight REAL,
            vitals_temp REAL,
            vitals_bsr TEXT,
            vitals_spo2 TEXT,
            vitals_heart_rate TEXT,
            presenting_complaint TEXT,
            signs_symptoms TEXT,
            history_presenting_illness TEXT,
            past_medical_hx TEXT,
            family_history TEXT,
            examination TEXT,
            differentials TEXT,
            treatment_plan TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    """)

    # Create inventory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            formula TEXT,
            stock INTEGER DEFAULT 0,
            price REAL DEFAULT 0.0
        )
    """)

    # Create finance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS finance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT CHECK(type IN ('Income', 'Expense')) NOT NULL,
            amount REAL NOT NULL,
            notes TEXT
        )
    """)

    # Create prescriptions table (medicines prescribed per visit)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT,
            duration TEXT,
            quantity INTEGER DEFAULT 1,
            price REAL DEFAULT 0.0,
            FOREIGN KEY (visit_id) REFERENCES visits (id)
        )
    """)

    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_contact ON patients(contact)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_visits_patient_id ON visits(patient_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prescriptions_visit_id ON prescriptions(visit_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_finance_date ON finance(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_finance_type ON finance(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_brand_name ON inventory(brand_name)")

    conn.commit()

    # Check if users table is empty and insert default admin
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        default_password_hash = hash_password("123")
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name)
            VALUES (?, ?, ?)
        """, ("admin", default_password_hash, "Dr. Khan"))
        conn.commit()

    conn.close()
    print("Database Ready")


def add_test_data():
    """Add comprehensive test data for all tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if test data already exists
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] > 0:
        print("Test data already exists. Skipping...")
        conn.close()
        return
    
    from datetime import date, timedelta
    import random
    
    today = date.today()
    
    # ============ INVENTORY / MEDICINES ============
    medicines = [
        ("Panadol 500mg", "Paracetamol", 100, 15),
        ("Brufen 400mg", "Ibuprofen", 80, 20),
        ("Augmentin 625mg", "Amoxicillin+Clavulanic Acid", 50, 120),
        ("Flagyl 400mg", "Metronidazole", 60, 25),
        ("Risek 20mg", "Omeprazole", 90, 45),
        ("Zantac 150mg", "Ranitidine", 70, 35),
        ("Ponstan 500mg", "Mefenamic Acid", 85, 18),
        ("Gravinate", "Dimenhydrinate", 40, 22),
        ("Motilium 10mg", "Domperidone", 65, 28),
        ("Septran DS", "Co-trimoxazole", 45, 55),
        ("Ciprofloxacin 500mg", "Ciprofloxacin", 55, 65),
        ("Amoxil 500mg", "Amoxicillin", 75, 40),
        ("Calpol Syrup", "Paracetamol Syrup", 30, 85),
        ("Ventolin Inhaler", "Salbutamol", 25, 350),
        ("Claritin 10mg", "Loratadine", 60, 30),
        ("Zyrtec 10mg", "Cetirizine", 70, 25),
        ("Disprin", "Aspirin", 100, 10),
        ("Buscopan 10mg", "Hyoscine", 40, 35),
        ("Nexium 40mg", "Esomeprazole", 50, 85),
        ("Entamizole", "Metronidazole+Diloxanide", 55, 45),
        ("Flagyl Susp", "Metronidazole Suspension", 35, 65),
        ("Arinac Forte", "Paracetamol+Pseudoephedrine", 80, 30),
        ("Solpadeine", "Paracetamol+Caffeine+Codeine", 45, 55),
        ("Nurofen Plus", "Ibuprofen+Codeine", 35, 75),
        ("Norflox 400mg", "Norfloxacin", 50, 48),
    ]
    
    for med in medicines:
        cursor.execute("""
            INSERT INTO inventory (brand_name, formula, stock, price)
            VALUES (?, ?, ?, ?)
        """, med)
    
    # ============ PATIENTS ============
    patients_data = [
        ("Muhammad Ahmed", 35, "0301-2345678", "Male", "Engineer", "Married", "House 123, Block A, Lahore"),
        ("Fatima Bibi", 28, "0302-3456789", "Female", "Housewife", "Married", "Street 5, Model Town, Lahore"),
        ("Ali Hassan", 45, "0303-4567890", "Male", "Businessman", "Married", "45-B, DHA Phase 5, Lahore"),
        ("Ayesha Khan", 22, "0304-5678901", "Female", "Student", "Single", "Hostel 3, Punjab University"),
        ("Imran Malik", 52, "0305-6789012", "Male", "Retired", "Married", "House 78, Gulberg III, Lahore"),
        ("Zainab Fatima", 8, "0306-7890123", "Female", "Student", "Single", "Plot 12, Johar Town, Lahore"),
        ("Usman Tariq", 30, "0307-8901234", "Male", "Teacher", "Married", "Street 9, Township, Lahore"),
        ("Khadija Begum", 65, "0308-9012345", "Female", "Retired", "Widow", "House 56, Garden Town, Lahore"),
        ("Bilal Hussain", 40, "0309-0123456", "Male", "Doctor", "Married", "Medical Colony, Lahore"),
        ("Sana Amir", 25, "0310-1234567", "Female", "Nurse", "Single", "Nurses Hostel, Mayo Hospital"),
        ("Rashid Khan", 55, "0311-2345678", "Male", "Shopkeeper", "Married", "Anarkali Bazaar, Lahore"),
        ("Nadia Perveen", 32, "0312-3456789", "Female", "Accountant", "Married", "Flat 5, Cavalry Ground"),
        ("Hamza Ali", 18, "0313-4567890", "Male", "Student", "Single", "FC College Hostel, Lahore"),
        ("Mehwish Hayat", 38, "0314-5678901", "Female", "Designer", "Divorced", "Studio 8, MM Alam Road"),
        ("Tariq Mehmood", 48, "0315-6789012", "Male", "Contractor", "Married", "House 90, Valencia Town"),
        ("Amina Yousaf", 29, "0316-7890123", "Female", "Pharmacist", "Single", "Pharmacy Colony, Lahore"),
        ("Shahid Afridi", 42, "0317-8901234", "Male", "Sportsman", "Married", "Sports Complex, Lahore"),
        ("Hira Mani", 33, "0318-9012345", "Female", "Actress", "Married", "TV Colony, Lahore"),
        ("Waqar Ahmed", 60, "0319-0123456", "Male", "Farmer", "Married", "Village Kot, Sheikhupura"),
        ("Saima Noor", 50, "0320-1234567", "Female", "Tailor", "Married", "Shop 23, Liberty Market"),
    ]
    
    for patient in patients_data:
        cursor.execute("""
            INSERT INTO patients (name, age, contact, gender, occupation, marital_status, address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, patient)
    
    # ============ VISITS ============
    complaints = [
        ("Fever and body ache", "High grade fever, myalgia, fatigue", "Viral Fever, Dengue", "Rest, fluids, antipyretics"),
        ("Cough and cold", "Runny nose, sore throat, mild fever", "URTI, Common Cold", "Symptomatic treatment, steam inhalation"),
        ("Abdominal pain", "Epigastric pain, nausea, bloating", "Gastritis, Peptic Ulcer", "PPI, antacids, dietary modification"),
        ("Headache", "Throbbing headache, photophobia", "Migraine, Tension Headache", "Analgesics, rest in dark room"),
        ("Loose motions", "Watery stools, cramping, dehydration", "Acute Gastroenteritis, Food Poisoning", "ORS, antibiotics if needed"),
        ("Back pain", "Lower back pain, radiating to legs", "Lumbar Strain, Disc Problem", "Rest, analgesics, physiotherapy"),
        ("Skin rash", "Itchy red rash on arms", "Allergic Dermatitis, Eczema", "Antihistamines, topical steroids"),
        ("Shortness of breath", "Dyspnea on exertion, wheezing", "Asthma, COPD", "Bronchodilators, steroids"),
        ("Sore throat", "Pain on swallowing, fever", "Pharyngitis, Tonsillitis", "Antibiotics, gargles, rest"),
        ("Joint pain", "Multiple joint pain, stiffness", "Arthritis, Viral Arthralgia", "NSAIDs, rest, hot fomentation"),
    ]
    
    # Create visits for the last 30 days
    visit_id = 1
    for day_offset in range(30, -1, -1):
        visit_date = (today - timedelta(days=day_offset)).isoformat()
        
        # 1-4 visits per day
        num_visits = random.randint(1, 4)
        for _ in range(num_visits):
            patient_id = random.randint(1, 20)
            complaint = random.choice(complaints)
            
            bp = f"{random.randint(110, 140)}/{random.randint(70, 90)}"
            weight = round(random.uniform(45, 95), 1)
            temp = round(random.uniform(98, 102), 1)
            bsr = f"{random.randint(80, 140)} mg/dL"
            spo2 = f"{random.randint(95, 99)}%"
            hr = f"{random.randint(65, 100)} bpm"
            
            cursor.execute("""
                INSERT INTO visits (patient_id, date, vitals_bp, vitals_weight, vitals_temp,
                    vitals_bsr, vitals_spo2, vitals_heart_rate, presenting_complaint,
                    signs_symptoms, differentials, treatment_plan)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, visit_date, bp, weight, temp, bsr, spo2, hr,
                  complaint[0], complaint[1], complaint[2], complaint[3]))
            
            current_visit_id = cursor.lastrowid
            
            # Add 1-4 prescriptions per visit
            num_meds = random.randint(1, 4)
            used_meds = random.sample(range(1, 26), num_meds)
            
            dosages = ["1+1+1", "1+0+1", "0+0+1", "1+0+0", "1+1+1+1", "SOS"]
            durations = ["3 days", "5 days", "7 days", "10 days", "14 days"]
            
            for med_id in used_meds:
                cursor.execute("SELECT brand_name, price FROM inventory WHERE id = ?", (med_id,))
                med = cursor.fetchone()
                qty = random.randint(5, 20)
                
                cursor.execute("""
                    INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (current_visit_id, med[0], random.choice(dosages), random.choice(durations), qty, med[1]))
                
                # Deduct from inventory
                cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (qty, med_id))
            
            visit_id += 1
    
    # ============ FINANCE ============
    # Add income entries
    for day_offset in range(30, -1, -1):
        finance_date = (today - timedelta(days=day_offset)).isoformat()
        
        # Consultation fees (1-4 per day)
        num_consultations = random.randint(1, 4)
        for i in range(num_consultations):
            amount = random.choice([500, 700, 1000, 1500])
            cursor.execute("""
                INSERT INTO finance (date, type, amount, notes)
                VALUES (?, 'Income', ?, ?)
            """, (finance_date, amount, f"Consultation Fee - Patient #{random.randint(1, 20)}"))
    
    # Add expense entries
    expenses = [
        ("Electricity Bill", 5000, 8000),
        ("Water Bill", 500, 1000),
        ("Staff Salary", 25000, 35000),
        ("Medical Supplies", 3000, 8000),
        ("Rent", 50000, 50000),
        ("Internet Bill", 2000, 3000),
        ("Cleaning Supplies", 500, 1500),
        ("Printer Ink/Paper", 1000, 3000),
    ]
    
    for day_offset in [28, 25, 20, 15, 10, 5, 2, 0]:
        expense_date = (today - timedelta(days=day_offset)).isoformat()
        expense = random.choice(expenses)
        amount = random.randint(expense[1], expense[2])
        cursor.execute("""
            INSERT INTO finance (date, type, amount, notes)
            VALUES (?, 'Expense', ?, ?)
        """, (expense_date, amount, expense[0]))
    
    # Restock inventory with expenses
    for day_offset in [25, 15, 5]:
        restock_date = (today - timedelta(days=day_offset)).isoformat()
        restock_amount = random.randint(5000, 15000)
        cursor.execute("""
            INSERT INTO finance (date, type, amount, notes)
            VALUES (?, 'Expense', ?, ?)
        """, (restock_date, restock_amount, "Medicine Stock Purchase"))
        
        # Actually add stock
        for med_id in random.sample(range(1, 26), 10):
            cursor.execute("UPDATE inventory SET stock = stock + ? WHERE id = ?", 
                          (random.randint(20, 50), med_id))
    
    conn.commit()
    conn.close()
    print("Test data added successfully!")


if __name__ == "__main__":
    init_database()
    add_test_data()
