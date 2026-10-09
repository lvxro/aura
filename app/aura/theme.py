"""Colors, typography and styles. The lamp shows the light's color; controls use the accent."""

from __future__ import annotations

import glob
import os

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase

# Monochrome palette: black, white and grays. The only color on screen is the
# glow of the light itself (and things that are colors: the wheel, swatches, chips).
NIGHT = QColor("#000000")       # lamp panel
BG = QColor("#0A0A0A")          # controls background
SURFACE = QColor("#131313")     # cards and fields
RAISED = QColor("#1F1F1F")      # elements on a card, hover
LINE = QColor("#2C2C2C")        # hairlines
TEXT = QColor("#FAFAFA")
MUTED = QColor("#9C9C9C")
FAINT = QColor("#606060")
INK = QColor("#0A0A0A")         # text on top of white or of the light color
ACCENT = QColor("#FFFFFF")      # selected items are inverted: white with black text
OK = QColor("#FAFAFA")
WARN = QColor("#FF7A7A")

FONT = "JetBrains Mono"         # all running text: sentences, buttons, tabs, labels
FONT_DOT = "Doto"               # dot-matrix: headlines and numbers
FALLBACKS = ["Cascadia Mono", "Consolas", "monospace"]


def load_fonts():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    for path in sorted(glob.glob(os.path.join(here, "*.ttf"))):
        QFontDatabase.addApplicationFont(path)


_FAMILY = {400: FONT, 500: FONT + " Medium", 600: FONT + " SemiBold", 700: FONT + " SemiBold"}
TEXT_SCALE = 0.93               # a monospaced face runs wide; a touch smaller keeps the layout


def font(size: float, weight: int = 400, display: bool = False, mono: bool = False) -> QFont:
    """Each weight is its own family, so it resolves the same on Windows, Linux and macOS.

    display: the dot-matrix face, for headlines and numbers (keep it at 18 px or more).
    mono:    the technical face, for small uppercase labels (letter-spaced).
    """
    f = QFont()
    if display:
        f.setFamilies([FONT_DOT] + FALLBACKS)
    elif mono:
        f.setFamilies([_FAMILY[500]] + FALLBACKS)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(1.0, size * 0.12))
    else:
        f.setFamilies([_FAMILY.get(weight, FONT)] + FALLBACKS)
        size = size * TEXT_SCALE
    f.setPixelSize(int(round(size)))
    f.setWeight(QFont.Weight.Normal)        # the weight lives in the family name
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def make_menu(parent=None, title: str | None = None):
    """Menu with truly rounded corners (without the opaque box Windows draws)."""
    from PySide6.QtWidgets import QMenu
    m = QMenu(title, parent) if title else QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint
                     | Qt.WindowType.NoDropShadowWindowHint)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return m


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def luminance(c: QColor) -> float:
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def readable(c: QColor, minimum: float = 0.30) -> QColor:
    """Lighten a color until it reads well on the dark background."""
    out = QColor(c)
    t = 0.0
    while luminance(out) < minimum and t < 1.0:
        t += 0.06
        out = mix(c, QColor("#ffffff"), t)
    return out


def with_alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(max(0.0, min(1.0, a)))
    return out


class Theme(QObject):
    """Holds the light's color and animates it; widgets repaint when it changes."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.light = QColor("#FFB45E")     # the light's real color
        self.power = 1.0                   # 0 off … 1 on
        self.level = 1.0                   # brightness 0..1
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._tick)
        self._from = (QColor(self.light), self.power, self.level)
        self._to = (QColor(self.light), self.power, self.level)

    @property
    def accent(self) -> QColor:
        return QColor(ACCENT)

    def set(self, light: QColor, power: float, level: float, animate: bool = True):
        target = (QColor(light), float(power), float(level))
        if (target[0] == self._to[0] and abs(target[1] - self._to[1]) < 1e-3
                and abs(target[2] - self._to[2]) < 1e-3):
            return
        self._to = target
        if not animate:
            self._anim.stop()
            self.light, self.power, self.level = target
            self._from = target
            self.changed.emit()
            return
        self._from = (QColor(self.light), self.power, self.level)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _tick(self, t):
        a, b = self._from, self._to
        self.light = mix(a[0], b[0], t)
        self.power = a[1] + (b[1] - a[1]) * t
        self.level = a[2] + (b[2] - a[2]) * t
        self.changed.emit()


class KeyboardFocusFilter(QObject):
    """Record whether a widget got focus from the keyboard, so the ring shows only then."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and obj.isWidgetType():
            kbd = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
            if bool(obj.property("kbd")) != kbd:
                obj.setProperty("kbd", kbd)
                obj.update()
        return False


THEME: Theme | None = None


def theme() -> Theme:
    global THEME
    if THEME is None:
        THEME = Theme()
    return THEME


def stylesheet() -> str:
    return f"""
    * {{ outline: none; }}
    QWidget {{ color: {TEXT.name()}; }}
    QToolTip {{
        background: {RAISED.name()}; color: {TEXT.name()};
        border: 1px solid {LINE.name()}; padding: 5px 8px;
        font-family: "{FONT}"; font-size: 11px;
    }}
    QLineEdit {{
        background: {SURFACE.name()}; color: {TEXT.name()};
        border: 1px solid {LINE.name()}; border-radius: 10px;
        padding: 0 12px; min-height: 38px;
        font-family: "{FONT}"; font-size: 13px;
        selection-background-color: {MUTED.name()}; selection-color: {INK.name()};
    }}
    QLineEdit:focus {{ border: 1px solid {MUTED.name()}; }}
    QLineEdit::placeholder {{ color: {FAINT.name()}; }}
    QMenu {{
        background: {SURFACE.name()}; border: 1px solid {LINE.name()};
        border-radius: 10px; padding: 6px;
        font-family: "{FONT}"; font-size: 12px;
    }}
    QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; color: {TEXT.name()}; }}
    QMenu::item:selected {{ background: {RAISED.name()}; }}
    QMenu::item:disabled {{ color: {FAINT.name()}; }}
    QMenu::separator {{ height: 1px; background: {LINE.name()}; margin: 6px 8px; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 0; }}
    QScrollBar::handle:vertical {{ background: {LINE.name()}; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: {FAINT.name()}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    """
