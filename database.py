"""
DrKhan Hospital Management System
Database Initialization Module
"""

import sqlite3
import hashlib
from pathlib import Path

# Database file path
DB_PATH = Path(__file__).parent / "clinic.db"


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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


if __name__ == "__main__":
    init_database()
