"""App and tray icons, drawn on the fly."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient

from . import icons
from . import theme as T


def app_pixmap(size: int, color: QColor | None = None) -> QPixmap:
    color = color or QColor("#FFFFFF")
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#000000"))
    p.drawRoundedRect(r, size * 0.23, size * 0.23)
    if size >= 32:      # hairline so the black tile keeps its shape on a dark taskbar
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#303030"), max(1.0, size / 128)))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), size * 0.23, size * 0.23)
        p.setPen(Qt.PenStyle.NoPen)
    c = r.center()
    p.setClipRect(r)
    g = QRadialGradient(c, size * 0.52)
    g.setColorAt(0.0, T.with_alpha(color, 0.55))
    g.setColorAt(0.55, T.with_alpha(color, 0.16))
    g.setColorAt(1.0, T.with_alpha(color, 0.0))
    path_clip = QRectF(r)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(path_clip, size * 0.23, size * 0.23)
    rad = size * 0.27
    g2 = QRadialGradient(QPointF(c.x(), c.y() - rad * 0.25), rad * 1.3)
    g2.setColorAt(0.0, T.mix(color, QColor("#ffffff"), 0.75))
    g2.setColorAt(0.7, T.mix(color, QColor("#ffffff"), 0.12))
    g2.setColorAt(1.0, T.mix(color, QColor("#000000"), 0.16))
    p.setBrush(QBrush(g2))
    p.drawEllipse(c, rad, rad)
    if size >= 32:
        icons.draw(p, "power", c.x(), c.y(), int(rad * 1.05), QColor("#0A0A0A"), 2.0 if size >= 64 else 2.4)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(s))
    return icon


def tray_icon(color: QColor, on: bool, available: bool = True) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(s / 2, s / 2)
        rad = s * 0.40
        if on and available:
            g = QRadialGradient(QPointF(c.x(), c.y() - rad * 0.3), rad * 1.4)
            g.setColorAt(0.0, T.mix(color, QColor("#ffffff"), 0.6))
            g.setColorAt(1.0, color)
            p.setBrush(QBrush(g))
            p.setPen(QPen(T.with_alpha(QColor("#ffffff"), 0.85), max(1.0, s / 16)))
            p.drawEllipse(c, rad, rad)
        else:
            p.setBrush(QColor(18, 18, 18, 235))
            p.setPen(QPen(QColor("#C9C5D6") if available else QColor("#8A8698"), max(1.2, s / 11)))
            p.drawEllipse(c, rad, rad)
        p.end()
        icon.addPixmap(pm)
    return icon
