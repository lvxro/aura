"""Portable settings: everything is saved in the "data" folder, next to the program."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

from . import sound

DEFAULTS = {
    "version": 2,
    "lights": [],            # [{"mac", "ip", "name", "model"}]
    "active": None,          # mac of the selected light
    "state": {               # last known state, so startup doesn't have to wait
        "on": True, "brightness": 100, "mode": "white",
        "rgb": [255, 140, 60], "temp": 2700, "scene": 6, "speed": 100,
    },
    "favorites": {
        "rgb": [
            {"name": "Sunset", "rgb": [255, 120, 40]},
            {"name": "Pink", "rgb": [255, 70, 140]},
            {"name": "Violet", "rgb": [128, 0, 255]},
            {"name": "Blue", "rgb": [0, 60, 255]},
            {"name": "Aqua", "rgb": [0, 255, 220]},
            {"name": "Green", "rgb": [40, 255, 60]},
            {"name": "Red", "rgb": [255, 0, 0]},
        ],
        "white": [
            {"name": "Candle", "temp": 2200, "brightness": 40},
            {"name": "Warm", "temp": 2700, "brightness": 100},
            {"name": "Relax", "temp": 3000, "brightness": 70},
            {"name": "Neutral", "temp": 4000, "brightness": 100},
            {"name": "Day", "temp": 5200, "brightness": 100},
            {"name": "Cool", "temp": 6500, "brightness": 100},
        ],
    },
    "effects": {
        "kind": "music",
        "music": {"mode": "spectrum", "sensitivity": 1.0, "smoothing": 0.3, "source": "pc"},
        "screen": {"mode": "edges", "smoothing": 0.6, "boost": 1.3, "monitor": 1},
    },
    "scenes": [               # scenes made by the person: the light glides between the colors
        {"id": "aurora", "name": "Aurora", "colors": [[0, 255, 140], [0, 170, 255], [150, 60, 255]], "seconds": 5.0},
        {"id": "embers", "name": "Embers", "colors": [[255, 50, 0], [255, 150, 20], [255, 30, 90]], "seconds": 4.0},
    ],
    "routines": {
        "sleep_minutes": 30,
        "wake": {"enabled": False, "time": "07:00", "minutes": 20, "days": "daily"},   # or "weekdays"
        "circadian": False,     # white follows the time of day
        "pc_follow": False,     # off when the PC locks or sleeps, back on when you return
    },
    "settings": {
        "hotkeys": {"toggle": "Ctrl+Alt+L", "brighter": "Ctrl+Alt+PageUp",
                    "dimmer": "Ctrl+Alt+PageDown", "next": "Ctrl+Alt+K"},
        "close_to_tray": True,
        "sound": "cream",         # keystroke played on power on/off: an id from sound.py, "custom" or "off"
        "tray_click": "toggle",   # "toggle" or "open"
        "tab": 0,
        "language": "en",         # "en" or "es"
    },
}


def app_root() -> str:
    """Program folder (where Aura.exe lives)."""
    env = os.environ.get("AURA_HOME")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))       # .../app/aura
    return os.path.dirname(os.path.dirname(here))            # .../


def _is_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path, prefix=".w")
        os.close(fd)
        os.remove(tmp)
        return True
    except OSError:
        return False


def data_dir() -> str:
    portable = os.path.join(app_root(), "data")
    if _is_writable(portable):
        return portable
    # Read-only folder (for example, Program Files): fall back to the user profile.
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback = os.path.join(base, "Aura")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Store:
    def __init__(self, directory: str | None = None):
        self.dir = directory or data_dir()
        self.path = os.path.join(self.dir, "aura.json")
        self.first_run = not os.path.exists(self.path)
        self.data = copy.deepcopy(DEFAULTS)
        self.load()
        if self.first_run:
            self._import_from_original()

    # -- disk -------------------------------------------------------------
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data = _merge(DEFAULTS, loaded)
                self._migrate(loaded)
        except (OSError, ValueError):
            pass

    def _migrate(self, loaded: dict):
        """Carry over settings saved by earlier versions."""
        s = self.data["settings"]
        old = (loaded.get("settings") or {})
        if "hotkey" in old and "hotkeys" not in old:
            s["hotkeys"]["toggle"] = old["hotkey"] or ""
        if "sounds" in old and "sound" not in old:      # it used to be a plain on/off switch
            s["sound"] = sound.DEFAULT if old["sounds"] else sound.OFF
        s["sound"] = sound.normalize(s.get("sound"))    # sounds that no longer exist become the default
        for gone in ("hotkey", "theme", "accent", "sounds"):
            s.pop(gone, None)

    def save(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _import_from_original(self):
        """If kek's original app was installed, bring over its saved lights."""
        base = os.environ.get("LOCALAPPDATA")
        if not base or sys.platform != "win32":
            return
        old = os.path.join(base, "KeksWizLightController")
        try:
            with open(os.path.join(old, "saved_lights.json"), "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        last_ip = ""
        try:
            with open(os.path.join(old, "last_ip.txt"), "r", encoding="utf-8") as f:
                last_ip = f.read().strip()
        except OSError:
            pass
        if not isinstance(saved, dict):
            return
        for mac, info in saved.items():
            if not isinstance(info, dict) or not info.get("ip"):
                continue
            self.upsert_light(str(mac).lower(), info["ip"], name=info.get("name"))
            if info["ip"] == last_ip:
                self.data["active"] = str(mac).lower()
        if self.data["lights"] and not self.data["active"]:
            self.data["active"] = self.data["lights"][0]["mac"]

    # -- lights -------------------------------------------------------------
    @property
    def lights(self) -> list[dict]:
        return self.data["lights"]

    def light(self, mac: str | None) -> dict | None:
        for l in self.data["lights"]:
            if l["mac"] == mac:
                return l
        return None

    def active_light(self) -> dict | None:
        return self.light(self.data.get("active"))

    def upsert_light(self, mac: str, ip: str, name: str | None = None,
                     model: str | None = None) -> dict:
        l = self.light(mac)
        if l is None:
            l = {"mac": mac, "ip": ip, "name": name or self._next_name(), "model": model or "WiZ light"}
            self.data["lights"].append(l)
        else:
            l["ip"] = ip
            if name:
                l["name"] = name
            if model:
                l["model"] = model
        return l

    def _next_name(self) -> str:
        names = {l["name"] for l in self.data["lights"]}
        if "My light" not in names:
            return "My light"
        n = 2
        while f"Light {n}" in names:
            n += 1
        return f"Light {n}"

    def remove_light(self, mac: str):
        self.data["lights"] = [l for l in self.data["lights"] if l["mac"] != mac]
        if self.data.get("active") == mac:
            self.data["active"] = self.data["lights"][0]["mac"] if self.data["lights"] else None

    # -- shortcuts ------------------------------------------------------------
    @property
    def settings(self) -> dict:
        return self.data["settings"]

    @property
    def favorites(self) -> dict:
        return self.data["favorites"]

    @property
    def effects(self) -> dict:
        return self.data["effects"]
