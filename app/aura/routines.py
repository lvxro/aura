"""Things the light does on its own: sleep timer, wake-up light, following the time
of day, and following the PC (off when it locks or sleeps, back on when you return).

All of it runs inside Aura, so Aura has to be running (the tray is enough).
"""

from __future__ import annotations

import datetime
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import wiz
from .controller import Light
from .store import Store

SLEEP_CHOICES = (15, 30, 45, 60)
WAKE_CHOICES = (10, 20, 30)
WAKE_START_TEMP, WAKE_END_TEMP = 2200, 4000

# Color temperature through the day: (hour, kelvin). Cool around midday, warm at night.
DAY_CURVE = [(0.0, 2300), (6.0, 2300), (7.0, 2700), (9.5, 5000), (12.0, 5500),
             (16.0, 5200), (19.0, 3800), (21.0, 2700), (23.0, 2300), (24.0, 2300)]


def temp_for_hour(hour: float) -> int:
    """Kelvin for a time of day (hour as a float, 0..24), rounded to 50."""
    hour = hour % 24.0
    for (h0, k0), (h1, k1) in zip(DAY_CURVE, DAY_CURVE[1:]):
        if h0 <= hour <= h1:
            f = 0.0 if h1 == h0 else (hour - h0) / (h1 - h0)
            return int(round((k0 + (k1 - k0) * f) / 50.0) * 50)
    return 2300


def parse_time(text: str) -> tuple[int, int] | None:
    """'7:30' or '07:30' -> (7, 30). None if it is not a valid time."""
    try:
        h, m = text.strip().split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


class Routines(QObject):
    changed = Signal()          # something worth redrawing: a countdown, a switch

    def __init__(self, light: Light, store: Store, pc=None, parent=None):
        super().__init__(parent)
        self.light, self.store, self.pc = light, store, pc
        self.cfg = store.data["routines"]
        self.now = datetime.datetime.now        # replaceable in tests
        self.clock = time.monotonic             # replaceable in tests

        self._sleep_end = 0.0
        self._sleep_total = 0.0
        self._sleep_from = 100
        self._sleep_restore = 100
        self._wake_running = False
        self._wake_window: tuple | None = None
        self._wake_done: tuple | None = None
        self._pc_off = False
        self._last_pc = ("", 0.0)

        self._tick = QTimer(self, interval=5000)
        self._tick.timeout.connect(self.tick)
        self._tick.start()
        light.userChanged.connect(self._user_changed)
        light.changed.connect(self._light_changed)
        if pc is not None:
            pc.away.connect(self.pc_away)
            pc.back.connect(self.pc_back)
        self._was_on = bool(light.state["on"])

    @property
    def pc_supported(self) -> bool:
        return bool(self.pc is not None and self.pc.supported)

    def _save(self):
        self.store.save()
        self.changed.emit()

    def tick(self):
        self._tick_sleep()
        self._tick_wake()
        self._tick_circadian()

    # -- sleep timer ---------------------------------------------------------
    @property
    def sleep_active(self) -> bool:
        return self._sleep_end > 0

    def sleep_remaining(self) -> int:
        """Whole minutes left (rounded up), 0 when idle."""
        if not self.sleep_active:
            return 0
        return max(1, int((self._sleep_end - self.clock() + 59) // 60))

    def start_sleep(self, minutes: int):
        if not self.light.info:
            return
        self.cfg["sleep_minutes"] = int(minutes)
        if not self.light.state["on"]:
            self.light.set_power(True, auto=True)
        self._sleep_total = minutes * 60.0
        self._sleep_end = self.clock() + self._sleep_total
        self._sleep_from = self._sleep_restore = int(self.light.state["brightness"])
        self._save()

    def cancel_sleep(self, restore: bool = True):
        if not self.sleep_active:
            return
        self._sleep_end = 0.0
        if restore and self.light.state["on"]:
            self.light.update(auto=True, brightness=self._sleep_restore)
        self.changed.emit()

    def _tick_sleep(self):
        if not self.sleep_active:
            return
        left = self._sleep_end - self.clock()
        if left <= 0:
            self._sleep_end = 0.0
            self.light.set_power(False, auto=True)
            # Next time it is turned on, it comes back at the brightness it had.
            self.light.state["brightness"] = self._sleep_restore
            self.light.changed.emit()
            self.changed.emit()
            return
        f = 1.0 - left / self._sleep_total if self._sleep_total else 1.0
        level = int(round(self._sleep_from + (wiz.MIN_DIM - self._sleep_from) * f))
        self.light.update(auto=True, brightness=max(wiz.MIN_DIM, level))
        self.changed.emit()

    # -- wake-up light -----------------------------------------------------------
    def set_wake(self, **changes):
        self.cfg["wake"].update(changes)
        self._wake_done = None
        self._save()
        self.tick()

    def _wake_window_now(self):
        """(start, end) of the ramp we are inside right now, or None."""
        w = self.cfg["wake"]
        hm = parse_time(w.get("time", ""))
        if not w.get("enabled") or hm is None:
            return None
        now = self.now()
        span = datetime.timedelta(minutes=int(w.get("minutes", 20)))
        for day in (now.date(), now.date() + datetime.timedelta(days=1)):
            end = datetime.datetime.combine(day, datetime.time(hm[0], hm[1]))
            if w.get("days") == "weekdays" and end.weekday() >= 5:
                continue
            if end - span <= now < end:
                return end - span, end
        return None

    def _tick_wake(self):
        if not self.light.info:
            return
        win = self._wake_window_now()
        if win is None:
            if self._wake_running:                # the set time arrived: finish at full
                self._wake_running = False
                self._wake_done = self._wake_window
                self.light.update(auto=True, on=True, mode="white", temp=WAKE_END_TEMP, brightness=100)
                self.changed.emit()
            return
        if win == self._wake_done:
            return                                # cancelled by hand for this morning
        if not self._wake_running:
            self._wake_running = True
            self._wake_window = win
            self.cancel_sleep(restore=False)
            if self.light.runner is not None:
                self.light.stop_effect(restore=False)
        start, end = win
        f = (self.now() - start).total_seconds() / max(1.0, (end - start).total_seconds())
        f = wiz.clamp(f, 0.0, 1.0)
        temp = int(round((WAKE_START_TEMP + (WAKE_END_TEMP - WAKE_START_TEMP) * f) / 50.0) * 50)
        self.light.update(auto=True, on=True, mode="white", temp=temp,
                          brightness=int(round(wiz.MIN_DIM + (100 - wiz.MIN_DIM) * f)))

    # -- following the time of day -------------------------------------------------
    def set_circadian(self, on: bool):
        self.cfg["circadian"] = bool(on)
        self._save()
        if on and self.light.info and self.light.state["on"]:
            self.light.update(auto=True, mode="white", temp=self._day_temp())
        self._tick_circadian()

    def _day_temp(self) -> int:
        now = self.now()
        return temp_for_hour(now.hour + now.minute / 60.0)

    def _tick_circadian(self):
        light = self.light
        if not self.cfg.get("circadian") or not light.info or self._wake_running:
            return
        st = light.state
        if not st["on"] or st["mode"] != "white" or light.runner is not None:
            return
        target = self._day_temp()
        if abs(target - st["temp"]) >= 50:
            light.update(auto=True, temp=target)

    # -- following the PC ------------------------------------------------------------
    def set_pc_follow(self, on: bool):
        self.cfg["pc_follow"] = bool(on)
        self._pc_off = False
        self._save()

    def _pc_event(self, kind: str) -> bool:
        """False for a repeat of the same event (Windows can deliver it more than once)."""
        last, when = self._last_pc
        now = self.clock()
        if last == kind and now - when < 2.0:
            return False
        self._last_pc = (kind, now)
        return True

    def pc_away(self):
        if not self._pc_event("away") or not self.cfg.get("pc_follow") or not self.light.info:
            return
        if self.light.state["on"]:
            self._pc_off = True
            self.light.set_power(False, auto=True)
            self.light.insist((0.15, 0.4))        # the PC may be asleep within a second

    def pc_back(self):
        if not self._pc_event("back") or not self.cfg.get("pc_follow") or not self._pc_off:
            return
        self._pc_off = False
        self.light.set_power(True, auto=True)
        self.light.insist((1.5, 4.0, 8.0, 15.0))   # the network can take a while after waking
        self._tick_circadian()

    # -- reacting to the person ---------------------------------------------------------
    def _user_changed(self, keys):
        keys = set(keys)
        if self._wake_running:
            # They are up and touching the light: stop the sunrise for today.
            self._wake_running = False
            self._wake_done = self._wake_window
        if self.sleep_active:
            if "on" in keys and not self.light.state["on"]:
                self._sleep_end = 0.0
                self.light.state["brightness"] = self._sleep_restore
                self.light.changed.emit()
            elif "brightness" in keys:
                # Continue the fade from the level they chose, over the time left.
                left = max(1.0, self._sleep_end - self.clock())
                self._sleep_total = left
                self._sleep_from = self._sleep_restore = int(self.light.state["brightness"])
        if "temp" in keys and self.cfg.get("circadian"):
            self.cfg["circadian"] = False          # a hand-picked white wins over the clock
            self.store.save()
        if "on" in keys:
            self._pc_off = False
        self.changed.emit()

    def _light_changed(self):
        on = bool(self.light.state["on"])
        was, self._was_on = self._was_on, on
        if on and not was:
            self._tick_circadian()                 # just turned on: start at the right white
