"""State of the selected light and communication with it, built for the interface.

The interface changes the state with update()/toggle() and listens to the changed
signal. Sends are throttled (so dragging a control feels live without flooding the
bulb) and queries run on separate threads.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import wiz
from .effects import EffectRunner
from .i18n import t
from .store import Store

SEND_GAP_MS = 70        # minimum gap between sends while a control is being dragged
RESEND_MS = 220         # UDP gives no delivery receipt: the last state is sent once more
POLL_MS = 4000          # how often the bulb is asked for its state


class Light(QObject):
    changed = Signal()               # the state changed (brightness, color, power…)
    userChanged = Signal(object)     # the person changed these state keys (not a routine)
    connectionChanged = Signal()     # connected or the selected light changed
    effectFrame = Signal(object)     # a frame from the running effect
    effectChanged = Signal(str)      # an effect started or stopped (error text or "")
    discovered = Signal(object)      # a light found during a scan
    discoveryFinished = Signal(int)

    _pilot = Signal(object, str)
    _relocated = Signal(str, str)
    _effectStopped = Signal(str, object)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.sender = wiz.Sender()
        s = store.data["state"]
        self.state = {
            "on": bool(s.get("on", True)), "brightness": int(s.get("brightness", 100)),
            "mode": s.get("mode", "white"), "rgb": tuple(s.get("rgb", (255, 140, 60))),
            "temp": int(s.get("temp", 2700)), "scene": int(s.get("scene", 6)),
            "speed": int(s.get("speed", 100)),
        }
        self.connected: bool | None = None     # None = not known yet
        self._fails = 0
        self._last_user = 0.0
        self._last_send = 0.0
        self._pending = False
        self._syncing = False
        self._locating = False
        self._last_locate = 0.0
        self.runner: EffectRunner | None = None
        self.effect_kind: str | None = None
        self.effect_id: str | None = None        # which custom scene is playing, if any
        self._scan_stop: threading.Event | None = None

        self._gap = QTimer(self, singleShot=True, interval=SEND_GAP_MS)
        self._gap.timeout.connect(self._flush_pending)
        self._resend = QTimer(self, singleShot=True, interval=RESEND_MS)
        self._resend.timeout.connect(self._send_now)
        self._save = QTimer(self, singleShot=True, interval=800)
        self._save.timeout.connect(self._persist)
        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self.sync)

        self._pilot.connect(self._on_pilot)
        self._relocated.connect(self._on_relocated)
        self._effectStopped.connect(self._on_effect_stopped)

    # -- selected light ------------------------------------------------------
    @property
    def info(self) -> dict | None:
        return self.store.active_light()

    @property
    def ip(self) -> str:
        l = self.info
        return l["ip"] if l else ""

    @property
    def name(self) -> str:
        l = self.info
        return l["name"] if l else ""

    def start(self):
        self._poll.start()
        if self.info:
            self.sync()

    def select(self, mac: str | None):
        self.stop_effect()
        self.store.data["active"] = mac
        self.store.save()
        self.connected = None
        self._fails = 0
        self.connectionChanged.emit()
        if mac:
            self.sync()

    # -- visible color ----------------------------------------------------------
    def display_rgb(self) -> tuple[int, int, int]:
        """The color the interface uses to represent the light right now."""
        st = self.state
        if st["mode"] == "rgb":
            r, g, b = st["rgb"]
            m = max(r, g, b, 1)
            return (int(r * 255 / m), int(g * 255 / m), int(b * 255 / m))
        if st["mode"] == "scene":
            for sid, _n, _d, colors in wiz.SCENES:
                if sid == st["scene"]:
                    c = colors[0].lstrip("#")
                    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
            return (255, 180, 90)
        return wiz.kelvin_to_rgb(st["temp"])

    # -- changes from the interface -------------------------------------------
    def update(self, auto: bool = False, **changes):
        """Change the state and send it to the light (throttled).

        auto=True marks a change made by a routine rather than by the person.
        """
        if self.runner is not None and any(k in changes for k in ("rgb", "temp", "scene", "mode")):
            self.stop_effect(restore=False)
        changed = set()
        for k, v in changes.items():
            if k == "rgb":
                v = tuple(int(x) for x in v)
            if self.state.get(k) != v:
                self.state[k] = v
                changed.add(k)
        if not changed:
            return
        self._last_user = time.monotonic()
        self.changed.emit()
        self._save.start()
        if self.runner is None:      # during an effect, brightness acts as an overall cap
            self._queue_send()
        if not auto:
            self.userChanged.emit(changed)

    def step_brightness(self, delta: int):
        self.update(brightness=int(wiz.clamp(self.state["brightness"] + delta, wiz.MIN_DIM, 100)))

    def insist(self, delays):
        """Send the current state again after each delay (seconds), for shaky moments."""
        for d in delays:
            QTimer.singleShot(int(d * 1000), self._send_now)

    def set_power(self, on: bool, auto: bool = False):
        if self.runner is not None and not on:
            self.stop_effect(restore=False)
        if self.state["on"] == on and self.runner is None:
            return
        self.state["on"] = on
        self._last_user = time.monotonic()
        self.changed.emit()
        self._save.start()
        self._send_now()
        self._resend.start()
        if not auto:
            self.userChanged.emit({"on"})

    def toggle(self):
        self.set_power(not self.state["on"])

    def _queue_send(self):
        if not self.ip:
            return
        if self._gap.isActive():
            self._pending = True
            return
        self._send_now()
        self._gap.start()
        self._resend.start()

    def _flush_pending(self):
        if self._pending:
            self._pending = False
            self._send_now()
            self._gap.start()
            self._resend.start()

    def _send_now(self):
        if not self.ip or self.runner is not None:
            return
        self.sender.send(self.ip, "setPilot", wiz.pilot_for(self.state))
        self._last_send = time.monotonic()

    def _persist(self):
        st = dict(self.state)
        st["rgb"] = list(st["rgb"])
        self.store.data["state"] = st
        self.store.save()

    # -- reading the real state --------------------------------------------------
    def sync(self):
        ip = self.ip
        if not ip or self._syncing or self.runner is not None:
            return
        self._syncing = True

        def work():
            result = wiz.get_pilot(ip)
            self._pilot.emit(result, ip)

        threading.Thread(target=work, daemon=True, name="aura-sync").start()

    def _on_pilot(self, result, ip):
        self._syncing = False
        self.sender.drain()
        if ip != self.ip:
            return
        if result is None:
            self._fails += 1
            if self._fails >= 2 or self.connected is None:
                if self.connected is not False:
                    self.connected = False
                    self.connectionChanged.emit()
                self._locate()
            return
        self._fails = 0
        if self.connected is not True:
            self.connected = True
            self.connectionChanged.emit()
        mac = result.get("mac")
        info = self.info
        if mac and info and str(mac).lower() != info["mac"]:
            return      # that IP now belongs to another device
        # Don't overwrite what the person just touched.
        if time.monotonic() - self._last_user < 1.5 or self.runner is not None:
            return
        new = wiz.state_from_pilot(result)
        changed = False
        for k, v in new.items():
            if self.state.get(k) != v:
                self.state[k] = v
                changed = True
        if changed:
            self.changed.emit()
            self._save.start()

    def _locate(self):
        """The router may have given it a new IP: find it again by its MAC."""
        info = self.info
        if not info or self._locating or time.monotonic() - self._last_locate < 15:
            return
        self._locating = True
        self._last_locate = time.monotonic()
        mac = info["mac"]

        def work():
            new_ip = ""
            for e in wiz.discover(timeout=1.0, attempts=2):
                if e["mac"] == mac:
                    new_ip = e["ip"]
                    break
            self._relocated.emit(mac, new_ip)

        threading.Thread(target=work, daemon=True, name="aura-locate").start()

    def _on_relocated(self, mac, new_ip):
        self._locating = False
        l = self.store.light(mac)
        if l and new_ip and l["ip"] != new_ip:
            l["ip"] = new_ip
            self.store.save()
            if self.store.data.get("active") == mac:
                self._fails = 0
                self.sync()

    # -- finding lights ------------------------------------------------------------
    def scan(self):
        if self._scan_stop is not None:
            return
        stop = self._scan_stop = threading.Event()

        def work():
            found = wiz.discover(timeout=1.2, attempts=3, on_found=self.discovered.emit, stop=stop)
            self._scan_stop = None
            self.discoveryFinished.emit(len(found))

        threading.Thread(target=work, daemon=True, name="aura-scan").start()

    def probe(self, ip: str, done):
        """Query an IP typed by hand. The result (dict or None) is emitted on `done`."""
        def work():
            cfg = wiz.get_system_config(ip, timeout=0.8, attempts=2)
            if cfg and cfg.get("mac"):
                done.emit({"ip": ip, "mac": str(cfg["mac"]).lower(),
                           "module": cfg.get("moduleName"),
                           "model": wiz._friendly_model(cfg.get("moduleName"))})
            else:
                done.emit(None)
        threading.Thread(target=work, daemon=True, name="aura-probe").start()

    # -- effects ---------------------------------------------------------------------
    def start_effect(self, kind: str, options: dict, effect_id: str | None = None):
        if not self.ip:
            self.effectChanged.emit(t("Choose a light first."))
            return
        previous = self.runner
        self.stop_effect(restore=False)
        if not self.state["on"]:
            self.state["on"] = True
            self.changed.emit()
        base = self.display_rgb()
        runner = EffectRunner(
            kind, options, self.ip, base, lambda: self.state["brightness"],
            on_frame=self.effectFrame.emit,
            on_stop=lambda err, r=None: self._effectStopped.emit(err, runner),
            after=previous)
        self.runner = runner
        self.effect_kind = kind
        self.effect_id = effect_id
        runner.start()
        self.effectChanged.emit("")

    def stop_effect(self, restore: bool = True):
        runner = self.runner
        if runner is None:
            return
        self.runner = None
        self.effect_kind = None
        self.effect_id = None
        runner.stop()
        self.effectChanged.emit("")
        if restore:
            # Give the thread a moment so it doesn't overwrite the restored state.
            QTimer.singleShot(120, self._restore_after_effect)

    def _restore_after_effect(self):
        if self.runner is None:
            self._send_now()
            self._resend.start()

    def _on_effect_stopped(self, error, runner):
        if runner is not self.runner:
            if self.runner is None and not self._gap.isActive():
                self._send_now()        # we stopped it ourselves: make the chosen state stick
            return
        self.runner = None
        self.effect_kind = None
        self.effect_id = None
        self.effectChanged.emit(error or "")
        self._send_now()

    def shutdown(self):
        self._poll.stop()
        if self.runner is not None:
            self.runner.stop()
            self.runner = None
            self._send_now()
        self._persist()
