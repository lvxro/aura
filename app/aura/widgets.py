"""Hand-drawn controls for Aura.

The look is monochrome: surfaces, text and controls are black, white and gray,
and state is shown by tonal inversion (a selected item turns white with black
text). The only color on screen comes from the light itself: the lamp, its
glow, and things that *are* colors (the wheel, swatches, scene chips).
"""

from __future__ import annotations

import colorsys
import math
import random

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFontMetrics, QImage, QLinearGradient,
                           QPainter, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from . import icons, wiz
from . import theme as T
from .i18n import t

AA = QPainter.RenderHint.Antialiasing
WHITE = QColor("#ffffff")
BLACK = QColor("#000000")


def _anim(owner, setter, duration=160, curve=QEasingCurve.Type.OutCubic):
    a = QVariantAnimation(owner)
    a.setDuration(duration)
    a.setEasingCurve(curve)
    a.valueChanged.connect(setter)
    return a


def _run(anim: QVariantAnimation, start: float, end: float):
    anim.stop()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.start()


def kfocus(w: QWidget) -> bool:
    """True if the widget has focus and got it from the keyboard (Tab)."""
    return w.hasFocus() and bool(w.property("kbd"))


def _focus_ring(p: QPainter, rect: QRectF, radius: float):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
    p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), radius + 3, radius + 3)


def _hairline(color: QColor | None = None, width: float = 1.0) -> QPen:
    return QPen(color or T.LINE, width)


class Themed(QWidget):
    """Widget that repaints when the light's color or the theme changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        T.theme().changed.connect(self.update)


# --------------------------------------------------------------------------
# Power button
# --------------------------------------------------------------------------
class Orb(QAbstractButton):
    """The lamp, drawn as a matrix of dots that light up in the light's color. It is the power button.

    The dots grow with the brightness, and they ignite from the centre outwards when the
    light turns on. The ring of dots around it is the brightness dial: it shows the level,
    and it can be dragged, clicked or scrolled to change it.
    """

    nudged = Signal(int)        # mouse wheel over the lamp: +1 / -1
    dialed = Signal(int)        # brightness picked on the ring, in percent
    D = 152                     # diameter of the lamp
    PITCH = 9.5                 # distance between dots
    CAP = 27                    # radius of the key in the middle
    RING = 60                   # dots on the dial
    RING_R = 23                 # how far the dial sits from the lamp
    SWEEP0, SWEEP = 135.0, 270.0  # the dial runs over the top and leaves a gap at the bottom

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 280)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._scale = 1.0
        self._pulse = 0.0
        self._zone = ""         # what the pointer is over: "lamp", "dial" or nothing
        self._dialing = False
        self._sa = _anim(self, self._set_scale, 140)
        self._pa = _anim(self, self._set_pulse, 420, QEasingCurve.Type.OutQuad)
        self.available = True
        T.theme().changed.connect(self.update)

    def _set_scale(self, v):
        self._scale = v
        self.update()

    def _set_pulse(self, v):
        self._pulse = v
        self.update()

    def pulse(self, strength: float = 1.0):
        _run(self._pa, max(self._pulse, strength), 0.0)

    # -- where things are
    def _polar(self, pos) -> tuple[float, float]:
        dx, dy = pos.x() - self.width() / 2, pos.y() - self.height() / 2
        return math.hypot(dx, dy), math.degrees(math.atan2(dy, dx)) % 360

    def zone_at(self, pos) -> str:
        dist, _ang = self._polar(pos)
        if dist <= self.D / 2 + 4:
            return "lamp"
        ring = self.D / 2 + self.RING_R
        if self.available and ring - 12 <= dist <= ring + 14:
            return "dial"
        return ""

    def value_at(self, pos) -> int:
        """The brightness the dial shows at that point."""
        _dist, ang = self._polar(pos)
        rel = (ang - self.SWEEP0) % 360
        if rel > self.SWEEP:                                  # in the gap: snap to the nearest end
            rel = self.SWEEP if rel < (self.SWEEP + 360) / 2 else 0.0
        return int(round(wiz.MIN_DIM + rel / self.SWEEP * (100 - wiz.MIN_DIM)))

    def dial_point(self, percent: float) -> QPointF:
        """Where a brightness sits on the dial."""
        frac = (percent - wiz.MIN_DIM) / (100 - wiz.MIN_DIM)
        ang = math.radians(self.SWEEP0 + self.SWEEP * max(0.0, min(1.0, frac)))
        r = self.D / 2 + self.RING_R
        return QPointF(self.width() / 2 + r * math.cos(ang), self.height() / 2 + r * math.sin(ang))

    def hitButton(self, pos):
        return self.zone_at(pos) == "lamp"

    def _set_zone(self, zone: str):
        if zone == self._zone:
            return
        self._zone = zone
        self.setCursor(Qt.CursorShape.PointingHandCursor if zone else Qt.CursorShape.ArrowCursor)
        if not self.isDown():
            _run(self._sa, self._scale, 1.035 if zone == "lamp" else 1.0)
        self.update()

    # -- pointer
    def leaveEvent(self, e):
        self._set_zone("")

    def mouseMoveEvent(self, e):
        if self._dialing:
            self.dialed.emit(self.value_at(e.position()))
            return
        self._set_zone(self.zone_at(e.position()))
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.zone_at(e.position()) == "dial":
            self._dialing = True
            self._set_zone("dial")
            self.dialed.emit(self.value_at(e.position()))
            return
        super().mousePressEvent(e)
        if self.isDown():
            _run(self._sa, self._scale, 0.955)

    def mouseReleaseEvent(self, e):
        if self._dialing:
            self._dialing = False
            self._set_zone(self.zone_at(e.position()))
            return
        super().mouseReleaseEvent(e)
        _run(self._sa, self._scale, 1.035 if self._zone == "lamp" else 1.0)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.nudged.emit(1 if d > 0 else -1)
            e.accept()

    # -- drawing
    def paintEvent(self, e):
        th = T.theme()
        p = QPainter(self)
        p.setRenderHint(AA)
        cx, cy = self.width() / 2, self.height() / 2
        c = QPointF(cx, cy)
        base_r = self.D / 2
        r = base_r * self._scale
        power = th.power if self.available else 0.0
        level = th.level
        glow = 0.35 + 0.65 * level
        L = th.light
        p.setPen(Qt.PenStyle.NoPen)

        # Halo hugging the lamp
        if power > 0.01:
            halo_r = base_r + 64 + 5 * self._pulse
            g = QRadialGradient(c, halo_r)
            a = (0.50 + 0.28 * self._pulse) * power * glow
            g.setColorAt(max(0.0, r / halo_r * 0.90), T.with_alpha(L, a))
            g.setColorAt(min(0.999, r / halo_r + 0.14), T.with_alpha(L, a * 0.34))
            g.setColorAt(1.0, T.with_alpha(L, 0.0))
            p.setBrush(QBrush(g))
            p.drawEllipse(c, halo_r, halo_r)

        # Brightness dial: a ring of dots, lit up to the current level, with a larger one as the handle
        n = self.RING
        lit = int(round(level * n)) if power > 0.01 else 0
        ring_r = base_r + self.RING_R
        active = self._zone == "dial" or self._dialing
        on_c = T.with_alpha(th.accent, 0.40 + 0.60 * power)
        off_c = T.with_alpha(WHITE, (0.30 if active else 0.17) if self.available else 0.08)
        for i in range(n):
            ang = math.radians(self.SWEEP0 + self.SWEEP * i / (n - 1))
            pt = QPointF(cx + math.cos(ang) * ring_r, cy + math.sin(ang) * ring_r)
            if i < lit:
                handle = i == lit - 1
                p.setBrush(on_c)
                rad = (4.6 if active else 3.8) if handle else 2.0
            else:
                p.setBrush(off_c)
                rad = 1.4
            p.drawEllipse(pt, rad, rad)

        # Lens: a dark disc, faintly lit from inside when the light is on
        lens = power * (0.55 + 0.35 * level)
        g = QRadialGradient(QPointF(cx, cy - r * 0.15), r * 1.1)
        g.setColorAt(0.0, T.mix(T.RAISED, T.mix(L, BLACK, 0.30), lens))
        g.setColorAt(1.0, T.mix(T.SURFACE, T.mix(L, BLACK, 0.62), lens))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)

        # The matrix. Each dot switches on as the power sweeps past it, centre first;
        # lit dots are larger towards the middle and grow with the brightness.
        pitch = self.PITCH * self._scale
        cap_r = self.CAP * self._scale
        steps = int(r / pitch) + 1
        idle = T.with_alpha(WHITE, 0.21 if self.available else 0.08)
        for j in range(-steps, steps + 1):
            for i in range(-steps, steps + 1):
                x, y = i * pitch, j * pitch
                d = math.hypot(x, y)
                if d > r - 5.5 or d < cap_r + 5.0:
                    continue
                f = d / r
                on = max(0.0, min(1.0, (power * 1.4 - f) / 0.4))
                full = (1.35 + 2.3 * level) * (1.0 - 0.52 * f ** 1.7) * self._scale
                rad = 1.15 + (full - 1.15) * on
                hot = T.mix(L, WHITE, 0.30 + 0.55 * (1.0 - f) * (0.5 + 0.5 * level))
                p.setBrush(T.mix(idle, hot, on) if on > 0 else idle)
                p.drawEllipse(QPointF(cx + x, cy + y), rad, rad)

        # Rim
        rim = T.mix(T.mix(T.LINE, WHITE, 0.14 if self._zone == "lamp" else 0.06), T.mix(L, WHITE, 0.50), power)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.with_alpha(rim, 0.95), 1.2))
        p.drawEllipse(c, r - 0.6, r - 0.6)

        # The key in the middle: hollow when off, solid when on (the same inversion as every selected item)
        p.setPen(QPen(T.mix(T.mix(T.LINE, WHITE, 0.22), WHITE, power), 1.2))
        p.setBrush(T.mix(T.SURFACE, T.mix(WHITE, L, 0.10), power))
        p.drawEllipse(c, cap_r, cap_r)
        ink = T.mix(T.MUTED if self.available else T.FAINT, T.INK, power)
        icons.draw(p, "power", cx, cy, int(30 * self._scale), ink, 1.9)

        if kfocus(self):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
            p.drawEllipse(c, r + 8, r + 8)
        p.end()


_grain: QPixmap | None = None


def grain() -> QPixmap:
    """A tile of fine noise. Laid over the glow, it hides gradient banding and adds texture."""
    global _grain
    if _grain is None:
        n = 128
        rng = random.Random(11)
        buf = bytearray(n * n * 4)
        for i in range(n * n):
            a = int(rng.random() ** 2 * 255)
            buf[4 * i] = buf[4 * i + 1] = buf[4 * i + 2] = a      # premultiplied white
            buf[4 * i + 3] = a
        img = QImage(bytes(buf), n, n, n * 4, QImage.Format.Format_ARGB32_Premultiplied)
        _grain = QPixmap.fromImage(img.copy())
    return _grain


class LampPanel(Themed):
    """Background of the left column: the light spills over the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.center = QPointF(160, 210)
        self.available = True

    def paintEvent(self, e):
        th = T.theme()
        p = QPainter(self)
        p.setRenderHint(AA)
        p.fillRect(self.rect(), T.NIGHT)
        power = th.power if self.available else 0.0
        if power > 0.01:
            level = 0.30 + 0.70 * th.level
            a = power * level
            R = 350
            g = QRadialGradient(self.center, R)
            L = th.light
            g.setColorAt(0.0, T.with_alpha(L, 0.52 * a))
            g.setColorAt(0.28, T.with_alpha(L, 0.27 * a))
            g.setColorAt(0.60, T.with_alpha(L, 0.09 * a))
            g.setColorAt(1.0, T.with_alpha(L, 0.0))
            p.fillRect(self.rect(), QBrush(g))
            p.setOpacity(0.055 * a)
            p.drawTiledPixmap(self.rect(), grain())
            p.setOpacity(1.0)
        # hairline between the lamp and the controls
        p.fillRect(QRectF(self.width() - 1, 0, 1, self.height()), T.LINE)
        p.end()


# --------------------------------------------------------------------------
# Sliders
# --------------------------------------------------------------------------
class _SliderBase(Themed):
    valueChanged = Signal(float)      # while dragging
    released = Signal()

    def __init__(self, lo=0.0, hi=1.0, value=0.0, step=None, parent=None):
        super().__init__(parent)
        self.lo, self.hi = float(lo), float(hi)
        self.step = step
        self._value = float(value)
        self._hover = False
        self._drag = False
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def value(self) -> float:
        return self._value

    def setValue(self, v: float, emit: bool = False):
        v = wiz.clamp(float(v), self.lo, self.hi)
        if self.step:
            v = round(v / self.step) * self.step
        if abs(v - self._value) < 1e-9:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def frac(self) -> float:
        return 0.0 if self.hi == self.lo else (self._value - self.lo) / (self.hi - self.lo)

    def _track(self) -> tuple[float, float]:
        """(start x, end x) of the usable travel."""
        return 0.0, float(self.width())

    def _set_from_x(self, x: float):
        x0, x1 = self._track()
        f = wiz.clamp((x - x0) / max(1.0, x1 - x0), 0.0, 1.0)
        self.setValue(self.lo + f * (self.hi - self.lo), emit=True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._set_from_x(e.position().x())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._set_from_x(e.position().x())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.released.emit()
            self.update()

    def nudge(self, direction: int):
        unit = max(self.step or 0, (self.hi - self.lo) / 20)
        self.setValue(self._value + (unit if direction > 0 else -unit), emit=True)
        self.released.emit()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.nudge(1 if d > 0 else -1)
            e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self.nudge(1)
        elif e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self.nudge(-1)
        else:
            super().keyPressEvent(e)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def focusInEvent(self, e):
        self.update()

    def focusOutEvent(self, e):
        self.update()


class BrightnessSlider(_SliderBase):
    """Segmented brightness bar with its label and value on top."""

    SEGMENTS = 32
    BAR_H = 26

    def __init__(self, title="Brightness", parent=None):
        super().__init__(wiz.MIN_DIM, 100, 100, step=1, parent=parent)
        self.title = title
        self.setFixedHeight(56)

    def _track(self):
        return 4.0, self.width() - 4.0

    def paintEvent(self, e):
        th = T.theme()
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h = self.width(), self.height()
        flags = Qt.AlignmentFlag.AlignVCenter
        p.setFont(T.font(11, mono=True))
        p.setPen(T.MUTED)
        p.drawText(QRectF(0, 0, w, 20), flags | Qt.AlignmentFlag.AlignLeft, self.title.lower())
        p.setFont(T.font(26, display=True))
        p.setPen(T.TEXT)
        p.drawText(QRectF(0, -5, w, 26), flags | Qt.AlignmentFlag.AlignRight, f"{int(round(self._value))}%")

        n = self.SEGMENTS
        gap = 3.0
        sw = (w - gap * (n - 1)) / n
        top = h - self.BAR_H
        lit = max(1, int(round(self._value / 100.0 * n)))
        on = T.mix(T.FAINT, th.accent, th.power)
        off = T.with_alpha(WHITE, 0.11)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            p.setBrush(on if i < lit else off)
            grow = 2.0 if (self._hover or self._drag) and i == lit - 1 else 0.0
            p.drawRoundedRect(QRectF(i * (sw + gap), top - grow, sw, self.BAR_H + grow), 2, 2)
        if kfocus(self):
            _focus_ring(p, QRectF(0, top, w, self.BAR_H).adjusted(1, 1, -1, -1), 4)
        p.end()


class Slider(_SliderBase):
    """Thin slider for settings, filled with the accent color."""

    def __init__(self, lo=0.0, hi=1.0, value=0.0, step=None, parent=None):
        super().__init__(lo, hi, value, step, parent)
        self.setFixedHeight(26)

    def _track(self):
        return 10.0, self.width() - 10.0

    def paintEvent(self, e):
        th = T.theme()
        p = QPainter(self)
        p.setRenderHint(AA)
        x0, x1 = self._track()
        cy = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.LINE)
        p.drawRoundedRect(QRectF(x0 - 2, cy - 2, x1 - x0 + 4, 4), 2, 2)
        x = x0 + self.frac() * (x1 - x0)
        p.setBrush(th.accent)
        p.drawRoundedRect(QRectF(x0 - 2, cy - 2, x - x0 + 2, 4), 2, 2)
        rad = 8.5 if (self._hover or self._drag) else 7.5
        p.setBrush(T.BG)
        p.drawEllipse(QPointF(x, cy), rad + 3, rad + 3)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(x, cy), rad, rad)
        if kfocus(self):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
            p.drawEllipse(QPointF(x, cy), rad + 5, rad + 5)
        p.end()


class TempSlider(_SliderBase):
    """From candlelight to daylight."""

    def __init__(self, parent=None):
        super().__init__(wiz.MIN_TEMP, wiz.MAX_TEMP, 2700, step=50, parent=parent)
        self.setFixedHeight(60)
        self.active = True

    def _track(self):
        return 30.0, self.width() - 30.0

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(0, 8, self.width(), self.height() - 16)
        rad = r.height() / 2
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        for i in range(9):
            f = i / 8
            g.setColorAt(f, QColor(*wiz.kelvin_to_rgb(self.lo + f * (self.hi - self.lo))))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.setOpacity(1.0 if self.active else 0.40)
        p.drawRoundedRect(r, rad, rad)
        p.setOpacity(1.0)
        x0, x1 = self._track()
        x = x0 + self.frac() * (x1 - x0)
        cy = self.height() / 2
        rr = 25 if (self._hover or self._drag) else 23.5
        p.setBrush(T.with_alpha(BLACK, 0.30))
        p.drawEllipse(QPointF(x, cy + 2), rr + 2, rr + 2)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(x, cy), rr, rr)
        p.setBrush(QColor(*wiz.kelvin_to_rgb(self._value)))
        p.drawEllipse(QPointF(x, cy), rr - 5, rr - 5)
        if kfocus(self):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
            p.drawEllipse(QPointF(x, cy), rr + 4, rr + 4)
        p.end()


# --------------------------------------------------------------------------
# Color wheel
# --------------------------------------------------------------------------
class ColorWheel(QWidget):
    colorChanged = Signal(int, int, int)
    released = Signal()
    CURVE = 1.15        # a little more room for pastels near the center

    def __init__(self, size=248, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.h, self.s = 0.08, 0.8
        self.active = True
        self._img: QPixmap | None = None
        self._img_key = None
        self._drag = False

    @property
    def radius(self) -> float:
        return self.width() / 2 - 14

    def set_rgb(self, r, g, b):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.001:
            self.h = h
        self.s = s
        self.update()

    def rgb(self) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, 1.0)
        return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))

    def _image(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self.width(), round(dpr, 2))
        if self._img is not None and self._img_key == key:
            return self._img
        n = int(round(self.width() * dpr))
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(AA)
        c = QPointF(n / 2, n / 2)
        R = self.radius * dpr
        # Hue around the circle. Qt's conical gradient runs counter-clockwise while
        # the picker measures clockwise (screen y grows downward), hence 1 - pos.
        hue = QConicalGradient(c, 0)
        for i in range(7):
            pos = i / 6
            hue.setColorAt(pos, QColor.fromHsvF((1.0 - pos) % 1.0, 1.0, 1.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hue))
        p.drawEllipse(c, R, R)
        # Saturation: white fading out from the center
        white = QRadialGradient(c, R)
        for i in range(17):
            pos = i / 16
            white.setColorAt(pos, T.with_alpha(WHITE, 1.0 - pos ** self.CURVE))
        p.setBrush(QBrush(white))
        p.drawEllipse(c, R + 0.5, R + 0.5)
        p.end()
        pm.setDevicePixelRatio(dpr)
        self._img, self._img_key = pm, key
        return pm

    def _pick(self, pos):
        c = self.width() / 2
        dx, dy = pos.x() - c, pos.y() - c
        dist = min(math.hypot(dx, dy), self.radius)
        self.h = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
        self.s = (dist / self.radius) ** self.CURVE
        self.active = True
        self.update()
        self.colorChanged.emit(*self.rgb())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._pick(e.position())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._pick(e.position())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.released.emit()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Left:
            self.h = (self.h - 1 / 72) % 1
        elif k == Qt.Key.Key_Right:
            self.h = (self.h + 1 / 72) % 1
        elif k == Qt.Key.Key_Up:
            self.s = min(1.0, self.s + 0.05)
        elif k == Qt.Key.Key_Down:
            self.s = max(0.0, self.s - 0.05)
        else:
            return super().keyPressEvent(e)
        self.active = True
        self.update()
        self.colorChanged.emit(*self.rgb())
        self.released.emit()

    def focusInEvent(self, e):
        self.update()

    def focusOutEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setOpacity(1.0 if self.active else 0.55)
        p.drawPixmap(QPointF(0, 0), self._image())
        p.setOpacity(1.0)
        if kfocus(self):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
            p.drawEllipse(c, self.radius + 5, self.radius + 5)
        if self.active:
            d = (self.s ** (1 / self.CURVE)) * self.radius
            ang = self.h * 2 * math.pi
            pt = QPointF(c.x() + math.cos(ang) * d, c.y() + math.sin(ang) * d)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.with_alpha(BLACK, 0.35))
            p.drawEllipse(QPointF(pt.x(), pt.y() + 1.5), 14.5, 14.5)
            p.setBrush(WHITE)
            p.drawEllipse(pt, 13, 13)
            p.setBrush(QColor(*self.rgb()))
            p.drawEllipse(pt, 9.5, 9.5)
        p.end()


# --------------------------------------------------------------------------
# Selectors
# --------------------------------------------------------------------------
class Segmented(Themed):
    """Tabs with a sliding indicator. The selected one is inverted: light pill, dark text."""

    changed = Signal(int)

    def __init__(self, labels, parent=None, height=40, compact=False):
        super().__init__(parent)
        self.labels = [str(l).lower() for l in labels]
        self.index = 0
        self._pos = 0.0
        self._hover = -1
        self.compact = compact
        self.setFixedHeight(height)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._a = _anim(self, self._set_pos, 220)

    def _set_pos(self, v):
        self._pos = v
        self.update()

    def setIndex(self, i: int, animate=True, emit=False):
        i = max(0, min(len(self.labels) - 1, i))
        if i == self.index and abs(self._pos - i) < 1e-3:
            return
        self.index = i
        if animate and self.isVisible():
            _run(self._a, self._pos, i)
        else:
            self._a.stop()
            self._pos = float(i)
            self.update()
        if emit:
            self.changed.emit(i)

    def _cell(self) -> float:
        return (self.width() - 8) / len(self.labels)

    def _at(self, x) -> int:
        return max(0, min(len(self.labels) - 1, int((x - 4) / self._cell())))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setIndex(self._at(e.position().x()), emit=True)

    def mouseMoveEvent(self, e):
        h = self._at(e.position().x())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Right:
            self.setIndex(self.index + 1, emit=True)
        elif e.key() == Qt.Key.Key_Left:
            self.setIndex(self.index - 1, emit=True)
        else:
            super().keyPressEvent(e)

    def focusInEvent(self, e):
        self.update()

    def focusOutEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2
        p.setPen(_hairline())
        p.setBrush(T.with_alpha(T.SURFACE, 0.6))
        p.drawRoundedRect(r, rad, rad)
        cw = self._cell()
        pill = QRectF(4 + self._pos * cw, 4, cw, self.height() - 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.theme().accent)
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        p.setFont(T.font(13 if self.compact else 14, 600))
        for i, label in enumerate(self.labels):
            cell = QRectF(4 + i * cw, 0, cw, self.height())
            near = 1.0 - min(1.0, abs(self._pos - i))
            idle = T.TEXT if i == self._hover else T.MUTED
            p.setPen(T.mix(idle, T.INK, near))
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, label)
        if kfocus(self):
            _focus_ring(p, r, rad)
        p.end()


class Switch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._a = _anim(self, self._set, 150)
        self.toggled.connect(lambda on: _run(self._a, self._pos, 1.0 if on else 0.0))
        T.theme().changed.connect(self.update)

    def _set(self, v):
        self._pos = v
        self.update()

    def setChecked(self, on):
        super().setChecked(on)
        self._a.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.mix(T.LINE, T.theme().accent, self._pos))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        x = r.left() + 12 + self._pos * (r.width() - 24)
        p.setBrush(T.mix(T.MUTED, T.INK, self._pos))
        p.drawEllipse(QPointF(x, r.center().y()), 8.5, 8.5)
        if kfocus(self):
            _focus_ring(p, r, r.height() / 2)
        p.end()


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------
class Button(QAbstractButton):
    """kind: 'primary' (accent fill), 'soft' (outlined neutral), 'ghost' (text only)."""

    def __init__(self, text="", kind="soft", icon=None, parent=None, height=40):
        super().__init__(parent)
        self.kind = kind
        self.icon_name = icon
        self.setText(str(text).lower())
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        T.theme().changed.connect(self.update)

    def sizeHint(self):
        w = QFontMetrics(T.font(14, 600)).horizontalAdvance(self.text()) + 36
        if self.icon_name:
            w += 24 if self.text() else -8
        return QSize(max(w, self.height()), self.height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def setIconName(self, name):
        self.icon_name = name
        self.updateGeometry()
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2
        acc = T.theme().accent
        border = Qt.PenStyle.NoPen
        if self.kind == "primary":
            bg = T.mix(acc, T.BG, 0.14) if self._hover else acc
            if self.isDown():
                bg = T.mix(acc, T.BG, 0.26)
            fg = T.INK
        elif self.kind == "soft":
            bg = T.RAISED if self._hover else T.SURFACE
            if self.isDown():
                bg = T.LINE
            fg = T.TEXT
            border = _hairline(T.mix(T.LINE, WHITE, 0.10) if self._hover else None)
        else:
            bg = T.with_alpha(WHITE, 0.08 if self._hover else 0.0)
            fg = T.TEXT if self._hover else T.MUTED
        p.setOpacity(1.0 if self.isEnabled() else 0.40)
        p.setPen(border)
        p.setBrush(bg)
        p.drawRoundedRect(r, rad, rad)
        f = T.font(14, 600)
        p.setFont(f)
        p.setPen(fg)
        text = self.text()
        if self.icon_name:
            tw = QFontMetrics(f).horizontalAdvance(text) if text else 0
            total = 18 + (8 + tw if text else 0)
            x = r.center().x() - total / 2
            icons.draw(p, self.icon_name, x + 9, r.center().y(), 18, fg, 2.0)
            if text:
                p.drawText(QRectF(x + 26, 0, tw + 4, self.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        else:
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, text)
        if kfocus(self):
            p.setOpacity(1.0)
            _focus_ring(p, r, rad)
        p.end()


class IconButton(QAbstractButton):
    def __init__(self, icon, tooltip="", parent=None, size=36):
        super().__init__(parent)
        self.icon_name = icon
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect())
        if self._hover or self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.with_alpha(WHITE, 0.16 if self.isDown() else 0.10))
            p.drawEllipse(r)
        icons.draw(p, self.icon_name, r.center().x(), r.center().y(), 20,
                   T.TEXT if self._hover else T.MUTED)
        if kfocus(self):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.with_alpha(T.TEXT, 0.8), 2))
            p.drawEllipse(r.adjusted(1, 1, -1, -1))
        p.end()


class DeviceButton(QAbstractButton):
    """Top left: which light is being controlled and whether it responds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name = ""
        self.status = None        # True, False or None (searching)
        self._hover = False
        self.setToolTip(t("Switch lights or find more"))

    def set(self, name: str, status):
        self.name = name
        self.status = status
        self.setAccessibleName(t("Light: {name}", name=name))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        w = QFontMetrics(T.font(14, 600)).horizontalAdvance(self._label()) + 68
        return QSize(min(w, 232), 36)

    def _label(self):
        return self.name.lower() or t("Choose a light")

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(_hairline(T.with_alpha(WHITE, 0.30 if self._hover else 0.18)))
        p.setBrush(T.with_alpha(WHITE, 0.10 if self._hover else 0.04))
        p.drawRoundedRect(r, 18, 18)
        status = self.status if self.name else None
        dot = QPointF(18, r.center().y())
        if status is False:               # offline: a hollow ring
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.WARN, 1.6))
            p.drawEllipse(dot, 4, 4)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.OK if status else T.FAINT)
            p.drawEllipse(dot, 4.5, 4.5)
        f = T.font(14, 600)
        p.setFont(f)
        p.setPen(T.TEXT)
        tr = QRectF(31, 0, r.width() - 31 - 28, self.height())
        text = QFontMetrics(f).elidedText(self._label(), Qt.TextElideMode.ElideRight, int(tr.width()))
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        icons.draw(p, "chevron", r.width() - 17, r.center().y() + 1, 16, T.MUTED, 2.1)
        if kfocus(self):
            _focus_ring(p, r, 18)
        p.end()


# --------------------------------------------------------------------------
# Swatches, tiles and scenes
# --------------------------------------------------------------------------
class Swatch(QAbstractButton):
    """A saved color. With color=None it is the 'save the current one' button."""

    def __init__(self, color: QColor | None, name="", parent=None):
        super().__init__(parent)
        self.color = color
        self.selected = False
        self._hover = False
        self.setFixedSize(44, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name if color is not None else t("Save the current color"))
        self.setAccessibleName(name or t("Save the current color"))

    def setSelected(self, on):
        if on != self.selected:
            self.selected = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        c = QRectF(self.rect()).center()
        if self.color is None:
            pen = QPen(T.MUTED if self._hover else T.FAINT, 1.4, Qt.PenStyle.DashLine)
            pen.setDashPattern([3, 3])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 17, 17)
            icons.draw(p, "plus", c.x(), c.y(), 18, T.TEXT if self._hover else T.MUTED, 2.0)
        else:
            if self.selected or kfocus(self):
                p.setPen(QPen(T.TEXT, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, 20.5, 20.5)
            rad = 15.5 if self.selected else (18 if self._hover or self.isDown() else 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.color)
            p.drawEllipse(c, rad, rad)
        p.end()


def _tile_frame(p: QPainter, r: QRectF, selected: bool, hover: bool, radius: float = 12):
    """Shared look of tiles: outlined when idle, inverted when selected."""
    if selected:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.theme().accent)
    else:
        p.setPen(_hairline(T.mix(T.LINE, WHITE, 0.14) if hover else None))
        p.setBrush(T.RAISED if hover else T.SURFACE)
    p.drawRoundedRect(r, radius, radius)


class Card(QWidget):
    """A plain outlined panel that groups related controls."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setPen(_hairline())
        p.setBrush(T.SURFACE)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.end()


class Tile(QAbstractButton):
    """Option with a title and description; optionally a color dot."""

    def __init__(self, title, subtitle="", dot: QColor | None = None, parent=None, height=62):
        super().__init__(parent)
        self.title = str(title).lower()
        self.subtitle = str(subtitle).lower()
        self.dot = dot
        self.selected = False
        self._hover = False
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)
        T.theme().changed.connect(self.update)

    def setSelected(self, on):
        if on != self.selected:
            self.selected = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        _tile_frame(p, r, self.selected, self._hover)
        title_c = T.INK if self.selected else T.TEXT
        sub_c = T.with_alpha(T.INK, 0.66) if self.selected else T.MUTED
        x = 15.0
        if self.dot is not None:
            p.setPen(QPen(T.with_alpha(BLACK, 0.18), 1) if self.selected else Qt.PenStyle.NoPen)
            p.setBrush(self.dot)
            p.drawEllipse(QPointF(x + 8, r.center().y()), 8, 8)
            x += 28
        tf = T.font(14, 600)
        sf = T.font(12, 400)
        avail = int(r.right() - x - 10)
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if self.subtitle:
            p.setFont(tf)
            p.setPen(title_c)
            p.drawText(QRectF(x, r.center().y() - 19, avail, 20), left,
                       QFontMetrics(tf).elidedText(self.title, Qt.TextElideMode.ElideRight, avail))
            p.setFont(sf)
            p.setPen(sub_c)
            p.drawText(QRectF(x, r.center().y() + 1, avail, 18), left,
                       QFontMetrics(sf).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, avail))
        else:
            p.setFont(tf)
            p.setPen(title_c)
            p.drawText(QRectF(x, r.top(), avail, r.height()), left, self.title)
        if kfocus(self):
            _focus_ring(p, r, 12)
        p.end()


class SceneTile(QAbstractButton):
    """A built-in scene: a neutral tile with a chip showing the scene's colors."""

    def __init__(self, scene_id, name, dynamic, colors, parent=None):
        super().__init__(parent)
        self.scene_id = scene_id
        self.name = str(name).lower()
        self.dynamic = dynamic
        self.colors = [QColor(c) if isinstance(c, str) else QColor(*c) for c in colors]
        self.selected = False
        self._hover = False
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(t("{name} scene", name=name))
        T.theme().changed.connect(self.update)

    def setSelected(self, on):
        if on != self.selected:
            self.selected = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        _tile_frame(p, r, self.selected, self._hover)
        chip = QRectF(r.left() + 13, r.top() + 13, 30, 14)
        g = QLinearGradient(chip.topLeft(), chip.topRight())
        last = max(1, len(self.colors) - 1)
        for i, c in enumerate(self.colors):
            g.setColorAt(i / last, c)
        p.setPen(QPen(T.with_alpha(BLACK, 0.18), 1) if self.selected else Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(chip, 7, 7)
        avail = int(r.width() - 24)
        f = T.font(13, 600)
        if QFontMetrics(f).horizontalAdvance(self.name) > avail:      # a long name: one size down before cutting it
            f = T.font(12, 600)
        p.setFont(f)
        p.setPen(T.INK if self.selected else T.TEXT)
        p.drawText(QRectF(r.left() + 13, r.bottom() - 31, avail, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QFontMetrics(f).elidedText(self.name, Qt.TextElideMode.ElideRight, avail))
        if kfocus(self):
            _focus_ring(p, r, 12)
        p.end()


class Bars(Themed):
    """Spectrum of what is playing."""

    COUNT = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = [0.0] * self.COUNT
        self.running = False
        self.setFixedHeight(44)

    def set(self, values):
        self.values = list(values) if values is not None else [0.0] * self.COUNT
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        n = len(self.values)
        gap = 3.0
        w = (self.width() - gap * (n - 1)) / n
        h = self.height()
        acc = T.theme().accent
        p.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(self.values):
            v = float(v)
            bh = max(3.0, v * h) if self.running else 3.0
            p.setBrush(T.with_alpha(acc, 0.40 + 0.60 * v) if self.running else T.LINE)
            p.drawRoundedRect(QRectF(i * (w + gap), h - bh, w, bh), 1.5, 1.5)
        p.end()


class ScreenPreview(Themed):
    """Shows the color being picked up from the screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = None
        self.running = False
        self.setFixedHeight(44)

    def set(self, rgb):
        self.color = QColor(*rgb) if rgb else None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 8.5, -0.5, -8.5)
        if self.running and self.color is not None:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, T.with_alpha(self.color, 0.20))
            g.setColorAt(0.5, self.color)
            g.setColorAt(1, T.with_alpha(self.color, 0.20))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
        else:
            p.setPen(_hairline())
            p.setBrush(T.SURFACE)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.end()
