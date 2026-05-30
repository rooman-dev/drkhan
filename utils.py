import sys
import tempfile
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


def ensure_windows_icon_path() -> str | None:
    """
    Return a valid Windows .ico path for PyWebView.

    PyWebView on Windows expects an actual .ico file. If the bundled ICO exists,
    it is used directly. Otherwise, we generate a temporary ICO from
    `static/logo.png` using Pillow.
    """
    bundled_ico = Path(resource_path("build/icon.ico"))
    if bundled_ico.exists():
        return str(bundled_ico)

    logo_png = Path(resource_path("static/logo.png"))
    if not logo_png.exists():
        return None

    try:
        from PIL import Image
    except Exception:
        return None

    temp_dir = Path(tempfile.gettempdir()) / "drkhan"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_ico = temp_dir / "pywebview_icon.ico"

    try:
        with Image.open(logo_png) as image:
            image.save(
                temp_ico,
                sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
            )
        return str(temp_ico)
    except Exception:
        return None


__all__ = ["resource_path", "ensure_windows_icon_path"]
