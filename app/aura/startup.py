"""Start with Windows: an entry under the current user's "Run" key.

This is the only thing Aura ever writes outside its own folder, and only while
the switch in Settings is on. Turning the switch off removes the entry.
"""

from __future__ import annotations

import os
import sys

from .store import app_root

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Aura"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    """What Windows should run at sign-in: Aura, straight into the tray."""
    launcher = os.path.join(app_root(), "Aura.exe")
    if os.path.isfile(launcher):
        return f'"{launcher}" --hidden'
    main = os.path.join(app_root(), "app", "main.py")
    return f'"{sys.executable}" -I "{main}" --hidden'


def current() -> str | None:
    """The registered command, or None if Aura does not start with Windows."""
    if not supported():
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE)
            return str(value)
    except OSError:
        return None


def is_enabled() -> bool:
    return current() is not None


def set_enabled(on: bool) -> bool:
    """Add or remove the entry. Returns True if the change was made."""
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def refresh():
    """If the folder was moved, point the existing entry at the new location."""
    cur = current()
    if cur is not None and cur != command():
        set_enabled(True)
