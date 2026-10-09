"""Functional test: real clicks on the interface, checking what the bulb receives."""
import os, sys, time, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["AURA_FAKE_AUDIO"] = "1"
home = tempfile.mkdtemp(); os.environ["AURA_HOME"] = home
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app")); sys.path.insert(0, HERE)
from fakebulb import FakeBulb
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
bulb = FakeBulb(); bulb.start()
from aura.store import Store
from aura import theme as T
st = Store(); l = st.upsert_light("a8bb50aabbcc", "127.0.0.1", name="Velador"); st.data["active"] = l["mac"]; st.save()
qt = QApplication(sys.argv[:1]); qt.setQuitOnLastWindowClosed(False)
T.load_fonts(); qt.setStyleSheet(T.stylesheet())
from aura.app import AuraApp
app = AuraApp(qt, st, False); w = app.window; light = app.light
def wait(ms):
    t = time.time() + ms / 1000
    while time.time() < t: qt.processEvents(); time.sleep(0.003)
def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond: check.failed += 1
check.failed = 0
wait(700)
check(light.connected is True, "connects and reads the state")
check(light.state["temp"] == 2700 and light.state["brightness"] == 80, "initial state read from the bulb")
# power button
c = QPoint(w.orb.width() // 2, w.orb.height() // 2)
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(400)
check(bulb.pilot["state"] is False, "clicking the circle turns it off")
check(w.title.text() == "off", "title is 'off'")
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=QPoint(8, 8)); wait(300)
check(bulb.pilot["state"] is False, "clicking outside the circle does nothing")
QTest.keyClick(w, Qt.Key.Key_Space); wait(400)
check(bulb.pilot["state"] is True, "space bar turns it on")
# brightness
n0 = len(bulb.log)
QTest.mousePress(w.bright, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
for x in range(40, 200, 8):
    QTest.mouseMove(w.bright, QPoint(x, 20)); wait(12)
QTest.mouseRelease(w.bright, Qt.MouseButton.LeftButton, pos=QPoint(200, 20)); wait(500)
sent = [x for x in bulb.log[n0:] if x[1] == "setPilot"]
check(bulb.pilot["dimming"] == light.state["brightness"] and 70 <= bulb.pilot["dimming"] <= 80, f"dragging the brightness -> {bulb.pilot['dimming']}% ({len(sent)} sends)")
check(len(sent) < 14, "sends are throttled while dragging")
# tabs and wheel
cw = w.tabs.width() / 5
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cw * 0.5), 20)); wait(300)
check(w.pages.currentIndex() == 0, "Color tab")
wh = w.color_page.wheel
QTest.mouseClick(wh, Qt.MouseButton.LeftButton, pos=QPoint(wh.width() - 6, wh.height() // 2)); wait(500)
check(bulb.pilot.get("r") == 255 and bulb.pilot.get("g", 99) < 12 and bulb.pilot.get("b", 99) < 12, f"wheel to the right = red {bulb.pilot.get('r'), bulb.pilot.get('g'), bulb.pilot.get('b')}")
sw = w.color_page.swatches[3]
QTest.mouseClick(sw, Qt.MouseButton.LeftButton); wait(500)
check((bulb.pilot["r"], bulb.pilot["g"], bulb.pilot["b"]) == (0, 60, 255), "Blue favorite")
check(w.sub.text() == "blue" and sw.selected, "subtitle and selection of the favorite")
w.color_page.hex.setFocus(); w.color_page.hex.setText("#00ff80"); QTest.keyClick(w.color_page.hex, Qt.Key.Key_Return); wait(500)
check((bulb.pilot["r"], bulb.pilot["g"], bulb.pilot["b"]) == (0, 255, 128), "hex code")
nfav = len(st.favorites["rgb"])
w.color_page._add(); check(len(st.favorites["rgb"]) == nfav + 1 and len(w.color_page.swatches) == nfav + 1, "save a favorite")
w.setFocus()
# white
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cw * 1.5), 20)); wait(250)
ts = w.white_page.slider
QTest.mouseClick(ts, Qt.MouseButton.LeftButton, pos=QPoint(ts.width() - 5, 30)); wait(500)
check(bulb.pilot.get("temp") == 6500 and "r" not in bulb.pilot, "temperature at maximum = 6500 K")
QTest.mouseClick(w.white_page.tiles[0], Qt.MouseButton.LeftButton); wait(500)
check(bulb.pilot.get("temp") == 2200 and bulb.pilot["dimming"] == 40, "Candle favorite (2200 K at 40%)")
# scenes
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cw * 2.5), 20)); wait(250)
tile = next(t for t in w.scenes_page.tiles if t.name == "fireplace")
QTest.mouseClick(tile, Qt.MouseButton.LeftButton); wait(500)
check(bulb.pilot.get("sceneId") == 5, "Fireplace scene (id 5)")
check(w.scenes_page.speed.isVisible(), "the speed control appears for scenes with motion")
# effects
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cw * 3.5), 20)); wait(250)
ep = w.effects_page
light.update(brightness=100); wait(300)
QTest.mouseClick(ep.music_tiles["pulse"], Qt.MouseButton.LeftButton); wait(100)
QTest.mouseClick(ep.go, Qt.MouseButton.LeftButton); wait(1500)
check(light.runner is not None and ep.go.text() == "stop", "starts the music effect")
n0 = len(bulb.log); wait(2000)
frames = [x[2] for x in bulb.log[n0:] if x[1] == "setPilot"]
dims = [f["dimming"] for f in frames]
check(8 <= len(frames) / 2 <= 17, f"send rate {len(frames) / 2:.1f}/s")
check(max(dims) - min(dims) > 30, f"the brightness pulses ({min(dims)}–{max(dims)}%)")
light.update(brightness=40); wait(300); t0 = time.monotonic(); wait(1200)
dims = [x[2]["dimming"] for x in bulb.log if x[1] == "setPilot" and x[0] > t0]
check(max(dims) <= 40, f"the overall brightness caps the effect (max {max(dims)}%)")
light.update(brightness=100)
QTest.mouseClick(ep.music_tiles["rainbow"], Qt.MouseButton.LeftButton); wait(900)
check(light.runner is not None and light.runner.options["mode"] == "rainbow", "changing the mode restarts the effect")
r0 = light.runner; ep._set("music", "sensitivity", 2.0); wait(200)
check(light.runner is r0 and r0.options["sensitivity"] == 2.0, "sensitivity is adjusted live, without restarting")
for mode in ("spectrum", "energy", "spectrum_pulse", "strobe"):
    QTest.mouseClick(ep.music_tiles[mode], Qt.MouseButton.LeftButton); wait(700)
    check(light.runner is not None and light.runner.is_alive(), f"{mode} mode runs")
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(700)
check(light.runner is None and bulb.pilot["state"] is False, "turning off during an effect stops it and turns the light off")
wait(500); check(bulb.pilot["state"] is False, "stays off (the effect does not turn it back on)")
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(400)
check(bulb.pilot["state"] is True and bulb.pilot.get("sceneId") == 5, "turning on brings back the previous scene")
# changes made from outside (the phone app)
bulb.pilot = {"state": True, "sceneId": 0, "r": 10, "g": 200, "b": 30, "c": 0, "w": 0, "dimming": 33}
wait(1700); light.sync(); wait(900)
check(light.state["mode"] == "rgb" and light.state["brightness"] == 33, "reflects changes made from another app")
# quick commands, tray, shortcut
app.run_command("off"); wait(350); check(bulb.pilot["state"] is False, "'off' command")
app.run_command("toggle"); wait(350); check(bulb.pilot["state"] is True, "'toggle' command")
if app.tray is not None:
    app._tray_activated(app.tray.ActivationReason.Trigger); wait(350)
    check(bulb.pilot["state"] is False, "clicking the tray icon turns it off")
    app._fill_favorites(); check(len(app.fav_menu.actions()) > 8, "favorites menu in the tray")
else:
    print("     (no tray in this environment)")
hk = w.settings.keys["toggle"]; w.settings.tabs.setIndex(2, emit=True)
w.settings.present(); QTest.mouseClick(hk, Qt.MouseButton.LeftButton); wait(50)
QTest.keyClick(hk, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier); wait(50)
check(st.settings["hotkeys"]["toggle"] == "Ctrl+Shift+K" and app.hotkeys.combos["toggle"] == "Ctrl+Shift+K", f"shortcut capture -> {st.settings['hotkeys']['toggle']}")
QTest.mouseClick(hk, Qt.MouseButton.LeftButton); QTest.keyClick(hk, Qt.Key.Key_L); wait(50)
check(st.settings["hotkeys"]["toggle"] == "Ctrl+Shift+K" and hk.listening, "a single letter is not accepted as a shortcut")
QTest.keyClick(hk, Qt.Key.Key_Escape); w.settings.dismiss()
from aura import hotkey
check(hotkey.parse("Ctrl+Alt+L") == (3, 0x4C) and hotkey.parse("F9") == (0, 0x78) and hotkey.parse("Ctrl+??") is None, "shortcut parsing")
# rename the light
w.devices.present(); wait(100); w.devices._rename(l["mac"], "Living"); wait(50)
check(w.device._label() == "living" and st.lights[0]["name"] == "Living", "renaming the light: saved as typed and shown in lowercase")
w.devices.ip.setText("300.1.1.1"); w.devices._add_ip(); check(w.devices.ip_msg.isVisible(), "an invalid IP shows a warning")
w.devices.dismiss()
# interface language and color, changed live
import io, contextlib
w.settings.present(); wait(100)
check(w.tabs.labels == ["color", "white", "scenes", "effects", "routines"] and st.settings["language"] == "en", "starts in English")
w.settings.tabs.setIndex(0, emit=True); wait(50)
old_w = w
lw = w.settings.lang.width() / 2
QTest.mouseClick(w.settings.lang, Qt.MouseButton.LeftButton, pos=QPoint(int(lw * 1.5), 18)); wait(500)
w = app.window
check(w is not old_w and w.tabs.labels == ["color", "blanco", "escenas", "efectos", "rutinas"], "switches to Spanish without restarting")
check(w.isVisible() and w.settings.isVisible() and not old_w.isVisible(), "the new window stays open on Settings")
check(w.title.text() in ("encendida", "apagada") and w.effects_page.go.text() == "iniciar", f"texts in Spanish ({w.title.text()})")
check(w.scenes_page.tiles[0].name == "acogedor" and w.device._label() == "living", "scenes translated, custom name left intact")
err = io.StringIO()
with contextlib.redirect_stderr(err):
    light.update(mode="rgb", rgb=(10, 250, 90), brightness=70); wait(400); light.toggle(); wait(300); light.toggle(); wait(300)
    w.effects_page.toggle(); wait(900); w.effects_page.toggle(); wait(400)
check(err.getvalue() == "" and (bulb.pilot["r"], bulb.pilot["g"]) == (10, 250), "the previous window leaves no dangling connections")
from PySide6.QtGui import QColor
check(T.theme().accent == QColor("#ffffff") and T.BG.name() == "#0a0a0a" and not hasattr(w.settings, "theme"), "only the monochrome interface remains")
b0 = light.state["brightness"]; w.orb.nudged.emit(-1); wait(400)
check(light.state["brightness"] < b0 and bulb.pilot["dimming"] == light.state["brightness"], "mouse wheel over the lamp lowers the brightness")
lw = w.settings.lang.width() / 2
QTest.mouseClick(w.settings.lang, Qt.MouseButton.LeftButton, pos=QPoint(int(lw * 0.5), 18)); wait(500)
w = app.window; check(w.tabs.labels[1] == "white", "switches back to English"); w.settings.dismiss()
# persistence
app.light._persist(); s2 = Store()
check(s2.active_light()["name"] == "Living" and s2.settings["hotkeys"]["toggle"] == "Ctrl+Shift+K", "everything is saved in data/aura.json")
check(os.listdir(home) == ["data"], f"portable mode: writes only to the program folder {os.listdir(home)}")
# close
app._cleanup(); wait(200)
print("CHECKS FAILED:", check.failed)
sys.exit(1 if check.failed else 0)
