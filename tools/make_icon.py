"""Draws the app icon with the app's own code and saves it as launcher/aura.ico.

Usage:  python tools/make_icon.py
"""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

app = QApplication([])
from aura import appicon  # noqa: E402

images = []
for size in (256, 128, 64, 48, 32, 24, 16):
    pixmap = appicon.app_pixmap(size)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
out = os.path.join(ROOT, "launcher", "aura.ico")
images[0].save(out, format="ICO", append_images=images[1:], sizes=[(i.width, i.height) for i in images])
print("wrote", os.path.relpath(out, ROOT), os.path.getsize(out), "bytes")
