"""Global keyboard shortcuts (Windows only): they work even while Aura sits in the tray."""

from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
BASE_ID = 0xA070

# Action name -> default shortcut. The order is the order shown in Settings.
DEFAULTS = {
    "toggle": "Ctrl+Alt+L",
    "brighter": "Ctrl+Alt+PageUp",
    "dimmer": "Ctrl+Alt+PageDown",
    "next": "Ctrl+Alt+K",
}
ACTIONS = tuple(DEFAULTS)

_NAMED = {
    "Space": 0x20, "Home": 0x24, "End": 0x23, "Insert": 0x2D, "Delete": 0x2E,
    "PageUp": 0x21, "PageDown": 0x22, "Left": 0x25, "Up": 0x26, "Right": 0x27,
    "Down": 0x28, "Pause": 0x13,
}
_QT_NAMED = {
    Qt.Key.Key_Space: "Space", Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
    Qt.Key.Key_Insert: "Insert", Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Up: "Up", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Down: "Down", Qt.Key.Key_Pause: "Pause",
}


def parse(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+L' -> (modifiers, virtual key). None if it is not valid."""
    if not text:
        return None
    mods = 0
    vk = None
    for part in [p.strip() for p in text.split("+") if p.strip()]:
        low = part.lower()
        if low == "ctrl":
            mods |= MOD_CONTROL
        elif low == "alt":
            mods |= MOD_ALT
        elif low == "shift":
            mods |= MOD_SHIFT
        elif low == "win":
            mods |= MOD_WIN
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
            vk = 0x70 + int(low[1:]) - 1
        elif part in _NAMED:
            vk = _NAMED[part]
        else:
            return None
    if vk is None:
        return None
    return mods, vk


def from_event(event) -> str | None:
    """Build the shortcut text from a Qt key event."""
    key = event.key()
    mods = event.modifiers()
    parts = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")
    name = None
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key)
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        name = f"F{key - Qt.Key.Key_F1 + 1}"
    elif key in _QT_NAMED:
        name = _QT_NAMED[key]
    if name is None:
        return None
    # A bare key as a global shortcut could no longer be typed anywhere.
    is_fkey = name.startswith("F") and name[1:].isdigit()
    if not parts and not is_fkey:
        return None
    if parts == ["Shift"] and not is_fkey:
        return None
    return "+".join(parts + [name])


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and BASE_ID <= msg.wParam < BASE_ID + len(ACTIONS):
                    self.callback(ACTIONS[msg.wParam - BASE_ID])
                    return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkeys(QObject):
    """One system-wide shortcut per action. `activated` carries the action name."""

    activated = Signal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.supported = sys.platform == "win32"
        self.combos: dict[str, str] = {}
        self.ok: dict[str, bool] = {}
        self._registered: set[str] = set()
        self._filter = None
        if self.supported:
            self._filter = _Filter(self.activated.emit)
            app.installNativeEventFilter(self._filter)

    def set(self, action: str, text: str) -> bool:
        """Register a shortcut. Returns False if Windows rejects it (already in use)."""
        self.clear(action)
        self.combos[action] = text or ""
        ok = True
        if self.supported and text:
            parsed = parse(text)
            if parsed is None:
                ok = False
            else:
                mods, vk = parsed
                try:
                    import ctypes
                    from ctypes import wintypes
                    register = ctypes.windll.user32.RegisterHotKey
                    register.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
                    register.restype = wintypes.BOOL
                    ok = bool(register(None, BASE_ID + ACTIONS.index(action), mods | MOD_NOREPEAT, vk))
                except Exception:
                    ok = False
                if ok:
                    self._registered.add(action)
        elif text and parse(text) is None:
            ok = False
        self.ok[action] = ok
        return ok

    def clear(self, action: str | None = None):
        for name in ([action] if action else list(self._registered)):
            if name in self._registered:
                try:
                    import ctypes
                    ctypes.windll.user32.UnregisterHotKey(None, BASE_ID + ACTIONS.index(name))
                except Exception:
                    pass
                self._registered.discard(name)
