"""
Load deterministic dummy fixtures into a SQLite DB for end-to-end testing.
Usage:
    .\.venv\Scripts\python.exe load_fixtures.py --db test_clinic.db

This will add a few patients, visits and prescriptions to exercise UI flows.
"""
import sqlite3
from pathlib import Path
import argparse
from datetime import date, timedelta


def load_fixtures(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure basic tables exist by calling init_database if available
    try:
        import database
        database.DB_PATH = db_path
        database.init_database()
    except Exception:
        pass

    # Insert predictable patients
    patients = [
        ("Test Patient One", 30, "0300-0000001", "Male", "Tester", "Single", "Test Address 1"),
        ("Test Patient Two", 45, "0300-0000002", "Female", "Engineer", "Married", "Test Address 2"),
        ("Test Patient Three", 10, "0300-0000003", "Female", "Student", "Single", "Test Address 3"),
    ]

    for p in patients:
        cur.execute(
            "INSERT INTO patients (name, age, contact, gender, occupation, marital_status, address, created_at, modified_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            p,
        )
    conn.commit()

    # Get inserted patient ids
    cur.execute("SELECT id FROM patients WHERE name LIKE 'Test Patient %' ORDER BY id")
    patient_ids = [r[0] for r in cur.fetchall()]

    # Ensure inventory has a few known meds
    meds = [
        ("FixturePanadol 500mg", "Paracetamol", 100, 15.0),
        ("FixtureBrufen 400mg", "Ibuprofen", 100, 20.0),
        ("FixtureAmoxil 500mg", "Amoxicillin", 100, 40.0),
    ]
    for m in meds:
        cur.execute("INSERT INTO inventory (brand_name, formula, stock, price) VALUES (?, ?, ?, ?)", m)
    conn.commit()

    # Prepare visits and prescriptions for each patient
    today = date.today()
    med_ids = [row[0] for row in cur.execute("SELECT id FROM inventory WHERE brand_name LIKE 'Fixture%'")]

    for i, pid in enumerate(patient_ids):
        # 3 visits per patient on successive days
        for j in range(3):
            vdate = (today - timedelta(days=(i*3 + j))).isoformat()
            bp = f"{120 + j}/{70 + j}"
            cur.execute(
                "INSERT INTO visits (patient_id, date, vitals_bp, vitals_weight, vitals_temp, vitals_spo2, vitals_heart_rate, presenting_complaint, examination, differentials, treatment_plan) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pid,
                    vdate,
                    bp,
                    70 + i + j,
                    98.6 + j * 0.1,
                    f"9{j+5}%",
                    f"7{j+0} bpm",
                    f"Fixture complaint {j+1}",
                    f"Fixture exam {j+1}",
                    f"Fixture diff {j+1}",
                    f"Fixture treatment {j+1}",
                ),
            )
            vid = cur.lastrowid

            # 1-3 medicines per visit, cycle through med_ids
            num_meds = ((i + j) % 3) + 1
            for k in range(num_meds):
                mid = med_ids[k % len(med_ids)]
                cur.execute("SELECT brand_name, price FROM inventory WHERE id = ?", (mid,))
                mrow = cur.fetchone()
                cur.execute(
                    "INSERT INTO prescriptions (visit_id, medicine_name, dosage, duration, quantity, price, inventory_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        vid,
                        mrow[0],
                        "1+0+1",
                        "3 days",
                        10 + k,
                        mrow[1],
                        mid,
                    ),
                )
                # decrement inventory stock a bit
                cur.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (5, mid))

    # Add a few finance entries
    cur.execute("INSERT INTO finance (date, type, amount, notes) VALUES (date('now'), 'Income', 500.0, 'Fixture consult')")
    cur.execute("INSERT INTO finance (date, type, amount, notes) VALUES (date('now'), 'Expense', 2000.0, 'Fixture supplies')")

    conn.commit()
    conn.close()
    print(f"Fixtures loaded into {db_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=str, default='test_clinic.db', help='Path to sqlite DB file')
    args = parser.parse_args()
    dbp = Path(args.db)
    if not dbp.exists():
        print(f"DB {dbp} does not exist. Creating via database.init_database() if available.")
    load_fixtures(dbp)
