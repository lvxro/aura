"""Line icons drawn for the app (SVG on a 24 grid)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "power": '<path d="M12 3.5v8"/><path d="M7.2 6.6a7.5 7.5 0 1 0 9.6 0"/>',
    "settings": '<path d="M4 7h9"/><path d="M17 7h3"/><circle cx="15" cy="7" r="2"/>'
                '<path d="M4 17h3"/><path d="M11 17h9"/><circle cx="9" cy="17" r="2"/>',
    "chevron": '<path d="M7 10l5 5 5-5"/>',
    "sun": '<circle cx="12" cy="12" r="3.6"/><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2'
           'M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18"/>',
    "plus": '<path d="M12 5.5v13M5.5 12h13"/>',
    "check": '<path d="M5.5 12.5l4.2 4.2 8.8-9.4"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M15.6 15.6L20 20"/>',
    "music": '<path d="M9.5 17.5V6l9-2v11.5"/><circle cx="7" cy="17.5" r="2.5"/><circle cx="16" cy="15.5" r="2.5"/>',
    "screen": '<rect x="3.5" y="5" width="17" height="11.5" rx="2"/><path d="M9 20h6M12 16.5V20"/>',
    "more": '<circle cx="6" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>'
            '<circle cx="18" cy="12" r="1.2" fill="currentColor"/>',
    "bulb": '<path d="M8.5 14.5a6 6 0 1 1 7 0c-.6.5-1 1.200-1 2v.5h-5v-.5c0-.8-.4-1.500-1-2z"/><path d="M10 20h4"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/>',
    "play": '<path d="M8.5 6.5v11l9-5.500z" fill="currentColor"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.600l2 2.200h7.400a2 2 0 0 1 2 2v7.800a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
}


def svg(name: str, color: str, stroke: float = 1.9) -> bytes:
    body = _PATHS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" color="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    ).encode("utf-8")


_cache: dict = {}


def pixmap(name: str, size: int, color: QColor, dpr: float = 1.0, stroke: float = 1.9) -> QPixmap:
    key = (name, size, color.rgba(), round(dpr, 2), stroke)
    pm = _cache.get(key)
    if pm is None:
        px = max(1, int(round(size * dpr)))
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(svg(name, color.name(), stroke)))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(color.alphaF())
        renderer.render(p, QRectF(0, 0, px, px))
        p.end()
        pm.setDevicePixelRatio(dpr)
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = pm
    return pm


def draw(p: QPainter, name: str, cx: float, cy: float, size: int, color: QColor, stroke: float = 1.9):
    dpr = p.device().devicePixelRatioF() if p.device() else 1.0
    pm = pixmap(name, size, color, dpr, stroke)
    p.drawPixmap(QRectF(cx - size / 2, cy - size / 2, size, size).toRect().topLeft(), pm)
