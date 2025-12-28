@echo off
REM DrKhan Clinic Management System - Windows Build Script
REM Run this script on a Windows machine to create the executable

echo ========================================
echo DrKhan Clinic - Windows Build Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
pip install --upgrade pip
pip install fastapi uvicorn jinja2 python-multipart pywebview fpdf2 pyinstaller pythonnet

echo [3/4] Building executable...
python -m PyInstaller build_windows.spec --clean --noconfirm

echo [4/4] Build complete!
echo.
echo ========================================
echo The executable is ready at: dist\DrKhan.exe
echo ========================================
echo.

REM Copy to a release folder
if not exist "release" mkdir release
copy dist\DrKhan.exe release\
echo.
echo Copied to release folder.
echo.
pause
