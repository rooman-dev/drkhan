# -*- mode: python ; coding: utf-8 -*-
"""
DrKhan Clinic Management System - Windows PyInstaller Spec File
Run on Windows: python -m PyInstaller build_windows.spec --clean --noconfirm
"""

import os
from pathlib import Path

block_cipher = None

# Get the project directory
project_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ],
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
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'webview.platforms.winforms',
        'jinja2',
        'jinja2.ext',
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'pydantic',
        'fpdf',
        'fpdf.fpdf',
        'fpdf.drawing',
        'fpdf.enums',
        'fpdf.fonts',
        'fpdf.graphics_state',
        'fpdf.html',
        'fpdf.image_parsing',
        'fpdf.line_break',
        'fpdf.outline',
        'fpdf.output',
        'fpdf.recorder',
        'fpdf.structure_tree',
        'fpdf.svg',
        'fpdf.syntax',
        'fpdf.table',
        'fpdf.text_region',
        'fpdf.util',
        'clr_loader',
        'pythonnet',
        'database',
        'prescription',
    ],
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
    icon='static/logo.ico' if os.path.exists('static/logo.ico') else None,
)
