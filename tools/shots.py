"""Opens the real interface without a display, against a simulated light, and saves
screenshots (and a short GIF) for the README. Nothing is mocked up: every image is
the app's own window, drawn by the app's own code.

Usage:  python tools/shots.py                 all screenshots, into docs/shots
        python tools/shots.py hero white      only the ones named
        python tools/shots.py --gif           the short demo, into docs/assets/demo.gif (needs ffmpeg)
        python tools/shots.py --es            the same in Spanish (files get an _es suffix)

Needs the app's packages plus PySide6 (the full package, for QtTest).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "shots")
GIF = "--gif" in sys.argv
SPANISH = "--es" in sys.argv
SUFFIX = "_es" if SPANISH else ""

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["AURA_FAKE_AUDIO"] = "1"                     # a synthetic signal instead of the sound card
os.environ["AURA_HOME"] = tempfile.mkdtemp()            # settings go to a throwaway folder
os.environ["QT_SCALE_FACTOR"] = "1" if GIF else os.environ.get("SHOT_SCALE", "2")
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fakebulb import FakeBulb  # noqa: E402

bulb = FakeBulb()
bulb.start()

from aura import theme as T  # noqa: E402
from aura.store import Store  # noqa: E402

store = Store()
store.data["settings"]["language"] = "es" if SPANISH else "en"
store.data["settings"]["tray_hint_shown"] = True
light_entry = store.upsert_light("a8bb50aabbcc", "127.0.0.1", name="velador" if SPANISH else "desk lamp",
                                 model="WiZ color light")
store.data["active"] = light_entry["mac"]
store.save()

qt = QApplication(sys.argv[:1])
qt.setQuitOnLastWindowClosed(False)
T.load_fonts()
qt.setFont(T.font(13))
qt.setStyleSheet(T.stylesheet())
focus_filter = T.KeyboardFocusFilter(qt)
qt.installEventFilter(focus_filter)

from aura.app import AuraApp  # noqa: E402

app = AuraApp(qt, store, False)
PURPLE = (139, 92, 246)


def wait(ms: float):
    end = time.time() + ms / 1000
    while time.time() < end:
        qt.processEvents()
        time.sleep(0.004)


def shot(name: str):
    wait(350)
    os.makedirs(OUT, exist_ok=True)
    app.window.grab().save(os.path.join(OUT, f"{name}{SUFFIX}.png"))
    print("shot", name)


def screenshots(only: list[str]):
    def want(name):
        return not only or name in only

    w = app.window
    light = app.light
    if want("hero"):
        w.tabs.setIndex(0, emit=True)
        light.update(mode="rgb", rgb=PURPLE, brightness=80)
        shot("hero")
    if want("white"):
        w.tabs.setIndex(1, emit=True)
        light.update(mode="white", temp=2700, brightness=80)
        shot("white")
    if want("scenes"):
        w.tabs.setIndex(2, emit=True)
        light.update(mode="rgb", rgb=(255, 120, 40), brightness=100)
        wait(200)
        w.scenes_page.play(store.data["scenes"][0])
        wait(900)
        shot("scenes")
        light.stop_effect()
        wait(300)
    if want("music"):
        w.tabs.setIndex(3, emit=True)
        light.update(mode="rgb", rgb=(255, 60, 60), brightness=100)
        wait(300)
        w.effects_page.toggle()
        wait(1600)
        shot("music")
        w.effects_page.toggle()
        wait(500)
    if want("screen"):
        w.tabs.setIndex(3, emit=True)
        light.update(mode="rgb", rgb=(60, 140, 255), brightness=100)
        w.effects_page.kind.setIndex(1, emit=True)
        shot("screen")
        w.effects_page.kind.setIndex(0, emit=True)
    if want("routines"):
        w.tabs.setIndex(4, emit=True)
        light.update(mode="white", temp=2700, brightness=80)
        wait(300)
        app.routines.start_sleep(30)
        wait(200)
        w.routines_page.wake_on.click()
        w.routines_page.circadian.click()
        shot("routines")
        app.routines.cancel_sleep()
        w.routines_page.wake_on.click()
        w.routines_page.circadian.click()
        wait(200)
    if want("settings"):
        w.tabs.setIndex(0, emit=True)
        light.update(mode="rgb", rgb=PURPLE, brightness=80)
        w.settings.present()
        w.settings.tabs.setIndex(1, emit=True)
        shot("settings")
        w.settings.tabs.setIndex(2, emit=True)
        shot("shortcuts")
        w.settings.dismiss()
        wait(300)
    if want("off"):
        w.tabs.setIndex(1, emit=True)
        light.update(mode="white", temp=2700, brightness=100)
        wait(300)
        light.set_power(False)
        shot("off")
        light.set_power(True)
        wait(300)


def demo_gif():
    """Off, on, brightness on the ring, three colors, white, off. About seven seconds."""
    frames = tempfile.mkdtemp()
    w = app.window
    light = app.light
    orb = w.orb
    count = [0]
    fps = 15

    def record(ms: float):
        end = time.time() + ms / 1000
        step = 1.0 / fps
        nxt = time.time()
        while time.time() < end:
            qt.processEvents()
            if time.time() >= nxt:
                w.grab().save(os.path.join(frames, f"f{count[0]:04d}.png"))
                count[0] += 1
                nxt += step
            time.sleep(0.003)

    center = QPoint(orb.width() // 2, orb.height() // 2)
    w.tabs.setIndex(0, emit=True)
    light.update(mode="rgb", rgb=PURPLE, brightness=80)
    wait(500)
    light.set_power(False)
    wait(900)
    record(500)
    QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=center)           # on
    record(1100)
    QTest.mousePress(orb, Qt.MouseButton.LeftButton, pos=orb.dial_point(80).toPoint())
    for value in list(range(78, 34, -4)) + list(range(38, 101, 4)):        # the ring, down and back up
        QTest.mouseMove(orb, orb.dial_point(value).toPoint())
        record(55)
    QTest.mouseRelease(orb, Qt.MouseButton.LeftButton, pos=orb.dial_point(100).toPoint())
    record(350)
    for rgb in ((255, 120, 40), (0, 200, 255), PURPLE):                    # three colors
        light.update(mode="rgb", rgb=rgb)
        record(750)
    w.tabs.setIndex(1, emit=True)                                          # white
    light.update(mode="white", temp=2700)
    record(900)
    QTest.mouseClick(orb, Qt.MouseButton.LeftButton, pos=center)           # off
    record(1000)

    out = os.path.join(ROOT, "docs", "assets", "demo.gif")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    palette = os.path.join(frames, "palette.png")
    scale = "scale=720:-1:flags=lanczos"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(frames, "f%04d.png"),
                           "-vf", f"{scale},palettegen=max_colors=256:stats_mode=full", palette])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(frames, "f%04d.png"),
                           "-i", palette, "-lavfi", f"{scale}[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle",
                           out])
    shutil.rmtree(frames, ignore_errors=True)
    print(f"gif: {count[0]} frames, {os.path.getsize(out) / 1e6:.1f} MB")


wait(900)
if GIF:
    demo_gif()
else:
    screenshots([a for a in sys.argv[1:] if not a.startswith("-")])
print("done")
os._exit(0)
