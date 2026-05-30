import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """
    Return absolute path to resource, works for dev and PyInstaller (_MEIPASS).

    Pass `relative_path` relative to the project root or the bundle layout,
    for example: 'static/logo.png' or 'assets/icon.ico'.
    """
    # When bundled by PyInstaller, files are extracted to _MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str((base / relative_path).resolve())


__all__ = ["resource_path"]
