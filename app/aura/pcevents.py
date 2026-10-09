"""What the PC is doing (Windows only): locked, unlocked, going to sleep, back from sleep.

Windows reports these to windows, so a hidden window is created just to listen:
session changes need an explicit subscription, power changes are broadcast.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QWidget

WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007       # woke up because the person did something
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "PcEvents"):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message in (WM_POWERBROADCAST, WM_WTSSESSION_CHANGE):
                    # Power changes are broadcast to every window: only count ours.
                    if not self.owner.hwnd or int(msg.hWnd or 0) == self.owner.hwnd:
                        self.owner.handle(msg.message, int(msg.wParam))
        except Exception:
            pass
        return False, 0


class PcEvents(QObject):
    away = Signal()         # the PC was locked or is going to sleep
    back = Signal()         # it was unlocked, or woken up by the person

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.supported = sys.platform == "win32"
        self.hwnd = 0
        self._window = None
        self._filter = None
        if not self.supported:
            return
        try:
            import ctypes
            from ctypes import wintypes
            self._window = QWidget()
            self._window.setWindowTitle("Aura events")
            self.hwnd = int(self._window.winId())       # creates the native window; it stays hidden
            register = ctypes.windll.wtsapi32.WTSRegisterSessionNotification
            register.argtypes = [wintypes.HWND, wintypes.DWORD]
            register.restype = wintypes.BOOL
            register(wintypes.HWND(self.hwnd), 0)        # 0 = only this session
            self._filter = _Filter(self)
            app.installNativeEventFilter(self._filter)
        except Exception:
            self.supported = False

    def handle(self, message: int, wparam: int):
        if message == WM_WTSSESSION_CHANGE:
            if wparam == WTS_SESSION_LOCK:
                self.away.emit()
            elif wparam == WTS_SESSION_UNLOCK:
                self.back.emit()
        elif message == WM_POWERBROADCAST:
            if wparam == PBT_APMSUSPEND:
                self.away.emit()
            elif wparam == PBT_APMRESUMESUSPEND:
                self.back.emit()

    def close(self):
        if self.supported and self.hwnd:
            try:
                import ctypes
                from ctypes import wintypes
                unregister = ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification
                unregister.argtypes = [wintypes.HWND]
                unregister(wintypes.HWND(self.hwnd))
            except Exception:
                pass
