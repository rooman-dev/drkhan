# -*- mode: python ; coding: utf-8 -*-
"""
DrKhan Clinic Management System - PyInstaller Spec File
"""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Get the project directory
project_dir = os.path.dirname(os.path.abspath(SPEC))

# Collect all fpdf files
fpdf_datas, fpdf_binaries, fpdf_hiddenimports = collect_all('fpdf')

# Collect gi (PyGObject) for GTK
gi_datas, gi_binaries, gi_hiddenimports = collect_all('gi')

# Combine all
all_datas = fpdf_datas + gi_datas
all_binaries = fpdf_binaries + gi_binaries
all_hiddenimports = fpdf_hiddenimports + gi_hiddenimports

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=all_binaries,
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ] + all_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'webview',
        'webview.platforms.gtk',
        'jinja2',
        'jinja2.ext',
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'pydantic',
        'database',
        'prescription',
        'gi',
        'gi.repository',
        'gi.repository.Gtk',
        'gi.repository.GLib',
        'gi.repository.Gdk',
        'gi.repository.WebKit2',
    ] + all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DrKhan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/logo.png' if os.path.exists('static/logo.png') else None,
)
