# DrKhan Clinic Management System

A desktop Hospital Management System for single doctor clinics.

## Features
- Patient Registration & Management
- Visit/Consultation Records with Clinical Fields
- Prescription Generation (PDF)
- Pharmacy/Inventory Management
- Finance Tracking (Income/Expenses)
- WhatsApp Follow-up Messages
- Patient History with PDF Export
- Database Backup/Restore

## Building for Windows

### Prerequisites
1. Install Python 3.10 or later from [python.org](https://python.org)
2. Make sure Python is added to PATH during installation

### Quick Build
1. Copy all project files to a Windows machine
2. Double-click `build_windows.bat`
3. The executable will be created at `dist\DrKhan.exe`

### Manual Build
```batch
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Build executable
python -m PyInstaller build_windows.spec --clean --noconfirm
```

## Running the Application

### From Source
```bash
python main.py
```

### From Executable
- Windows: Double-click `DrKhan.exe`
- Linux: Run `./DrKhan`

## Default Login
- Username: `admin`
- Password: `123`

## Tech Stack
- **Backend**: Python FastAPI
- **Frontend**: HTML5 + Bootstrap 5 + Vanilla JS
- **Database**: SQLite
- **Desktop**: PyWebView
- **PDF**: fpdf2

## Currency
All amounts are in PKR (Rs.)

## Contact
DrKhan Clinic - +92 304 7501095
