"""Tests for the newer features: routines, custom scenes, shortcuts, sound and settings."""
import contextlib, ctypes, datetime, io, json, os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["AURA_FAKE_AUDIO"] = "1"
home = tempfile.mkdtemp(); os.environ["AURA_HOME"] = home
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app")); sys.path.insert(0, HERE)
from fakebulb import FakeBulb
from PySide6.QtCore import Qt, QPoint, QByteArray
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import shiboken6

# migration of settings from the previous version
os.makedirs(os.path.join(home, "data"))
json.dump({"settings": {"hotkey": "Ctrl+Alt+J", "theme": "purple", "language": "en"},
           "lights": [{"mac": "a8bb50aabbcc", "ip": "127.0.0.1", "name": "Velador", "model": "WiZ color light"}],
           "active": "a8bb50aabbcc"}, open(os.path.join(home, "data", "aura.json"), "w"))
bulb = FakeBulb(); bulb.start()
from aura.store import Store
from aura import theme as T, routines as R, hotkey, pcevents, startup, sound, i18n
st = Store()
def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond: check.failed += 1
check.failed = 0
check(st.settings["hotkeys"]["toggle"] == "Ctrl+Alt+J" and "theme" not in st.settings and "hotkey" not in st.settings
      and st.settings["hotkeys"]["brighter"] == "Ctrl+Alt+PageUp", "migrates the old shortcut and drops the theme")
st.settings["hotkeys"]["toggle"] = "Ctrl+Alt+L"

qt = QApplication(sys.argv[:1]); qt.setQuitOnLastWindowClosed(False)
T.load_fonts(); qt.setStyleSheet(T.stylesheet())
from aura.app import AuraApp
app = AuraApp(qt, st, False); w = app.window; light = app.light; rt = app.routines
def wait(ms):
    t = time.time() + ms / 1000
    while time.time() < t: qt.processEvents(); time.sleep(0.003)
wait(700)
check(light.connected is True, "connects to the light")
light.update(mode="white", temp=2700, brightness=80); wait(400)

# ---------------------------------------------------------------- sound
app.sound.played.clear()
c = QPoint(w.orb.width() // 2, w.orb.height() // 2)
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(300)
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(300)
check(app.sound.played == ["cream:off", "cream:on"] and bulb.pilot["state"] is True, f"plays a sound when turning off and on {app.sound.played}")
light.set_power(False, auto=True); light.set_power(True, auto=True); wait(200)
check(app.sound.played == ["cream:off", "cream:on"], "a routine plays no sound")
light.update(brightness=70); wait(100)
check(app.sound.played == ["cream:off", "cream:on"], "changing the brightness plays no sound")
import wave as _wave
def _wav_ok(path):
    with _wave.open(path) as f:      # what Windows' player needs: plain 16-bit PCM
        return (f.getsampwidth() == 2 and f.getframerate() == 44100 and f.getnchannels() in (1, 2)
                and 0.10 < f.getnframes() / 44100 < 0.40)
check(len(sound.STYLES) == 13 and all(_wav_ok(sound.path_for(s_, k)) for s_ in sound.STYLES for k in ("on", "off")),
      "13 recorded sounds, each with its on and off as PCM WAV")
check(sorted(os.listdir(sound.HERE)) == sorted([f"{s_}_{k}.wav" for s_ in sound.STYLES for k in ("on", "off")] + ["LICENSES.txt"]),
      "the sounds folder has no extra files")
ws = w.settings
ws.present(); wait(100)
ws.tabs.setIndex(1, emit=True); wait(100)
tiles = ws.sound_tiles
check(list(tiles)[:1] == ["cream"] and list(tiles)[-2:] == ["custom", "off"] and len(tiles) == 15,
      "Sound tab: 13 keyboards, custom and none")
check(tiles["cream"].selected and [k for k, v in tiles.items() if v.selected] == ["cream"], "NK Cream by default")
app.sound.played.clear()
QTest.mouseClick(tiles["holypanda"], Qt.MouseButton.LeftButton); wait(100)
check(st.settings["sound"] == "holypanda" and app.sound.played == ["holypanda:on"] and tiles["holypanda"].selected
      and not tiles["cream"].selected, f"clicking one selects it and plays it {app.sound.played}")
QTest.mouseClick(tiles["holypanda"], Qt.MouseButton.LeftButton); wait(100)
QTest.mouseClick(tiles["holypanda"], Qt.MouseButton.LeftButton); wait(100)
check(app.sound.played == ["holypanda:on", "holypanda:off", "holypanda:on"], f"another click plays the off sound {app.sound.played}")
app.sound.played.clear(); light.toggle(); light.toggle(); wait(200)
check(sorted(app.sound.played) == ["holypanda:off", "holypanda:on"], f"the light uses the chosen sound {app.sound.played}")
QTest.mouseClick(tiles["off"], Qt.MouseButton.LeftButton); wait(100)
check(st.settings["sound"] == "off" and app.sound.enabled is False, "none can be chosen")
app.sound.played.clear(); light.toggle(); light.toggle(); wait(200)
check(app.sound.played == [], "with sound off nothing plays")
# custom sound: with no files it opens the folder and explains; with files it is selected and plays
opened = []
ws._open_folder = opened.append
QTest.mouseClick(tiles["custom"], Qt.MouseButton.LeftButton); wait(100)
custom_dir = os.path.join(st.dir, "sounds")
check(opened == [custom_dir] and os.path.isdir(custom_dir) and st.settings["sound"] == "off"
      and "on.wav" in ws.sound_intro.text() and not tiles["custom"].selected, "custom with no files: opens the folder and explains")
import shutil as _sh
_sh.copy(sound.path_for("mxblue", "on"), os.path.join(custom_dir, "on.wav"))
QTest.mouseClick(tiles["custom"], Qt.MouseButton.LeftButton); wait(100)
check(st.settings["sound"] == "custom" and app.sound.played == ["custom:on"] and tiles["custom"].selected
      and "on.wav" not in ws.sound_intro.text() and app.sound.file("off") == os.path.join(custom_dir, "on.wav"),
      "custom with on.wav: selected, plays, and is also used for turning off")
_sh.copy(sound.path_for("mxblue", "off"), os.path.join(custom_dir, "off.wav"))
check(app.sound.file("off") == os.path.join(custom_dir, "off.wav"), "with off.wav, that one is used for turning off")
_sh.rmtree(custom_dir)
app.sound.played.clear(); light.toggle(); light.toggle(); wait(200)
check(app.sound.played == [], "if the custom files are deleted, it neither fails nor plays")
QTest.mouseClick(tiles["cream"], Qt.MouseButton.LeftButton); wait(100)
check(st.settings["sound"] == "cream" and app.sound.style == "cream", "back to NK Cream")
ws.tabs.setIndex(0, emit=True); wait(50)
# settings saved by earlier versions are carried over
from aura.store import Store as _S
import json as _json, tempfile as _tmp
for _old, _want in (({"sounds": True}, "cream"), ({"sounds": False}, "off"), ({"sound": "thock"}, "cream"),
                    ({"sound": "clack"}, "cream"), ({"sound": "off"}, "off"), ({"sound": "topre"}, "topre"),
                    ({"sound": "custom"}, "custom"), ({}, "cream")):
    _d = _tmp.mkdtemp()
    _json.dump({"settings": _old}, open(os.path.join(_d, "aura.json"), "w"))
    _st = _S(_d)
    check(_st.settings.get("sound") == _want and "sounds" not in _st.settings, f"migrates {_old} to {_want}")

# ---------------------------------------------------------------- brightness dial around the button
orb = w.orb
ws.dismiss(); wait(200)
light.set_power(True); light.update(brightness=80); wait(400)
mid = QPoint(orb.width() // 2, orb.height() // 2)
check(orb.zone_at(mid) == "lamp" and orb.zone_at(orb.dial_point(50)) == "dial" and orb.zone_at(QPoint(2, 2)) == "",
      "button zones: lamp, dial and nothing")
check(abs(orb.value_at(orb.dial_point(50)) - 50) <= 1 and orb.value_at(orb.dial_point(10)) == 10
      and orb.value_at(orb.dial_point(100)) == 100, "the dial converts the angle to brightness")
gap_left = QPoint(int(orb.width() / 2 - 60), int(orb.height() / 2 + 95)); gap_right = QPoint(int(orb.width() / 2 + 60), int(orb.height() / 2 + 95))
check(orb.value_at(gap_left) == 10 and orb.value_at(gap_right) == 100, "in the gap at the bottom it goes to the nearest end")
app.sound.played.clear()
QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=orb.dial_point(40).toPoint()); wait(500)
check(abs(light.state["brightness"] - 40) <= 2 and abs(bulb.pilot["dimming"] - 40) <= 2 and bulb.pilot["state"] is True
      and app.sound.played == [], f"clicking the dial: brightness 40 without turning off or playing a sound ({light.state['brightness']}, {bulb.pilot['dimming']})")
QTest.mousePress(orb, Qt.MouseButton.LeftButton, pos=orb.dial_point(40).toPoint()); wait(30)
for v in (50, 60, 70, 85):
    QTest.mouseMove(orb, orb.dial_point(v).toPoint()); wait(60)
QTest.mouseRelease(orb, Qt.MouseButton.LeftButton, pos=orb.dial_point(85).toPoint()); wait(500)
check(abs(light.state["brightness"] - 85) <= 2 and abs(bulb.pilot["dimming"] - 85) <= 2 and abs(w.bright.value() - 85) <= 2,
      f"dragging the dial: brightness 85 and the slider follows ({light.state['brightness']}, {bulb.pilot['dimming']})")
QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=mid); wait(300)
check(bulb.pilot["state"] is False and app.sound.played == ["cream:off"], "the center still turns it off")
QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=mid); wait(300)
check(bulb.pilot["state"] is True, "and turns it on")
img = orb.grab().toImage()
check(img.width() > 0, "the button is drawn")

# ---------------------------------------------------------------- settings
check(w.settings.tabs.labels == ["general", "sound", "shortcuts", "about"], "settings in four sections")
check(not w.settings.startup.isEnabled() and not startup.supported() and startup.is_enabled() is False
      and startup.set_enabled(True) is False, "start with Windows: disabled outside Windows")
check('Aura.exe" --hidden' in startup.command() or "--hidden" in startup.command(), f"startup command: {startup.command()[-40:]}")
w.settings.tabs.setIndex(2, emit=True); wait(100)
check(list(w.settings.keys) == ["toggle", "brighter", "dimmer", "next"]
      and w.settings.keys["brighter"].value == "Ctrl+Alt+PageUp", "four configurable shortcuts")
hk = w.settings.keys["next"]
QTest.mouseClick(hk, Qt.MouseButton.LeftButton); wait(50)
QTest.keyClick(hk, Qt.Key.Key_F8, Qt.KeyboardModifier.ControlModifier); wait(50)
check(st.settings["hotkeys"]["next"] == "Ctrl+F8" and app.hotkeys.combos["next"] == "Ctrl+F8", "changing the next-favorite shortcut")
w.settings.dismiss()

# ---------------------------------------------------------------- shortcuts
check(hotkey.parse("Ctrl+Alt+PageUp") == (3, 0x21) and hotkey.parse("Ctrl+Alt+K") == (3, 0x4B), "keys of the new shortcuts")
f = hotkey._Filter(lambda a: hits.append(a)); hits = []
from ctypes import wintypes
msg = wintypes.MSG(); msg.message = hotkey.WM_HOTKEY
for i, name in enumerate(hotkey.ACTIONS):
    msg.wParam = hotkey.BASE_ID + i
    f.nativeEventFilter(QByteArray(b"windows_generic_MSG"), shiboken6.VoidPtr(ctypes.addressof(msg)))
msg.wParam = hotkey.BASE_ID + 9
f.nativeEventFilter(QByteArray(b"windows_generic_MSG"), shiboken6.VoidPtr(ctypes.addressof(msg)))
check(hits == list(hotkey.ACTIONS), f"the Windows message is translated into the action {hits}")
light.update(brightness=50); wait(300)
app.run_action("brighter"); wait(300)
check(bulb.pilot["dimming"] == 60, "shortcut: brighter (+10)")
app.run_action("dimmer"); app.run_action("dimmer"); wait(400)
check(bulb.pilot["dimming"] == 40, "shortcut: dimmer (-10)")
light.update(brightness=100); app.run_action("brighter"); wait(300)
check(bulb.pilot["dimming"] == 100, "the brightness does not go above 100")
light.update(mode="rgb", rgb=(1, 2, 3)); wait(300)
app.run_action("next"); wait(400)
check((bulb.pilot["r"], bulb.pilot["g"], bulb.pilot["b"]) == (255, 120, 40), "shortcut: first favorite")
app.run_action("next"); wait(400)
check((bulb.pilot["r"], bulb.pilot["g"], bulb.pilot["b"]) == (255, 70, 140), "shortcut: next favorite")
light.update(mode="rgb", rgb=tuple(st.favorites["rgb"][-1]["rgb"])); wait(300); app.run_action("next"); wait(400)
check(bulb.pilot.get("temp") == 2200 and bulb.pilot["dimming"] == 40, "after the colors come the whites")
n = len(app.favorites()); light.update(mode="white", temp=6500, brightness=100); wait(300); app.run_action("next"); wait(400)
check(n == 13 and (bulb.pilot["r"], bulb.pilot["g"]) == (255, 120), "from the last one it wraps around to the first")
app.run_action("toggle"); wait(300); check(bulb.pilot["state"] is False, "shortcut: turn off"); app.run_action("toggle"); wait(300)

# ---------------------------------------------------------------- sleep timer
clock = [1000.0]; rt.clock = lambda: clock[0]
light.update(mode="white", temp=2700, brightness=90); wait(400)
app.sound.played.clear()
cwid = w.tabs.width() / 5
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cwid * 4.5), 20)); wait(250)
rp = w.routines_page
check(w.pages.currentWidget() is rp and rp.sleep_btn.text() == "start", "Routines tab")
QTest.mouseClick(rp.sleep_len, Qt.MouseButton.LeftButton, pos=QPoint(int(rp.sleep_len.width() * 0.6), 15)); wait(100)
QTest.mouseClick(rp.sleep_btn, Qt.MouseButton.LeftButton); wait(200)
check(rt.sleep_active and rt.sleep_remaining() == 45 and rp.sleep_btn.text() == "cancel"
      and "45" in rp.sleep_desc.text() and "45 min" in w.sub.text(), f"starts at 45 min ({rp.sleep_desc.text()})")
clock[0] += 45 * 60 / 2; rt.tick(); wait(400)
check(bulb.pilot["dimming"] == 50 and rt.sleep_remaining() == 23, f"halfway through, the brightness is at half ({bulb.pilot['dimming']}%)")
light.update(brightness=30); wait(300)      # the person lowers it by hand
clock[0] += 45 * 60 / 4; rt.tick(); wait(400)
check(bulb.pilot["dimming"] == 20, f"if you lower it by hand it continues from there ({bulb.pilot['dimming']}%)")
clock[0] += 45 * 60; rt.tick(); wait(500)
check(bulb.pilot["state"] is False and not rt.sleep_active and light.state["brightness"] == 30
      and rp.sleep_btn.text() == "start", "when it ends it turns off and remembers the brightness for next time")
check(app.sound.played == [], "the timer turns off silently")
light.set_power(True); wait(300); check(bulb.pilot["dimming"] == 30, "turning on brings back the previous brightness")
rt.start_sleep(15); light.update(brightness=80); wait(200); clock[0] += 300; rt.tick(); wait(300)
rt.cancel_sleep(); wait(400)
check(not rt.sleep_active and bulb.pilot["dimming"] == 80 and bulb.pilot["state"] is True, "canceling restores the brightness")
rt.start_sleep(15); wait(100); light.set_power(False); wait(300)
check(not rt.sleep_active, "turning off by hand cancels the timer")
light.set_power(True); wait(300)

# ---------------------------------------------------------------- wake-up light
check(R.parse_time("7:05") == (7, 5) and R.parse_time("24:00") is None and R.parse_time("x") is None, "time parsing")
fake = [datetime.datetime(2026, 10, 9, 6, 30)]          # Friday
rt.now = lambda: fake[0]
light.set_power(False); wait(300)
rp.wake_time.setFocus(); rp.wake_time.setText("7:00"); w.setFocus(); wait(100)
QTest.mouseClick(rp.wake_on, Qt.MouseButton.LeftButton); wait(200)
check(st.data["routines"]["wake"] == {"enabled": True, "time": "07:00", "minutes": 20, "days": "daily"} and rp.wake_time.text() == "07:00",
      f"wake-up light configured {st.data['routines']['wake']}")
rt.tick(); wait(300)
check(bulb.pilot["state"] is False, "does nothing before it is time")
fake[0] = datetime.datetime(2026, 10, 9, 6, 40); rt.tick(); wait(400)
check(bulb.pilot["state"] is True and bulb.pilot.get("temp") == 2200 and bulb.pilot["dimming"] == 10, f"starts dim and warm {bulb.pilot}")
fake[0] = datetime.datetime(2026, 10, 9, 6, 50); rt.tick(); wait(400)
check(bulb.pilot["temp"] == 3100 and bulb.pilot["dimming"] == 55, f"halfway through {bulb.pilot['temp']} K, {bulb.pilot['dimming']}%")
fake[0] = datetime.datetime(2026, 10, 9, 7, 0, 3); rt.tick(); wait(400)
check(bulb.pilot["temp"] == 4000 and bulb.pilot["dimming"] == 100, "at the set time it reaches the maximum")
fake[0] = datetime.datetime(2026, 10, 9, 7, 5); rt.tick(); wait(300)
check(bulb.pilot["dimming"] == 100, "afterwards it does not touch anything again")
rt.set_wake(days="weekdays"); light.set_power(False, auto=True); wait(300)
fake[0] = datetime.datetime(2026, 10, 10, 6, 50); rt.tick(); wait(300)        # Saturday
check(bulb.pilot["state"] is False, "with 'weekdays' it does not run on Saturday")
fake[0] = datetime.datetime(2026, 10, 12, 6, 45); rt.tick(); wait(300)        # Monday
check(bulb.pilot["state"] is True, "and it does run on Monday")
light.update(brightness=70); wait(200)                                         # the person adjusts the light
fake[0] = datetime.datetime(2026, 10, 12, 6, 55); rt.tick(); wait(300)
check(bulb.pilot["dimming"] == 70, "if you adjust the light, today's wake-up light stops")
rt.set_wake(time="00:05", days="daily"); light.set_power(False, auto=True); wait(200)
fake[0] = datetime.datetime(2026, 10, 12, 23, 50); rt.tick(); wait(300)
check(bulb.pilot["state"] is True and bulb.pilot["dimming"] < 40, "works across midnight")
rt.set_wake(enabled=False); wait(100)

# ---------------------------------------------------------------- time of day
check([R.temp_for_hour(h) for h in (3, 7, 12, 19, 22, 23.5)] == [2300, 2700, 5500, 3800, 2500, 2300], "daily curve")
fake[0] = datetime.datetime(2026, 10, 12, 12, 0)
light.update(mode="rgb", rgb=(255, 0, 0)); wait(300)
QTest.mouseClick(rp.circadian, Qt.MouseButton.LeftButton); wait(400)
check(st.data["routines"]["circadian"] is True and bulb.pilot.get("temp") == 5500 and "r" not in bulb.pilot, f"turning it on switches to the midday white {bulb.pilot.get('temp')}")
fake[0] = datetime.datetime(2026, 10, 12, 20, 0); rt.tick(); wait(400)
check(bulb.pilot["temp"] == 3250, f"in the evening it gets warmer ({bulb.pilot['temp']} K)")
light.update(mode="rgb", rgb=(0, 0, 255)); wait(300); fake[0] = datetime.datetime(2026, 10, 12, 22, 0); rt.tick(); wait(300)
check("temp" not in bulb.pilot and st.data["routines"]["circadian"] is True, "in color mode it does not intervene, but stays enabled")
light.set_power(False, auto=True); wait(200); light.update(auto=True, mode="white"); light.set_power(True, auto=True); wait(400)
check(bulb.pilot.get("temp") == 2500, f"when turned on it starts at the white for that hour ({bulb.pilot.get('temp')})")
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cwid * 1.5), 20)); wait(200)
QTest.mouseClick(w.white_page.tiles[3], Qt.MouseButton.LeftButton); wait(400)
check(bulb.pilot["temp"] == 4000 and st.data["routines"]["circadian"] is False and not rp.circadian.isChecked(), "picking a white by hand disables it")

# ---------------------------------------------------------------- follow this PC
pc = app.pc
check(pc.supported is False and not rp.pc.isEnabled() and "windows" in rp.findChildren(type(rp.sleep_desc))[-2].text(), "outside Windows, disabled and explained")
got = []
pc.away.connect(lambda: got.append("away")); pc.back.connect(lambda: got.append("back"))
for m, wp in ((pcevents.WM_WTSSESSION_CHANGE, 7), (pcevents.WM_WTSSESSION_CHANGE, 8), (pcevents.WM_POWERBROADCAST, 4),
              (pcevents.WM_POWERBROADCAST, 7), (pcevents.WM_POWERBROADCAST, 0x12), (pcevents.WM_WTSSESSION_CHANGE, 5)):
    pc.handle(m, wp)
check(got == ["away", "back", "away", "back"], f"lock/unlock and suspend/resume {got}")
pf = pcevents._Filter(pc); pc.hwnd = 4242; got.clear()
msg = wintypes.MSG(); msg.message = pcevents.WM_POWERBROADCAST; msg.wParam = 4; msg.hWnd = 4242
pf.nativeEventFilter(QByteArray(b"windows_generic_MSG"), shiboken6.VoidPtr(ctypes.addressof(msg)))
msg.hWnd = 999
pf.nativeEventFilter(QByteArray(b"windows_generic_MSG"), shiboken6.VoidPtr(ctypes.addressof(msg)))
check(got == ["away"], "only the notification that reaches its own window counts")
pc.hwnd = 0; clock[0] += 100
rt.set_pc_follow(True); app.sound.played.clear()
light.update(mode="white", temp=3000, brightness=60); wait(300)
pc.away.emit(); pc.away.emit(); wait(400)
check(bulb.pilot["state"] is False, "locking the PC turns the light off")
clock[0] += 60; pc.back.emit(); wait(400)
check(bulb.pilot["state"] is True and bulb.pilot["dimming"] == 60, "on return it turns back on as it was")
check(app.sound.played == [], "and without sound")
light.set_power(False); wait(300); clock[0] += 60; pc.away.emit(); wait(200); clock[0] += 60; pc.back.emit(); wait(400)
check(bulb.pilot["state"] is False, "if it was already off, returning does not turn it on")
rt.set_pc_follow(False); light.set_power(True); wait(300); clock[0] += 60; pc.away.emit(); wait(300)
check(bulb.pilot["state"] is True, "with the option off it does nothing")

# ---------------------------------------------------------------- custom scenes
QTest.mouseClick(w.tabs, Qt.MouseButton.LeftButton, pos=QPoint(int(cwid * 2.5), 20)); wait(250)
sp = w.scenes_page
check([t.name for t in sp.own_tiles] == ["aurora", "embers"] and len(sp.tiles) == 28, "two sample custom scenes and the 28 built-in ones")
light.update(mode="rgb", rgb=(10, 20, 250), brightness=100); wait(400)
n0 = len(bulb.log); QTest.mouseClick(sp.own_tiles[0], Qt.MouseButton.LeftButton); wait(2600)
frames = [x[2] for x in bulb.log[n0:] if x[1] == "setPilot" and "r" in x[2]]
cols = {(f["r"], f["g"], f["b"]) for f in frames}
check(light.effect_kind == "anim" and light.effect_id == "aurora" and sp.own_tiles[0].selected and len(cols) > 8
      and all(f["r"] == 0 for f in frames), f"plays the scene, moving through its colors ({len(frames)} sends, {len(cols)} shades)")
check(w.sub.text().startswith("aurora scene"), f"the panel says what is playing ({w.sub.text()!r})")
QTest.mouseClick(sp.own_tiles[0], Qt.MouseButton.LeftButton); wait(600)
check(light.runner is None and (bulb.pilot["r"], bulb.pilot["g"], bulb.pilot["b"]) == (10, 20, 250), "clicking again stops it and the previous color returns")
# editor: new scene
QTest.mouseClick(sp.new_btn, Qt.MouseButton.LeftButton); wait(500)
ed = w.scene_editor
check(ed.isVisible() and len(ed.swatches) == 2 and light.effect_id == "preview" and not ed.remove_color.isEnabled(), "editor open with a preview on the light")
QTest.mouseClick(ed.wheel, Qt.MouseButton.LeftButton, pos=QPoint(ed.wheel.width() - 6, ed.wheel.height() // 2)); wait(200)
check(ed.colors[0] == [255, 0, 0] and light.runner.options["colors"][0] == [255, 0, 0], "the color picked on the wheel goes to the preview")
ed._add_color(); wait(150); ed._add_color(); wait(150)
check(len(ed.colors) == 4 and ed.sel == 3 and ed.remove_color.isEnabled() and ed.slots.count() == 5, "up to four colors")
ed._select(1); ed._remove_color(); wait(150)
check(len(ed.colors) == 3 and len(light.runner.options["colors"]) == 3, "remove a color")
ed.pace.slider.setValue(2.0, emit=True); wait(100)
check(light.runner.options["seconds"] == 2.0, "the speed is applied live")
ed.name.setText("Fiesta"); QTest.mouseClick(ed.ok, Qt.MouseButton.LeftButton); wait(600)
saved = st.data["scenes"][-1]
check(not ed.isVisible() and saved["name"] == "Fiesta" and len(saved["colors"]) == 3 and saved["seconds"] == 2.0
      and light.effect_id == saved["id"] and [t.name for t in sp.own_tiles] == ["aurora", "embers", "fiesta"]
      and sp.own_tiles[2].selected, f"save: it is in the list and playing ({saved['id']})")
# edit and cancel
sp.editRequested.emit(st.data["scenes"][1]); wait(400)
check(ed.isVisible() and ed.name.text() == "embers" and light.effect_id == "preview", "edit an existing one")
ed.colors[0] = [1, 2, 3]; ed.dismiss(); wait(600)
check(st.data["scenes"][1]["colors"][0] == [255, 50, 0] and light.runner is None, "canceling does not save and stops the preview")
sp.editRequested.emit(st.data["scenes"][1]); wait(300); ed.name.setText(""); ed._save(); wait(400)
check(st.data["scenes"][1]["name"] == "Scene 1" and i18n.t_name("Scene 1") == "scene 1", "with no name it gets an automatic one")
light.stop_effect(); wait(300)
st.data["scenes"].remove(saved); sp.rebuild_own(); wait(100)
check(len(sp.own_tiles) == 2, "delete a scene")
QTest.mouseClick(sp.own_tiles[0], Qt.MouseButton.LeftButton); wait(500)
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(600)
check(light.runner is None and bulb.pilot["state"] is False, "turning off stops the scene")
QTest.mouseClick(w.orb, Qt.MouseButton.LeftButton, pos=c); wait(300)

# ---------------------------------------------------------------- in Spanish
err = io.StringIO()
with contextlib.redirect_stderr(err):
    app._set_language("es"); wait(500); w = app.window
    labels = w.tabs.labels
    w.settings.dismiss(); w.tabs.setIndex(4, emit=True); wait(200)
    desc = w.routines_page.sleep_desc.text()
    app.routines.start_sleep(30); wait(200); running = w.routines_page.sleep_desc.text(); app.routines.cancel_sleep(); wait(200)
    i18n_scene = i18n.t_name("Scene 1")
check(labels[-1] == "rutinas" and "apaga" in desc and "30 min" in running and i18n_scene == "escena 1" and err.getvalue() == "",
      f"routines in Spanish ({desc!r}; {running!r})")
app.light._persist(); check(sorted(os.listdir(home)) == ["data"], "everything is still saved only in the program folder")
app._cleanup(); wait(200)
print("CHECKS FAILED:", check.failed)
sys.exit(1 if check.failed else 0)
