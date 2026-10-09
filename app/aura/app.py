"""Aura startup: single instance, system tray, global shortcuts and quick commands."""

from __future__ import annotations

import getpass
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import APP_NAME, appicon, hotkey, startup, wiz
from . import theme as T
from .controller import Light
from .hotkey import GlobalHotkeys
from .i18n import set_language, t, t_name
from .pcevents import PcEvents
from .routines import SLEEP_CHOICES, Routines
from .sound import Player
from .store import Store

COMMANDS = ("toggle", "on", "off", "show")
USAGE = """Aura: control for WiZ lights

  Aura.exe            open the window
  Aura.exe --toggle   turn the light on or off, then exit
  Aura.exe --on       turn the light on, then exit
  Aura.exe --off      turn the light off, then exit
  Aura.exe --hidden   start straight in the tray
"""


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"aura-wiz-{user}"


def _send_to_running(command: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(300):
        return False
    sock.write(command.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _headless(command: str, store: Store) -> int:
    """Turn the light on/off without opening the window (for shortcuts)."""
    info = store.active_light()
    if not info:
        return 2
    ip = info["ip"]
    if command == "toggle":
        pilot = wiz.get_pilot(ip, timeout=0.6, attempts=2)
        on = not bool(pilot.get("state", True)) if pilot is not None else not store.data["state"].get("on", True)
    else:
        on = command == "on"
    sender = wiz.Sender()
    import time
    for _ in range(3):
        sender.send(ip, "setPilot", {"state": on})
        time.sleep(0.08)
    sender.close()
    store.data["state"]["on"] = on
    store.save()
    return 0


class AuraApp:
    def __init__(self, qt: QApplication, store: Store, start_hidden: bool):
        self.qt = qt
        self.store = store
        set_language(store.settings.get("language", "en"))
        self.light = Light(store)
        qt.setWindowIcon(appicon.app_icon())
        startup.refresh()           # the folder may have been moved since the last run

        # A second copy of Aura (or a shortcut with --toggle) sends its commands here.
        self.server = QLocalServer()
        QLocalServer.removeServer(_server_name())
        self.server.listen(_server_name())
        self.server.newConnection.connect(self._incoming)

        self.sound = Player(data_dir=store.dir, style=store.settings.get("sound"))
        self.light.userChanged.connect(self._user_changed)

        self.hotkeys = GlobalHotkeys(qt)
        self.hotkeys.activated.connect(self.run_action)
        for action in hotkey.ACTIONS:
            self.hotkeys.set(action, (store.settings.get("hotkeys") or {}).get(action, ""))
        self._fav_index = -1

        self.pc = PcEvents(qt)
        self.routines = Routines(self.light, store, self.pc)

        self.tray = None
        self.menu = None
        self._tray_key = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(qt)
            self.tray.activated.connect(self._tray_activated)

        self.window = None
        self._build_window()
        if self.tray is not None:
            self._build_menu()
            self.tray.show()

        self.light.changed.connect(self._refresh_tray)
        self.light.connectionChanged.connect(self._refresh_tray)
        self.light.effectChanged.connect(lambda _e: self._refresh_tray())
        self.light.discoveryFinished.connect(self._first_scan_done)
        self.routines.changed.connect(self._refresh_tray)
        qt.aboutToQuit.connect(self._cleanup)

        self._first_run_scan = False
        self.light.start()
        if not (start_hidden and self.tray is not None):
            self.show()
        if not store.lights:
            self._first_run_scan = True
            QTimer.singleShot(250, self._present_devices)

    def _present_devices(self):
        self.window.devices.present()

    def _build_window(self):
        """Create the main window. Called again when the language changes."""
        from .window import MainWindow

        w = MainWindow(self.light, self.store, self.routines)
        w.setWindowIcon(appicon.app_icon())
        w.tray_available = self.tray is not None
        w.quitRequested.connect(self.quit)
        w.closedToTray.connect(self._closed_to_tray)
        w.settings.hotkeyChanged.connect(self._apply_hotkey)
        w.settings.languageChanged.connect(self._set_language)
        w.settings.soundsChanged.connect(self._set_sounds)
        w.settings.hotkey_results(self.hotkeys.ok, self.hotkeys.supported)
        self.window = w
        return w

    def _set_language(self, code: str):
        if code == self.store.settings.get("language", "en"):
            return
        self.store.settings["language"] = code
        self.store.save()
        set_language(code)
        self._rebuild_window()

    def _set_sounds(self, style: str, kind: str):
        self.sound.style = style
        self.sound.play(kind)           # let them hear what they just picked (silent when off)

    def _rebuild_window(self):
        """Swap in a fresh window (new language), keeping its place on screen."""
        old = self.window
        visible, pos = old.isVisible(), old.pos()
        new = self._build_window()
        new.move(pos)
        if visible:
            new.show()
            new.settings.present()
        old.hide()
        old.deleteLater()
        if self.tray is not None:
            self._build_menu()

    # -- window ----------------------------------------------------------------
    def show(self):
        w = self.window
        w.show()
        w.setWindowState(w.windowState() & ~Qt.WindowState.WindowMinimized)
        w.raise_()
        w.activateWindow()
        self.light.sync()

    def quit(self):
        self.window.really_quit = True
        self.qt.quit()

    def _cleanup(self):
        self.hotkeys.clear()
        self.pc.close()
        self.light.shutdown()
        if self.tray is not None:
            self.tray.hide()
        self.server.close()

    def _closed_to_tray(self):
        if self.tray is not None and not self.store.settings.get("tray_hint_shown"):
            self.store.settings["tray_hint_shown"] = True
            self.store.save()
            self.tray.showMessage(
                t("Aura is still running"),
                t("It stays here, next to the clock. Right-click the icon to quit."),
                appicon.app_icon(), 5000)

    def _first_scan_done(self, _count):
        """First run: if there is exactly one light on the network, use it without asking."""
        if not self._first_run_scan:
            return
        self._first_run_scan = False
        sheet = self.window.devices
        if not self.store.lights and len(sheet.found) == 1:
            sheet._adopt(next(iter(sheet.found.values())))

    def _user_changed(self, keys):
        # Only when the person flips the light, never when a routine does.
        if "on" in keys:
            self.sound.play("on" if self.light.state["on"] else "off")

    # -- commands --------------------------------------------------------------
    def _incoming(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return

        def read():
            cmd = bytes(conn.readAll()).decode("utf-8", "replace").strip()
            if cmd:
                self.run_command(cmd)
            conn.disconnectFromServer()

        conn.readyRead.connect(read)
        if conn.bytesAvailable():
            read()

    def run_command(self, cmd: str):
        if cmd == "toggle":
            self.light.toggle()
        elif cmd == "on":
            self.light.set_power(True)
        elif cmd == "off":
            self.light.set_power(False)
        else:
            self.show()

    def run_action(self, action: str):
        """A global shortcut was pressed."""
        if not self.light.info:
            self.show()
            return
        if action == "toggle":
            self.light.toggle()
        elif action == "brighter":
            self.light.step_brightness(10)
        elif action == "dimmer":
            self.light.step_brightness(-10)
        elif action == "next":
            self.next_favorite()

    def favorites(self) -> list[dict]:
        """Every favorite in the order the shortcut walks through them: colors, then whites."""
        fav = self.store.favorites
        return [{"mode": "rgb", "rgb": tuple(f["rgb"])} for f in fav["rgb"]] + \
               [{"mode": "white", "temp": int(f["temp"]), "brightness": int(f.get("brightness", 100))}
                for f in fav["white"]]

    def next_favorite(self):
        favs = self.favorites()
        if not favs:
            return
        st = self.light.state
        # Continue from the favorite the light is on now, if it is on one.
        for i, f in enumerate(favs):
            if all(st.get(k) == v for k, v in f.items()):
                self._fav_index = i
                break
        self._fav_index = (self._fav_index + 1) % len(favs)
        self.light.update(on=True, **favs[self._fav_index])

    def _toggle(self):
        self.run_action("toggle")

    def _apply_hotkey(self, action: str, combo: str):
        self.hotkeys.set(action, combo)
        self.window.settings.hotkey_results(self.hotkeys.ok, self.hotkeys.supported)
        self.window.refresh()

    # -- tray ------------------------------------------------------------------
    def _build_menu(self):
        self.menu = T.make_menu()
        self.menu.setStyleSheet(T.stylesheet())
        self.act_open = QAction(t("Open Aura"), self.menu)
        self.act_open.triggered.connect(self.show)
        self.act_power = QAction(t("Turn on"), self.menu)
        self.act_power.triggered.connect(self._toggle)
        self.act_stop = QAction(t("Stop the effect"), self.menu)
        self.act_stop.triggered.connect(lambda: self.light.stop_effect())
        self.bright_menu = T.make_menu(self.menu, t("Brightness"))
        for pct in (100, 75, 50, 25, 10):
            a = self.bright_menu.addAction(f"{pct}%")
            a.triggered.connect(lambda _=False, v=pct: self.light.update(brightness=v, on=True))
        self.fav_menu = T.make_menu(self.menu, t("Favorites"))
        self.fav_menu.aboutToShow.connect(self._fill_favorites)
        self.sleep_menu = T.make_menu(self.menu, t("Sleep timer"))
        for minutes in SLEEP_CHOICES:
            a = self.sleep_menu.addAction(t("{n} minutes", n=minutes))
            a.triggered.connect(lambda _=False, m=minutes: self.routines.start_sleep(m))
        self.sleep_menu.addSeparator()
        self.act_sleep_cancel = self.sleep_menu.addAction(t("Cancel the timer"))
        self.act_sleep_cancel.triggered.connect(lambda: self.routines.cancel_sleep())
        act_quit = QAction(t("Quit"), self.menu)
        act_quit.triggered.connect(self.quit)
        self.menu.addAction(self.act_power)
        self.menu.addMenu(self.bright_menu)
        self.menu.addMenu(self.fav_menu)
        self.menu.addMenu(self.sleep_menu)
        self.menu.addAction(self.act_stop)
        self.menu.addSeparator()
        self.menu.addAction(self.act_open)
        self.menu.addAction(act_quit)
        self.tray.setContextMenu(self.menu)
        self._tray_key = None
        self._refresh_tray()

    def _fill_favorites(self):
        self.fav_menu.clear()
        for f in self.store.favorites["rgb"]:
            a = self.fav_menu.addAction(t(f["name"]))
            a.triggered.connect(lambda _=False, fav=f: self.light.update(
                on=True, mode="rgb", rgb=tuple(fav["rgb"])))
        self.fav_menu.addSeparator()
        for f in self.store.favorites["white"]:
            a = self.fav_menu.addAction(f'{t(f["name"])} ({f["temp"]} k)')
            a.triggered.connect(lambda _=False, fav=f: self.light.update(
                on=True, mode="white", temp=int(fav["temp"]), brightness=int(fav.get("brightness", 100))))

    def _tray_activated(self, reason):
        R = QSystemTrayIcon.ActivationReason
        if reason == R.Trigger:
            if self.store.settings.get("tray_click", "toggle") == "toggle":
                self._toggle()
            else:
                self.show()
        elif reason in (R.DoubleClick, R.MiddleClick):
            self.show()

    def _refresh_tray(self):
        if self.tray is None or self.menu is None:
            return
        light = self.light
        has = light.info is not None
        on = bool(light.state["on"]) and has
        available = has and light.connected is not False
        rgb = light.display_rgb()
        key = (rgb, on, available)
        if key != self._tray_key:
            self._tray_key = key
            self.tray.setIcon(appicon.tray_icon(QColor(*rgb), on, available))
        self.act_power.setText(t("Turn off") if on else t("Turn on"))
        self.act_power.setEnabled(has)
        self.bright_menu.setEnabled(has)
        self.fav_menu.setEnabled(has)
        self.sleep_menu.setEnabled(has)
        self.act_sleep_cancel.setEnabled(self.routines.sleep_active)
        self.act_stop.setVisible(light.runner is not None)
        if not has:
            tip = t("Aura: no light selected yet")
        elif not available:
            tip = t("{name}: offline", name=t_name(light.name))
        elif on:
            tip = t("{name}: on at {pct}%", name=t_name(light.name), pct=light.state["brightness"])
            if self.routines.sleep_active:
                tip += "\n" + t("Turns off in {n} min", n=self.routines.sleep_remaining())
        else:
            tip = t("{name}: off", name=t_name(light.name))
        self.tray.setToolTip(tip)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = {a.lstrip("-").lower() for a in argv if a.startswith("-")}
    if flags & {"h", "help", "?"}:
        print(USAGE)
        return 0
    command = next((c for c in ("toggle", "on", "off") if c in flags), None)

    qt = QApplication(sys.argv[:1])
    qt.setApplicationName(APP_NAME)
    qt.setApplicationDisplayName(APP_NAME)
    qt.setQuitOnLastWindowClosed(False)

    # If Aura is already running, hand it the command and exit.
    if _send_to_running(command or "show"):
        return 0

    store = Store()
    if command:
        return _headless(command, store)

    T.load_fonts()
    qt.setFont(T.font(13))
    qt.setStyleSheet(T.stylesheet())
    qt._focus_filter = T.KeyboardFocusFilter(qt)
    qt.installEventFilter(qt._focus_filter)
    app = AuraApp(qt, store, start_hidden="hidden" in flags)
    qt._aura = app          # keep the reference alive
    return qt.exec()
