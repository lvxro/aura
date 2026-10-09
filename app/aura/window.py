"""Aura's main window."""

from __future__ import annotations

import colorsys
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QRegularExpressionValidator
from PySide6.QtWidgets import (QAbstractButton, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, hotkey, icons, sound, startup, wiz
from . import theme as T
from .controller import Light
from .effects import MUSIC_MODES, SCREEN_MODES
from .i18n import LANGUAGES, language, t, t_name
from .routines import SLEEP_CHOICES, WAKE_CHOICES, Routines, parse_time
from .store import Store
from .widgets import (AA, Bars, BrightnessSlider, Button, Card, ColorWheel, DeviceButton, IconButton,
                      LampPanel, Orb, SceneTile, ScreenPreview, Segmented, Slider, Swatch, Switch,
                      TempSlider, Tile)

W, H, LEFT = 900, 536, 320


class Text(QLabel):
    """A label that shows its text in lowercase, like the rest of the interface."""

    def __init__(self, text=""):
        super().__init__(str(text).lower())

    def setText(self, text):
        super().setText(str(text).lower())


def label(text="", size=13, weight=400, color: QColor = T.TEXT, display=False, wrap=False) -> QLabel:
    l = Text(text)
    l.setFont(T.font(size, weight, display))
    l.setStyleSheet(f"color: {color.name()}; background: transparent;")
    l.setWordWrap(wrap)
    return l


def caption(text: str, color: QColor = T.MUTED) -> QLabel:
    """A section label, set like the ones on a spec sheet: small and letter-spaced."""
    l = Text(text)
    l.setFont(T.font(11, mono=True))
    l.setStyleSheet(f"color: {color.name()}; background: transparent;")
    return l


def temp_key(k: int) -> str:
    if k < 2500:
        return "Candlelight"
    if k < 3200:
        return "Warm light"
    if k < 4300:
        return "Neutral light"
    if k < 5500:
        return "Daylight"
    return "Cool light"


def temp_name(k: int) -> str:
    return t(temp_key(k))


class LabeledSlider(QWidget):
    """Name on the left, value on the right, slider below."""

    changed = Signal(float)

    def __init__(self, title, lo, hi, value, fmt, step=None, parent=None):
        super().__init__(parent)
        self.fmt = fmt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self.title = label(title, 13, 500, T.TEXT)
        self.val = label("", 13, 400, T.MUTED)
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.val)
        lay.addLayout(top)
        self.slider = Slider(lo, hi, value, step)
        self.slider.setAccessibleName(title)
        lay.addWidget(self.slider)
        self.slider.valueChanged.connect(self._on)
        self._show(value)

    def _show(self, v):
        self.val.setText(self.fmt(v))

    def _on(self, v):
        self._show(v)
        self.changed.emit(v)

    def setValue(self, v):
        self.slider.setValue(v)
        self._show(self.slider.value())

    def value(self):
        return self.slider.value()


# --------------------------------------------------------------------------
# Tab: Color
# --------------------------------------------------------------------------
class ColorPage(QWidget):
    def __init__(self, light: Light, store: Store, parent=None):
        super().__init__(parent)
        self.light, self.store = light, store
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(28)

        self.wheel = ColorWheel(312)
        self.wheel.setAccessibleName(t("Color wheel"))
        lay.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignVCenter)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.addStretch(1)
        right.addWidget(caption(t("Favorites")))
        right.addSpacing(8)
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        self.grid.setContentsMargins(0, 0, 0, 0)
        right.addLayout(self.grid)
        right.addSpacing(8)
        self.hint = label(t("Right-click to rename or remove."), 12, 400, T.FAINT, wrap=True)
        right.addWidget(self.hint)
        right.addSpacing(26)
        right.addWidget(caption(t("Color code")))
        right.addSpacing(8)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(124)
        self.hex.setPlaceholderText("#ff7828")
        self.hex.setAccessibleName(t("Hex color code"))
        self.hex.setValidator(QRegularExpressionValidator(r"#?[0-9A-Fa-f]{0,6}"))
        right.addWidget(self.hex)
        right.addStretch(1)
        lay.addLayout(right, 1)

        self.swatches: list[Swatch] = []
        self.wheel.colorChanged.connect(lambda r, g, b: self.light.update(mode="rgb", rgb=(r, g, b)))
        self.hex.editingFinished.connect(self._hex_entered)
        self.rebuild()

    def rebuild(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.swatches = []
        favs = self.store.favorites["rgb"]
        for i, fav in enumerate(favs[:12]):
            sw = Swatch(QColor(*fav["rgb"]), t(fav["name"]))
            sw.fav = fav
            sw.clicked.connect(lambda _=False, f=fav: self.light.update(mode="rgb", rgb=tuple(f["rgb"])))
            sw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            sw.customContextMenuRequested.connect(lambda pos, s=sw: self._menu(s, pos))
            self.grid.addWidget(sw, i // 4, i % 4)
            self.swatches.append(sw)
        if len(favs) < 12:
            add = Swatch(None)
            add.clicked.connect(self._add)
            n = len(favs)
            self.grid.addWidget(add, n // 4, n % 4)
        self.grid.setColumnStretch(4, 1)
        self.refresh()

    def _add(self):
        rgb = list(self.light.state["rgb"])
        favs = self.store.favorites["rgb"]
        if any(f["rgb"] == rgb for f in favs):
            return
        favs.append({"name": "#%02x%02x%02x" % tuple(rgb), "rgb": rgb})
        self.store.save()
        self.rebuild()

    def _menu(self, sw: Swatch, pos):
        m = T.make_menu(self)
        rename = m.addAction(t("Rename…"))
        remove = m.addAction(t("Remove from favorites"))
        chosen = m.exec(sw.mapToGlobal(pos))
        if chosen == remove:
            self.store.favorites["rgb"].remove(sw.fav)
            self.store.save()
            self.rebuild()
        elif chosen == rename:
            self.window().ask_text(t("Favorite name"), t(sw.fav["name"]),
                                   lambda text, f=sw.fav: self._rename(f, text))

    def _rename(self, fav, text):
        fav["name"] = text
        self.store.save()
        self.rebuild()

    def _hex_entered(self):
        code = self.hex.text().strip().lstrip("#")
        if len(code) == 3:
            code = "".join(ch * 2 for ch in code)
        if len(code) != 6:
            self.refresh()
            return
        rgb = (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))
        if rgb == (0, 0, 0):
            self.refresh()
            return
        self.light.update(mode="rgb", rgb=rgb)

    def refresh(self):
        st = self.light.state
        is_rgb = st["mode"] == "rgb" and self.light.runner is None
        rgb = tuple(st["rgb"])
        self.wheel.active = is_rgb
        if not self.wheel._drag:
            self.wheel.set_rgb(*rgb)
        else:
            self.wheel.update()
        if not self.hex.hasFocus():
            self.hex.setText("#%02x%02x%02x" % rgb)
        for sw in self.swatches:
            sw.setSelected(is_rgb and tuple(sw.fav["rgb"]) == rgb)


# --------------------------------------------------------------------------
# Tab: White
# --------------------------------------------------------------------------
class WhitePage(QWidget):
    def __init__(self, light: Light, store: Store, parent=None):
        super().__init__(parent)
        self.light, self.store = light, store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.kelvin = label("2700k", 40, 600, T.TEXT, display=True)
        self.kname = label(t("Warm"), 15, 500, T.MUTED)
        head.addWidget(self.kelvin, 0, Qt.AlignmentFlag.AlignBaseline)
        head.addWidget(self.kname, 0, Qt.AlignmentFlag.AlignBaseline)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(10)
        self.slider = TempSlider()
        self.slider.setAccessibleName(t("White temperature"))
        lay.addWidget(self.slider)
        ends = QHBoxLayout()
        ends.addWidget(label(t("Warmer"), 12, 400, T.FAINT))
        ends.addStretch(1)
        ends.addWidget(label(t("Cooler"), 12, 400, T.FAINT))
        lay.addSpacing(4)
        lay.addLayout(ends)
        lay.addSpacing(26)

        row = QHBoxLayout()
        row.addWidget(caption(t("Favorites")))
        row.addStretch(1)
        self.add = Button(t("Save current"), "ghost", "plus", height=32)
        row.addWidget(self.add)
        lay.addLayout(row)
        lay.addSpacing(10)
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        lay.addLayout(self.grid)
        lay.addStretch(1)

        self.tiles: list[Tile] = []
        self.slider.valueChanged.connect(lambda v: self.light.update(mode="white", temp=int(v)))
        self.add.clicked.connect(self._add)
        self.rebuild()

    def rebuild(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.tiles = []
        favs = self.store.favorites["white"]
        for i, fav in enumerate(favs[:9]):
            tile = Tile(t(fav["name"]),
                        t("{temp} K at {pct}%", temp=fav["temp"], pct=fav.get("brightness", 100)),
                        QColor(*wiz.kelvin_to_rgb(fav["temp"])))
            tile.fav = fav
            tile.clicked.connect(lambda _=False, f=fav: self.light.update(
                mode="white", temp=int(f["temp"]), brightness=int(f.get("brightness", 100))))
            tile.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tile.customContextMenuRequested.connect(lambda pos, tl=tile: self._menu(tl, pos))
            self.grid.addWidget(tile, i // 3, i % 3)
            self.tiles.append(tile)
        self.add.setVisible(len(favs) < 9)
        self.refresh()

    def _add(self):
        st = self.light.state
        favs = self.store.favorites["white"]
        if any(f["temp"] == st["temp"] and f.get("brightness", 100) == st["brightness"] for f in favs):
            return
        favs.append({"name": temp_key(st["temp"]), "temp": st["temp"], "brightness": st["brightness"]})
        self.store.save()
        self.rebuild()

    def _menu(self, tile: Tile, pos):
        m = T.make_menu(self)
        rename = m.addAction(t("Rename…"))
        remove = m.addAction(t("Remove from favorites"))
        chosen = m.exec(tile.mapToGlobal(pos))
        if chosen == remove:
            self.store.favorites["white"].remove(tile.fav)
            self.store.save()
            self.rebuild()
        elif chosen == rename:
            self.window().ask_text(t("Favorite name"), t(tile.fav["name"]),
                                   lambda text, f=tile.fav: self._rename(f, text))

    def _rename(self, fav, text):
        fav["name"] = text
        self.store.save()
        self.rebuild()

    def refresh(self):
        st = self.light.state
        is_white = st["mode"] == "white" and self.light.runner is None
        self.slider.active = is_white
        if not self.slider._drag:
            self.slider.setValue(st["temp"])
        else:
            self.slider.update()
        k = int(self.slider.value())
        self.kelvin.setText(f"{k}k")       # the dot-matrix space is a full cell wide
        self.kname.setText(temp_name(k))
        for tile in self.tiles:
            tile.setSelected(is_white and tile.fav["temp"] == st["temp"]
                             and tile.fav.get("brightness", 100) == st["brightness"])


# --------------------------------------------------------------------------
# Tab: Scenes
# --------------------------------------------------------------------------
class ScenesPage(QWidget):
    """Scenes made by the person (played from the PC) and the ones built into the light."""

    editRequested = Signal(object)      # a scene dict to edit, or None for a new one

    def __init__(self, light: Light, store: Store, parent=None):
        super().__init__(parent)
        self.light, self.store = light, store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 12, 0)
        col.setSpacing(0)

        head = QHBoxLayout()
        head.addWidget(caption(t("Your scenes")))
        head.addStretch(1)
        self.new_btn = Button(t("New scene"), "ghost", "plus", height=32)
        head.addWidget(self.new_btn)
        col.addLayout(head)
        col.addSpacing(8)
        self.own_grid = QGridLayout()
        self.own_grid.setSpacing(4)
        col.addLayout(self.own_grid)
        col.addSpacing(8)
        self.own_hint = label(t("Right-click one of yours to edit or delete it. They play while Aura is open."),
                              12, 400, T.FAINT, wrap=True)
        col.addWidget(self.own_hint)
        col.addSpacing(18)

        col.addWidget(caption(t("Built into the light")))
        col.addSpacing(8)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tiles: list[SceneTile] = []
        for i, (sid, name, dyn, colors) in enumerate(wiz.SCENES):
            tile = SceneTile(sid, t(name), dyn, colors)
            tile.clicked.connect(lambda _=False, s=sid: self.light.update(mode="scene", scene=s))
            grid.addWidget(tile, i // 4, i % 4)
            self.tiles.append(tile)
        col.addLayout(grid)
        col.addStretch(1)
        area.setWidget(inner)
        area.viewport().setStyleSheet("background: transparent;")
        lay.addWidget(area, 1)

        self.speed = LabeledSlider(t("Motion speed"), 20, 200, 100,
                                   lambda v: f"{int(v)}%", step=5)
        self.speed.changed.connect(lambda v: self.light.update(speed=int(v)))
        lay.addWidget(self.speed)
        self.note = label(t("Built-in scenes run inside the light, so they keep going after you close Aura."),
                          12, 400, T.FAINT, wrap=True)
        lay.addWidget(self.note)

        self.own_tiles: list[SceneTile] = []
        self.new_btn.clicked.connect(lambda: self.editRequested.emit(None))
        self.rebuild_own()

    def rebuild_own(self):
        while self.own_grid.count():
            w = self.own_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.own_tiles = []
        for i, scene in enumerate(self.store.data["scenes"][:12]):
            tile = SceneTile(scene["id"], t_name(scene["name"]), True, scene["colors"])
            tile.scene = scene
            tile.clicked.connect(lambda _=False, s=scene: self.play(s))
            tile.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tile.customContextMenuRequested.connect(lambda pos, tl=tile: self._menu(tl, pos))
            self.own_grid.addWidget(tile, i // 4, i % 4)
            self.own_tiles.append(tile)
        for c in range(4):
            self.own_grid.setColumnStretch(c, 1)
        self.new_btn.setVisible(len(self.store.data["scenes"]) < 12)
        self.own_hint.setVisible(bool(self.own_tiles))
        self.refresh()

    def play(self, scene: dict):
        """Start one of the person's scenes; clicking the one that is playing stops it."""
        if self.light.effect_kind == "anim" and self.light.effect_id == scene["id"]:
            self.light.stop_effect()
        else:
            self.light.start_effect("anim", {"colors": scene["colors"], "seconds": scene["seconds"]},
                                    effect_id=scene["id"])

    def _menu(self, tile: SceneTile, pos):
        m = T.make_menu(self)
        edit = m.addAction(t("Edit…"))
        remove = m.addAction(t("Delete this scene"))
        chosen = m.exec(tile.mapToGlobal(pos))
        if chosen == edit:
            self.editRequested.emit(tile.scene)
        elif chosen == remove:
            if self.light.effect_id == tile.scene["id"]:
                self.light.stop_effect()
            self.store.data["scenes"].remove(tile.scene)
            self.store.save()
            self.rebuild_own()

    def refresh(self):
        st = self.light.state
        playing = self.light.effect_id if self.light.effect_kind == "anim" else None
        for tile in self.own_tiles:
            tile.setSelected(tile.scene_id == playing)
        on = st["mode"] == "scene" and self.light.runner is None
        dynamic = False
        for tile in self.tiles:
            sel = on and tile.scene_id == st["scene"]
            tile.setSelected(sel)
            dynamic = dynamic or (sel and tile.dynamic)
        if not self.speed.slider._drag:
            self.speed.setValue(st["speed"])
        self.speed.setEnabled(dynamic)
        self.speed.setVisible(dynamic)
        self.note.setVisible(not dynamic)


# --------------------------------------------------------------------------
# Tab: Effects
# --------------------------------------------------------------------------
class EffectsPage(QWidget):
    def __init__(self, light: Light, store: Store, parent=None):
        super().__init__(parent)
        self.light, self.store = light, store
        cfg = store.effects
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QHBoxLayout()
        self.kind = Segmented([t("Music"), t("Screen")], height=36, compact=True)
        self.kind.setFixedWidth(210)
        self.kind.setAccessibleName(t("Effect type"))
        top.addWidget(self.kind)
        top.addSpacing(14)
        self.status = label("", 13, 400, T.MUTED)
        top.addWidget(self.status, 1)
        lay.addLayout(top)
        lay.addSpacing(14)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # --- music
        music = QWidget()
        ml = QVBoxLayout(music)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.music_tiles: dict[str, Tile] = {}
        for i, (key, name, desc) in enumerate(MUSIC_MODES):
            tile = Tile(t(name), t(desc), height=58)
            tile.clicked.connect(lambda _=False, k=key: self._set("music", "mode", k))
            grid.addWidget(tile, i // 2, i % 2)
            self.music_tiles[key] = tile
        ml.addLayout(grid)
        ml.addSpacing(16)
        sl = QHBoxLayout()
        sl.setSpacing(24)
        self.sens = LabeledSlider(t("Sensitivity"), 0.4, 2.6, cfg["music"]["sensitivity"],
                                  lambda v: t("Low") if v < 0.8 else "normal" if v < 1.4 else t("High") if v < 2.1 else t("Max"))
        self.msmooth = LabeledSlider(t("Smoothing"), 0.0, 1.0, cfg["music"]["smoothing"],
                                     lambda v: f"{int(round(v * 100))}%")
        sl.addWidget(self.sens)
        sl.addWidget(self.msmooth)
        ml.addLayout(sl)
        ml.addSpacing(12)
        src = QHBoxLayout()
        src.addWidget(label(t("Listen to"), 13, 500))
        src.addStretch(1)
        self.source = Segmented([t("This PC's audio"), t("Microphone")], height=34, compact=True)
        self.source.setFixedWidth(300)
        self.source.setAccessibleName(t("Audio source"))
        src.addWidget(self.source)
        ml.addLayout(src)
        ml.addStretch(1)
        self.stack.addWidget(music)

        # --- screen
        screen = QWidget()
        sl2 = QVBoxLayout(screen)
        sl2.setContentsMargins(0, 0, 0, 0)
        sl2.setSpacing(0)
        grid2 = QGridLayout()
        grid2.setSpacing(8)
        self.screen_tiles: dict[str, Tile] = {}
        for i, (key, name, desc) in enumerate(SCREEN_MODES):
            tile = Tile(t(name), t(desc), height=58)
            tile.clicked.connect(lambda _=False, k=key: self._set("screen", "mode", k))
            grid2.addWidget(tile, i, 0)
            self.screen_tiles[key] = tile
        sl2.addLayout(grid2)
        sl2.addSpacing(16)
        row = QHBoxLayout()
        row.setSpacing(24)
        self.ssmooth = LabeledSlider(t("Smoothing"), 0.0, 0.95, cfg["screen"]["smoothing"],
                                     lambda v: f"{int(round(v * 100))}%")
        self.boost = LabeledSlider(t("Color intensity"), 1.0, 2.2, cfg["screen"]["boost"],
                                   lambda v: "Natural" if v < 1.15 else t("Vivid") if v < 1.7 else t("Very vivid"))
        row.addWidget(self.ssmooth)
        row.addWidget(self.boost)
        sl2.addLayout(row)
        sl2.addSpacing(14)
        ab = QHBoxLayout()
        txt = QVBoxLayout()
        txt.setSpacing(1)
        txt.addWidget(label(t("Brightness follows the music"), 13, 500))
        txt.addWidget(label(t("Color comes from the screen, brightness from what's playing."), 12, 400, T.MUTED))
        ab.addLayout(txt, 1)
        self.audio_brightness = Switch()
        self.audio_brightness.setAccessibleName(t("Brightness follows the music"))
        self.audio_brightness.setChecked(bool(cfg["screen"].get("audio_brightness")))
        ab.addWidget(self.audio_brightness)
        sl2.addLayout(ab)
        sl2.addStretch(1)
        self.stack.addWidget(screen)

        # --- footer: preview + button
        self.error = label("", 12, 500, T.WARN, wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        lay.addSpacing(8)
        foot = QHBoxLayout()
        foot.setSpacing(18)
        self.preview = QStackedWidget()
        self.preview.setFixedHeight(44)
        self.bars = Bars()
        self.swatch = ScreenPreview()
        self.preview.addWidget(self.bars)
        self.preview.addWidget(self.swatch)
        foot.addWidget(self.preview, 1)
        self.go = Button(t("Start"), "primary", "play", height=46)
        self.go.setFixedWidth(150)
        foot.addWidget(self.go)
        lay.addLayout(foot)

        self.kind.setIndex(0 if cfg.get("kind") == "music" else 1, animate=False)
        self.stack.setCurrentIndex(self.kind.index)
        self.preview.setCurrentIndex(self.kind.index)
        self.source.setIndex(1 if cfg["music"].get("source") == "mic" else 0, animate=False)

        self.kind.changed.connect(self._kind_changed)
        self.source.changed.connect(lambda i: self._set("music", "source", "mic" if i else "pc"))
        self.sens.slider.released.connect(lambda: self._set("music", "sensitivity", round(self.sens.value(), 2)))
        self.msmooth.slider.released.connect(lambda: self._set("music", "smoothing", round(self.msmooth.value(), 2)))
        self.ssmooth.slider.released.connect(lambda: self._set("screen", "smoothing", round(self.ssmooth.value(), 2)))
        self.boost.slider.released.connect(lambda: self._set("screen", "boost", round(self.boost.value(), 2)))
        self.audio_brightness.toggled.connect(lambda on: self._set("screen", "audio_brightness", bool(on)))
        self.go.clicked.connect(self.toggle)
        light.effectChanged.connect(self._effect_changed)
        light.effectFrame.connect(self._frame)
        self.refresh()

    def current_kind(self) -> str:
        return "music" if self.kind.index == 0 else "screen"

    def _kind_changed(self, i):
        self.stack.setCurrentIndex(i)
        self.preview.setCurrentIndex(i)
        self.store.effects["kind"] = self.current_kind()
        self.store.save()
        self.refresh()

    def _set(self, kind, key, value):
        self.store.effects[kind][key] = value
        self.store.save()
        self.refresh()
        runner = self.light.runner
        if runner is not None and self.light.effect_kind == kind:
            if key in ("sensitivity", "smoothing", "boost"):
                runner.options[key] = value            # applied live
            else:
                self.light.start_effect(kind, self.store.effects[kind])   # needs a restart

    def toggle(self):
        self.error.hide()
        kind = self.current_kind()
        if self.light.runner is not None and self.light.effect_kind == kind:
            self.light.stop_effect()
        else:
            self.light.start_effect(kind, self.store.effects[kind])

    def _effect_changed(self, error):
        if error:
            self.error.setText(error)
            self.error.show()
        self.refresh()

    def _frame(self, frame):
        if self.light.effect_kind == "music":
            self.bars.set(frame.get("bars"))
        elif self.light.effect_kind == "screen":
            self.swatch.set(frame.get("rgb"))

    def refresh(self):
        cfg = self.store.effects
        for k, tile in self.music_tiles.items():
            tile.setSelected(k == cfg["music"]["mode"])
        for k, tile in self.screen_tiles.items():
            tile.setSelected(k == cfg["screen"]["mode"])
        kind = self.current_kind()
        running = self.light.runner is not None and self.light.effect_kind == kind
        other = self.light.runner is not None and not running
        self.go.setText(t("Stop") if running else t("Start"))
        self.go.setIconName("stop" if running else "play")
        self.go.kind = "soft" if running else "primary"
        self.go.setEnabled(bool(self.light.ip))
        self.bars.running = running and kind == "music"
        self.swatch.running = running and kind == "screen"
        if not running:
            self.bars.set(None)
            self.swatch.set(None)
        if not self.light.ip:
            self.status.setText(t("Choose a light to use effects."))
        elif running:
            self.status.setText(t("The light is following the music.") if kind == "music" else t("The light is following the screen."))
        elif other:
            self.status.setText(t("One of your scenes is playing.") if self.light.effect_kind == "anim"
                                else t("The other effect is running right now."))
        elif kind == "music":
            self.status.setText(t("Play music and the light follows it."))
        else:
            self.status.setText(t("The light mirrors your screen."))
        self.bars.update()
        self.swatch.update()
        self.go.update()


# --------------------------------------------------------------------------
# Tab: Routines
# --------------------------------------------------------------------------
class RoutinesPage(QWidget):
    """Sleep timer, wake-up light, following the time of day, following the PC."""

    def __init__(self, light: Light, store: Store, routines: Routines, parent=None):
        super().__init__(parent)
        self.light, self.store, self.routines = light, store, routines
        cfg = routines.cfg
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        def card(title, desc):
            c = Card()
            box = QVBoxLayout(c)
            box.setContentsMargins(16, 12, 14, 12)
            box.setSpacing(10)
            row = QHBoxLayout()
            row.setSpacing(14)
            text = QVBoxLayout()
            text.setSpacing(1)
            text.addWidget(label(title, 14, 600))
            d = label(desc, 12, 400, T.MUTED, wrap=True)
            text.addWidget(d)
            row.addLayout(text, 1)
            box.addLayout(row)
            lay.addWidget(c)
            return box, row, d

        # --- sleep timer
        _box, row, self.sleep_desc = card(t("Sleep timer"), "")
        self.sleep_len = Segmented([str(m) for m in SLEEP_CHOICES], height=34, compact=True)
        self.sleep_len.setFixedWidth(168)
        self.sleep_len.setAccessibleName(t("Minutes until the light turns off"))
        mins = cfg.get("sleep_minutes", 30)
        self.sleep_len.setIndex(SLEEP_CHOICES.index(mins) if mins in SLEEP_CHOICES else 1, animate=False)
        self.sleep_unit = label("min", 12, 400, T.MUTED)
        self.sleep_btn = Button(t("Start"), "primary", height=34)
        self.sleep_btn.setFixedWidth(92)
        row.addWidget(self.sleep_len, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.sleep_unit, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.sleep_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # --- wake-up light
        box, row, _d = card(t("Wake-up light"),
                            t("Rises little by little and reaches full brightness at the time you set."))
        self.wake_on = Switch()
        self.wake_on.setAccessibleName(t("Wake-up light"))
        self.wake_on.setChecked(bool(cfg["wake"].get("enabled")))
        row.addWidget(self.wake_on, 0, Qt.AlignmentFlag.AlignVCenter)
        opts = QHBoxLayout()
        opts.setSpacing(10)
        opts.addWidget(label(t("At"), 13, 500, T.MUTED))
        self.wake_time = QLineEdit(cfg["wake"].get("time", "07:00"))
        self.wake_time.setFixedWidth(72)
        self.wake_time.setMaxLength(5)
        self.wake_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wake_time.setAccessibleName(t("Wake-up time, hours and minutes"))
        self.wake_time.setValidator(QRegularExpressionValidator(r"[0-2]?\d?:?[0-5]?\d?"))
        opts.addWidget(self.wake_time)
        opts.addWidget(label(t("over"), 13, 500, T.MUTED))
        self.wake_len = Segmented([str(m) for m in WAKE_CHOICES], height=34, compact=True)
        self.wake_len.setFixedWidth(108)
        self.wake_len.setAccessibleName(t("Minutes the light takes to rise"))
        wl = cfg["wake"].get("minutes", 20)
        self.wake_len.setIndex(WAKE_CHOICES.index(wl) if wl in WAKE_CHOICES else 1, animate=False)
        opts.addWidget(self.wake_len)
        opts.addWidget(label("min", 12, 400, T.MUTED))
        opts.addStretch(1)
        self.wake_days = Segmented([t("Every day"), t("Weekdays")], height=34, compact=True)
        self.wake_days.setFixedWidth(168)
        self.wake_days.setAccessibleName(t("Days the wake-up light runs"))
        self.wake_days.setIndex(1 if cfg["wake"].get("days") == "weekdays" else 0, animate=False)
        opts.addWidget(self.wake_days)
        box.addLayout(opts)

        # --- time of day
        _box, row, _d = card(t("Follow the time of day"),
                             t("Cool white by day, warm at night. It changes on its own while the light is on white."))
        self.circadian = Switch()
        self.circadian.setAccessibleName(t("Follow the time of day"))
        row.addWidget(self.circadian, 0, Qt.AlignmentFlag.AlignVCenter)

        # --- the PC
        pc_desc = t("Turns the light off when this PC locks or goes to sleep, and back on when you return.") \
            if routines.pc_supported else t("Only available on Windows.")
        _box, row, _d = card(t("Follow this PC"), pc_desc)
        self.pc = Switch()
        self.pc.setAccessibleName(t("Follow this PC"))
        self.pc.setEnabled(routines.pc_supported)
        row.addWidget(self.pc, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)
        lay.addWidget(label(t("Routines run while Aura is open. It can stay in the tray."), 12, 400, T.FAINT))

        self.sleep_btn.clicked.connect(self._sleep_clicked)
        self.sleep_len.changed.connect(lambda i: self._remember_sleep(SLEEP_CHOICES[i]))
        self.wake_on.toggled.connect(self._wake_toggled)
        self.wake_len.changed.connect(lambda i: routines.set_wake(minutes=WAKE_CHOICES[i]))
        self.wake_days.changed.connect(lambda i: routines.set_wake(days="weekdays" if i else "daily"))
        self.wake_time.editingFinished.connect(self._time_entered)
        self.circadian.toggled.connect(self._circadian_toggled)
        self.pc.toggled.connect(self._pc_toggled)
        routines.changed.connect(self.refresh)
        self.refresh()

    def _remember_sleep(self, minutes: int):
        self.routines.cfg["sleep_minutes"] = minutes
        self.store.save()

    def _sleep_clicked(self):
        if self.routines.sleep_active:
            self.routines.cancel_sleep()
        else:
            self.routines.start_sleep(SLEEP_CHOICES[self.sleep_len.index])

    def _time_entered(self):
        hm = parse_time(self.wake_time.text())
        if hm is None:
            self.wake_time.setText(self.routines.cfg["wake"].get("time", "07:00"))
            return
        text = f"{hm[0]:02d}:{hm[1]:02d}"
        self.wake_time.setText(text)
        if text != self.routines.cfg["wake"].get("time"):
            self.routines.set_wake(time=text)

    def _wake_toggled(self, on: bool):
        if bool(on) != bool(self.routines.cfg["wake"].get("enabled")):
            self.routines.set_wake(enabled=bool(on))

    def _pc_toggled(self, on: bool):
        if bool(on) != bool(self.routines.cfg.get("pc_follow")):
            self.routines.set_pc_follow(bool(on))

    def _circadian_toggled(self, on: bool):
        if bool(on) != bool(self.routines.cfg.get("circadian")):
            self.routines.set_circadian(bool(on))

    def refresh(self):
        r = self.routines
        running = r.sleep_active
        self.sleep_len.setVisible(not running)
        self.sleep_unit.setVisible(not running)
        self.sleep_btn.setText(t("Cancel") if running else t("Start"))
        self.sleep_btn.kind = "soft" if running else "primary"
        self.sleep_btn.setEnabled(self.light.info is not None)
        self.sleep_btn.update()
        if running:
            self.sleep_desc.setText(t("The light turns off in {n} min.", n=r.sleep_remaining()))
        else:
            self.sleep_desc.setText(t("Dims the light little by little, then turns it off."))
        if self.circadian.isChecked() != bool(r.cfg.get("circadian")):
            self.circadian.setChecked(bool(r.cfg.get("circadian")))
        if self.pc.isChecked() != bool(r.cfg.get("pc_follow")):
            self.pc.setChecked(bool(r.cfg.get("pc_follow")))
        if self.wake_on.isChecked() != bool(r.cfg["wake"].get("enabled")):
            self.wake_on.setChecked(bool(r.cfg["wake"].get("enabled")))


# --------------------------------------------------------------------------
# Overlay sheets
# --------------------------------------------------------------------------
class Sheet(QWidget):
    """Panel that appears over the window on a dimmed backdrop."""

    def __init__(self, parent, title, width=470):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.card = QWidget(self)
        self.card.setFixedWidth(width)
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.card.paintEvent = self._paint_card
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(26, 20, 26, 24)
        self.body.setSpacing(0)
        head = QHBoxLayout()
        self._title = label(title, 26, 600, T.TEXT, display=True)
        head.addWidget(self._title)
        head.addStretch(1)
        self.close_btn = IconButton("close", t("Close"))
        self.close_btn.clicked.connect(self.dismiss)
        head.addWidget(self.close_btn)
        self.body.addLayout(head)
        self.body.addSpacing(14)
        self.hide()

    def _paint_card(self, e):
        p = QPainter(self.card)
        p.setRenderHint(AA)
        r = QRectF(self.card.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(T.BG)
        p.setPen(QPen(T.LINE, 1))
        p.drawRoundedRect(r, 20, 20)
        p.end()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 190))
        p.end()

    def set_title(self, text: str):
        self._title.setText(text)

    def place(self):
        self.setGeometry(self.parentWidget().rect())
        lay = self.card.layout()
        lay.invalidate()
        need = lay.totalHeightForWidth(self.card.width())
        if need <= 0:
            need = self.card.sizeHint().height()
        h = min(need, self.height() - 32)
        self.card.setFixedHeight(h)
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - h) // 2)

    def present(self):
        self.place()
        self.show()
        self.raise_()
        self.setFocus()
        self.replace_soon()

    def replace_soon(self):
        # Newly added widgets are shown on the next turn of the event loop;
        # only then is the computed height final.
        QTimer.singleShot(0, lambda: self.isVisible() and self.place())

    def dismiss(self):
        self.hide()
        self.parentWidget().setFocus()

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.dismiss()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(e)


class LightRow(QAbstractButton):
    menuRequested = Signal()

    def __init__(self, entry: dict, selected: bool, is_new: bool, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.selected = selected
        self.is_new = is_new
        self._hover = False
        self.setFixedHeight(58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(entry.get("name") or entry.get("model") or t("Light"))
        if not is_new:
            self.more = IconButton("more", t("Rename or remove"), self, size=34)
            self.more.clicked.connect(self.menuRequested.emit)
        else:
            self.more = None

    def resizeEvent(self, e):
        if self.more:
            self.more.move(self.width() - 44, (self.height() - 34) // 2)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        acc = T.theme().accent
        p.setBrush(T.RAISED if self._hover else T.SURFACE)
        p.setPen(QPen(acc, 1.6) if self.selected else QPen(T.LINE, 1))
        p.drawRoundedRect(r, 12, 12)
        icons.draw(p, "check" if self.selected else "bulb", 28, r.center().y(), 22,
                   acc if self.selected else T.MUTED)
        model = t(self.entry.get("model") or "WiZ light")
        name = t_name(self.entry.get("name") or "") or model
        detail = t("{model} at {ip}", model=model, ip=self.entry["ip"])
        if self.is_new:
            detail = t("Not added yet, at {ip}", ip=self.entry["ip"])
        p.setFont(T.font(14, 600))
        p.setPen(T.TEXT)
        p.drawText(QRectF(52, r.center().y() - 19, r.width() - 110, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        p.setFont(T.font(12, 400))
        p.setPen(T.MUTED)
        p.drawText(QRectF(52, r.center().y() + 1, r.width() - 110, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, detail)
        if self.is_new:
            p.setFont(T.font(13, 600))
            p.setPen(acc)
            p.drawText(QRectF(r.right() - 90, r.top(), 76, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, t("Add"))
        p.end()


class DevicesSheet(Sheet):
    def __init__(self, parent, light: Light, store: Store):
        super().__init__(parent, t("Your lights"), 480)
        self.light, self.store = light, store
        self.found: dict[str, dict] = {}
        self.scanning = False
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        self.body.addLayout(self.list)
        self.body.addSpacing(12)
        self.msg = label("", 13, 400, T.MUTED, wrap=True)
        self.msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.msg.setFixedHeight(38)
        self.body.addWidget(self.msg)
        self.body.addSpacing(12)
        self.scan_btn = Button(t("Find lights"), "soft", "search", height=40)
        self.body.addWidget(self.scan_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.body.addSpacing(20)
        self.body.addWidget(label(t("Not showing up? Add it by IP address"), 13, 500))
        self.body.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("192.168.1.50")
        self.ip.setAccessibleName(t("Light IP address"))
        row.addWidget(self.ip, 1)
        self.add = Button(t("Add"), "soft", height=40)
        row.addWidget(self.add)
        self.body.addLayout(row)
        self.ip_msg = label("", 12, 500, T.WARN, wrap=True)
        self.ip_msg.setFixedHeight(20)
        self.ip_msg.hide()
        self.body.addSpacing(6)
        self.body.addWidget(self.ip_msg)

        self.scan_btn.clicked.connect(self.scan)
        self.add.clicked.connect(self._add_ip)
        self.ip.returnPressed.connect(self._add_ip)
        light.discovered.connect(self._found)
        light.discoveryFinished.connect(self._scan_done)
        self._probe.connect(self._probed)

    _probe = Signal(object)

    def present(self):
        self.ip_msg.hide()
        self.rebuild()
        super().present()
        if not self.store.lights:
            self.scan()

    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText(t("Searching…"))
        self.msg.setText(t("Looking for WiZ lights on your network…"))
        self.light.scan()

    def _found(self, entry):
        saved = self.store.light(entry["mac"])
        if saved is not None:
            if saved["ip"] != entry["ip"]:
                saved["ip"] = entry["ip"]
                self.store.save()
                if self.store.data.get("active") == saved["mac"]:
                    self.light.sync()
        else:
            self.found[entry["mac"]] = entry
        if self.isVisible():
            self.rebuild()

    def _scan_done(self, count):
        self.scanning = False
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText(t("Search again"))
        self.rebuild()

    def rebuild(self):
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.deleteLater()
        active = self.store.data.get("active")
        for l in self.store.lights:
            row = LightRow(l, l["mac"] == active, False)
            row.clicked.connect(lambda _=False, m=l["mac"]: self._choose(m))
            row.menuRequested.connect(lambda r=row: self._menu(r))
            self.list.addWidget(row)
        new = [e for m, e in self.found.items() if self.store.light(m) is None]
        for e in new[:max(0, 5 - len(self.store.lights))]:
            row = LightRow(e, False, True)
            row.clicked.connect(lambda _=False, en=e: self._adopt(en))
            self.list.addWidget(row)
        total = len(self.store.lights) + len(new)
        if self.scanning:
            self.msg.setText(t("Looking for WiZ lights on your network…"))
        elif total == 0:
            self.msg.setText(t("No lights found. Check that the light has power and that this PC "
                               "is on the same Wi-Fi as the light."))
        elif new:
            self.msg.setText(t("Pick a light to add it and start controlling it."))
        else:
            self.msg.setText(t("Pick a light to control it."))
        if self.isVisible():
            self.place()
            self.replace_soon()

    def _choose(self, mac):
        self.light.select(mac)
        self.dismiss()

    def _adopt(self, entry):
        l = self.store.upsert_light(entry["mac"], entry["ip"], model=entry.get("model"))
        self.found.pop(entry["mac"], None)
        self.store.save()
        self._choose(l["mac"])

    def _menu(self, row: LightRow):
        m = T.make_menu(self)
        rename = m.addAction(t("Rename…"))
        remove = m.addAction(t("Remove this light"))
        chosen = m.exec(row.more.mapToGlobal(row.more.rect().bottomLeft()))
        mac = row.entry["mac"]
        if chosen == rename:
            self.window().ask_text(t("Light name"), t_name(row.entry["name"]), lambda text: self._rename(mac, text))
        elif chosen == remove:
            was_active = self.store.data.get("active") == mac
            self.store.remove_light(mac)
            self.store.save()
            if was_active:
                self.light.select(self.store.data.get("active"))
            self.rebuild()

    def _rename(self, mac, text):
        l = self.store.light(mac)
        if l:
            l["name"] = text
            self.store.save()
            self.light.connectionChanged.emit()
        self.rebuild()

    def _add_ip(self):
        ip = self.ip.text().strip()
        if not wiz.is_valid_ip(ip):
            self.ip_msg.setText(t("That doesn't look like an IP address. It should look like 192.168.1.50"))
            self.ip_msg.show()
            self.place()
            return
        self.ip_msg.hide()
        self.add.setEnabled(False)
        self.add.setText(t("Checking…"))
        self.light.probe(ip, self._probe)

    def _probed(self, entry):
        self.add.setEnabled(True)
        self.add.setText(t("Add"))
        if entry is None:
            self.ip_msg.setText(t("No WiZ light answered at that address."))
            self.ip_msg.show()
            self.place()
            return
        self.ip.clear()
        self._adopt(entry)


class HotkeyEdit(QAbstractButton):
    """Shows the shortcut; after a click it waits for the new key combination."""

    captured = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = ""
        self.listening = False
        self.setFixedSize(230, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(t("Click to change it. Backspace clears it."))
        self.clicked.connect(self._listen)

    def set(self, value):
        self.value = value or ""
        self.update()

    def _listen(self):
        self.listening = True
        self.setFocus()
        self.update()

    def focusOutEvent(self, e):
        self.listening = False
        self.update()

    def keyPressEvent(self, e):
        if not self.listening:
            return super().keyPressEvent(e)
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.listening = False
        elif k in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not e.modifiers():
            self.listening = False
            self.value = ""
            self.captured.emit("")
        else:
            combo = hotkey.from_event(e)
            if combo:
                self.listening = False
                self.value = combo
                self.captured.emit(combo)
        self.update()
        e.accept()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(T.SURFACE)
        p.setPen(QPen(T.theme().accent if self.listening else T.LINE, 1.6 if self.listening else 1))
        p.drawRoundedRect(r, 10, 10)
        p.setFont(T.font(13, 600 if not self.listening else 400))
        if self.listening:
            p.setPen(T.MUTED)
            text = t("Press the keys…")
        else:
            p.setPen(T.TEXT if self.value else T.FAINT)
            text = self.value.replace("+", " + ").lower() if self.value else t("No shortcut")
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class SettingsSheet(Sheet):
    hotkeyChanged = Signal(str, str)        # action, key combination
    languageChanged = Signal(str)
    soundsChanged = Signal(str, str)        # sound id, and which one to play: on or off

    SOUND_INTRO = ("Real recordings of mechanical keyboards. Click one to hear it; "
                   "click it again to hear the off sound.")
    SOUND_CUSTOM_HELP = ("Put a file named on.wav in the folder that just opened (plus off.wav for "
                         "a different off sound), then choose Custom again.")
    HOTKEY_TITLES = {
        "toggle": "Turn on and off",
        "brighter": "Brighter",
        "dimmer": "Dimmer",
        "next": "Next favorite",
    }

    def __init__(self, parent, store: Store):
        super().__init__(parent, t("Settings"), 680)
        self.store = store
        s = store.settings

        self.tabs = Segmented([t("General"), t("Sound"), t("Shortcuts"), t("About")], height=36, compact=True)
        self.tabs.setFixedWidth(430)
        self.tabs.setAccessibleName(t("Settings sections"))
        self.body.addWidget(self.tabs, 0, Qt.AlignmentFlag.AlignLeft)
        self.body.addSpacing(18)
        self.stack = QStackedWidget()
        self.body.addWidget(self.stack)

        def page():
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            self.stack.addWidget(w)
            return lay

        def row(lay, title, desc, control):
            h = QHBoxLayout()
            h.setSpacing(16)
            v = QVBoxLayout()
            v.setSpacing(2)
            v.addWidget(label(title, 14, 600))
            d = None
            if desc is not None:
                d = label(desc, 12, 400, T.MUTED, wrap=True)
                v.addWidget(d)
            h.addLayout(v, 1)
            h.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addLayout(h)
            lay.addSpacing(16)
            return d

        # --- general
        g = page()
        # Language names are never translated, and English always comes first.
        self.lang = Segmented([name for _code, name in LANGUAGES], height=36, compact=True)
        self.lang.setFixedWidth(300)
        self.lang.setAccessibleName(t("Interface language"))
        codes = [code for code, _name in LANGUAGES]
        self.lang.setIndex(codes.index(language()) if language() in codes else 0, animate=False)
        row(g, t("Language"), None, self.lang)

        self.startup = Switch()
        self.startup.setAccessibleName(t("Start with Windows"))
        self.startup.setEnabled(startup.supported())
        self.startup.setChecked(startup.is_enabled())
        self.startup_desc = row(
            g, t("Start with Windows"),
            t("Aura opens in the tray when you sign in.") if startup.supported()
            else t("Only available on Windows."), self.startup)

        self.tray = Switch()
        self.tray.setAccessibleName(t("Keep running in the tray"))
        self.tray.setChecked(bool(s.get("close_to_tray", True)))
        row(g, t("Keep running in the tray"),
            t("Closing the window leaves Aura next to the clock so shortcuts and routines keep working. "
              "To quit, right-click its icon."), self.tray)
        self.click = Segmented([t("Toggles the light"), t("Opens Aura")], height=36, compact=True)
        self.click.setFixedWidth(300)
        self.click.setAccessibleName(t("Tray icon click action"))
        self.click.setIndex(0 if s.get("tray_click", "toggle") == "toggle" else 1, animate=False)
        row(g, t("Tray icon click"), None, self.click)
        g.addStretch(1)

        # --- sound: every option is a tile; clicking it plays it, so choosing is done by ear
        sp = page()
        self.sound_intro = label(t(self.SOUND_INTRO), 12, 400, T.MUTED, wrap=True)
        self.sound_intro.setFixedHeight(34)
        self.sound_intro.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        sp.addWidget(self.sound_intro)
        sp.addSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(8)
        options = [(sid, name, t(kind)) for sid, name, kind in sound.SOUNDS]
        options += [(sound.CUSTOM, t("Custom"), t("Your own files")), (sound.OFF, t("None"), t("Silent"))]
        self.sound_tiles: dict[str, Tile] = {}
        self._sound_kind = "on"
        for i, (sid, name, sub) in enumerate(options):
            tile = Tile(name, sub, height=46)
            tile.setSelected(sid == s.get("sound"))
            tile.clicked.connect(lambda _=False, key=sid: self._sound(key))
            grid.addWidget(tile, i // 4, i % 4)
            self.sound_tiles[sid] = tile
        for c in range(4):
            grid.setColumnStretch(c, 1)
        sp.addLayout(grid)
        sp.addStretch(1)

        # --- shortcuts
        k = page()
        self.keys: dict[str, HotkeyEdit] = {}
        self.key_notes: dict[str, QLabel] = {}
        for action in hotkey.ACTIONS:
            edit = HotkeyEdit()
            edit.set((s.get("hotkeys") or {}).get(action, ""))
            edit.setAccessibleName(t(self.HOTKEY_TITLES[action]))
            edit.captured.connect(lambda combo, a=action: self._hotkey(a, combo))
            note = row(k, t(self.HOTKEY_TITLES[action]), "", edit)
            note.hide()
            self.keys[action] = edit
            self.key_notes[action] = note
        self.keys_note = label("", 12, 400, T.MUTED, wrap=True)
        k.addWidget(self.keys_note)
        k.addStretch(1)

        # --- about
        a = page()
        a.addWidget(label(f"{APP_NAME} {__version__}", 24, 600, T.TEXT, display=True))
        a.addSpacing(8)
        a.addWidget(label(
            t("Based on kek's WiZ Light Controller by Eshaan Pisal, with effects inspired by wiz-hack "
              "by Shravan Revanna. Free software under the GPL-3.0 license. "
              "Not an official WiZ or Signify product."), 13, 400, T.MUTED, wrap=True))
        a.addSpacing(14)
        a.addWidget(label(
            t("Everything Aura saves stays in its own folder. The only exception is the "
              "Start with Windows entry, which exists only while that switch is on."),
            13, 400, T.MUTED, wrap=True))
        a.addSpacing(16)
        self.folder = Button(t("Open the data folder"), "soft", "folder", height=36)
        a.addWidget(self.folder, 0, Qt.AlignmentFlag.AlignLeft)
        a.addStretch(1)

        self.tabs.changed.connect(self.stack.setCurrentIndex)
        self.tray.toggled.connect(lambda on: self._save("close_to_tray", bool(on)))
        self.click.changed.connect(lambda i: self._save("tray_click", "toggle" if i == 0 else "open"))
        self.lang.changed.connect(lambda i: self.languageChanged.emit(codes[i]))
        self.startup.toggled.connect(self._startup)
        self.folder.clicked.connect(lambda: self._open_folder(store.dir))

    def _save(self, key, value):
        self.store.settings[key] = value
        self.store.save()

    def _sound(self, sid: str):
        folder = os.path.join(self.store.dir, "sounds")
        if sid == sound.CUSTOM and not os.path.isfile(os.path.join(folder, "on.wav")):
            # Nothing to play yet: open the folder and say what goes in it.
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass
            self._open_folder(folder)
            self.sound_intro.setText(t(self.SOUND_CUSTOM_HELP))
            return
        again = sid == self.store.settings.get("sound")
        self._sound_kind = ("off" if self._sound_kind == "on" else "on") if again else "on"
        for key, tile in self.sound_tiles.items():
            tile.setSelected(key == sid)
        self.sound_intro.setText(t(self.SOUND_INTRO))
        self._save("sound", sid)
        self.soundsChanged.emit(sid, self._sound_kind)

    def _open_folder(self, path: str):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _startup(self, on):
        if bool(on) == startup.is_enabled():
            return
        if not startup.set_enabled(bool(on)):
            self.startup_desc.setText(t("Windows didn't allow this change."))
            self.startup.setChecked(startup.is_enabled())

    def _hotkey(self, action, combo):
        self.store.settings["hotkeys"][action] = combo
        self.store.save()
        self.hotkeyChanged.emit(action, combo)

    def hotkey_results(self, results: dict, supported: bool):
        """Show which shortcuts Windows accepted. results: action -> bool."""
        any_bad = False
        for action, note in self.key_notes.items():
            bad = supported and not results.get(action, True)
            any_bad = any_bad or bad
            note.setText(t("Another app already uses that shortcut. Try a different one.") if bad else "")
            note.setStyleSheet(f"color: {T.WARN.name()}; background: transparent;")
            note.setVisible(bad)
        if not supported:
            self.keys_note.setText(t("Global shortcuts are only available on Windows."))
        else:
            self.keys_note.setText(t("They work from any app, even while Aura sits in the tray. "
                                     "Click one to change it; Backspace clears it."))
        if self.isVisible():
            self.replace_soon()


class TextSheet(Sheet):
    """Asks for a short text (renaming)."""

    def __init__(self, parent):
        super().__init__(parent, t("Name"), 400)
        self.edit = QLineEdit()
        self.edit.setMaxLength(32)
        self.body.addWidget(self.edit)
        self.body.addSpacing(18)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel = Button(t("Cancel"), "ghost", height=40)
        self.ok = Button(t("Save"), "primary", height=40)
        row.addWidget(self.cancel)
        row.addSpacing(8)
        row.addWidget(self.ok)
        self.body.addLayout(row)
        self._cb = None
        self.cancel.clicked.connect(self.dismiss)
        self.ok.clicked.connect(self._accept)
        self.edit.returnPressed.connect(self._accept)

    def ask(self, title, value, callback):
        self.set_title(title)
        self.edit.setText(value)
        self._cb = callback
        self.present()
        self.edit.setFocus()
        self.edit.selectAll()

    def _accept(self):
        text = self.edit.text().strip()
        if not text:
            return
        cb, self._cb = self._cb, None
        self.dismiss()
        if cb:
            cb(text)


class SceneEditor(Sheet):
    """Make or change one of the person's scenes: two to four colors and a pace.

    While the sheet is open the light plays the scene being edited, so every
    change is seen right away. Cancelling puts the light back as it was.
    """

    saved = Signal()
    MAX_COLORS = 4

    def __init__(self, parent, light: Light, store: Store):
        super().__init__(parent, t("New scene"), 590)
        self.light, self.store = light, store
        self.scene: dict | None = None
        self.colors: list[list[int]] = []
        self.sel = 0
        self._previewing = False

        row = QHBoxLayout()
        row.setSpacing(26)
        self.wheel = ColorWheel(232)
        self.wheel.setAccessibleName(t("Color wheel"))
        row.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.setPlaceholderText(t("Scene name"))
        self.name.setAccessibleName(t("Scene name"))
        col.addWidget(self.name)
        col.addSpacing(16)
        col.addWidget(caption(t("Colors")))
        col.addSpacing(6)
        self.slots = QHBoxLayout()
        self.slots.setSpacing(2)
        self.slots.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self.slots)
        col.addSpacing(4)
        self.hint = label(t("Pick a color here, then choose it on the wheel."), 12, 400, T.FAINT, wrap=True)
        col.addWidget(self.hint)
        col.addSpacing(14)
        self.pace = LabeledSlider(t("Time on each color"), 1.0, 15.0, 4.0,
                                  lambda v: t("{n} s", n=int(round(v))), step=1.0)
        col.addWidget(self.pace)
        col.addStretch(1)
        row.addLayout(col, 1)
        self.body.addLayout(row)
        self.body.addSpacing(18)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.remove_color = Button(t("Remove this color"), "ghost", height=40)
        foot.addWidget(self.remove_color)
        foot.addStretch(1)
        self.cancel = Button(t("Cancel"), "ghost", height=40)
        self.ok = Button(t("Save"), "primary", height=40)
        foot.addWidget(self.cancel)
        foot.addWidget(self.ok)
        self.body.addLayout(foot)

        self.swatches: list[Swatch] = []
        self.wheel.colorChanged.connect(self._wheel_changed)
        self.pace.changed.connect(lambda _v: self._push())
        self.remove_color.clicked.connect(self._remove_color)
        self.cancel.clicked.connect(self.dismiss)
        self.ok.clicked.connect(self._save)
        self.name.returnPressed.connect(self._save)

    # -- opening and closing -------------------------------------------------
    def open(self, scene: dict | None):
        self.scene = scene
        self.set_title(t("Edit scene") if scene else t("New scene"))
        if scene:
            self.colors = [list(c) for c in scene["colors"]][:self.MAX_COLORS]
            self.name.setText(t_name(scene["name"]))
            self.pace.setValue(float(scene.get("seconds", 4.0)))
        else:
            self.colors = [[255, 90, 40], [170, 60, 255]]
            self.name.setText("")
            self.pace.setValue(4.0)
        self.sel = 0
        self._rebuild_slots()
        self.present()
        self._previewing = bool(self.light.ip)
        if self._previewing:
            self.light.start_effect("anim", self._options(), effect_id="preview")

    def dismiss(self):
        if self._previewing:
            self._previewing = False
            if self.light.effect_id == "preview":
                self.light.stop_effect()
        super().dismiss()

    # -- editing ---------------------------------------------------------------
    def _options(self) -> dict:
        return {"colors": [list(c) for c in self.colors], "seconds": float(self.pace.value())}

    def _push(self):
        """Send the current edit to the scene that is playing as a preview."""
        runner = self.light.runner
        if self._previewing and runner is not None and self.light.effect_id == "preview":
            runner.options.update(self._options())

    def _rebuild_slots(self):
        while self.slots.count():
            item = self.slots.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.swatches = []
        for i, c in enumerate(self.colors):
            sw = Swatch(QColor(*c), t("Color {n}", n=i + 1))
            sw.setSelected(i == self.sel)
            sw.clicked.connect(lambda _=False, k=i: self._select(k))
            self.slots.addWidget(sw)
            self.swatches.append(sw)
        if len(self.colors) < self.MAX_COLORS:
            add = Swatch(None)
            add.setToolTip(t("Add a color"))
            add.setAccessibleName(t("Add a color"))
            add.clicked.connect(self._add_color)
            self.slots.addWidget(add)
        self.slots.addStretch(1)
        self.remove_color.setEnabled(len(self.colors) > 2)
        self.wheel.set_rgb(*self.colors[self.sel])
        self.wheel.active = True

    def _select(self, i: int):
        self.sel = i
        for k, sw in enumerate(self.swatches):
            sw.setSelected(k == i)
        self.wheel.set_rgb(*self.colors[i])

    def _wheel_changed(self, r, g, b):
        self.colors[self.sel] = [r, g, b]
        sw = self.swatches[self.sel]
        sw.color = QColor(r, g, b)
        sw.update()
        self._push()

    def _add_color(self):
        r, g, b = self.colors[-1]
        h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        nr, ng, nb = colorsys.hsv_to_rgb((h + 0.28) % 1.0, max(s, 0.7), 1.0)
        self.colors.append([int(nr * 255), int(ng * 255), int(nb * 255)])
        self.sel = len(self.colors) - 1
        self._rebuild_slots()
        self._push()
        self.replace_soon()

    def _remove_color(self):
        if len(self.colors) <= 2:
            return
        del self.colors[self.sel]
        self.sel = min(self.sel, len(self.colors) - 1)
        self._rebuild_slots()
        self._push()
        self.replace_soon()

    def _save(self):
        scenes = self.store.data["scenes"]
        name = self.name.text().strip()
        if not name:
            taken = {s["name"] for s in scenes}
            n = 1
            while f"Scene {n}" in taken:
                n += 1
            name = f"Scene {n}"
        opts = self._options()
        if self.scene is not None:
            if name != t_name(self.scene["name"]):
                self.scene["name"] = name
            self.scene["colors"], self.scene["seconds"] = opts["colors"], opts["seconds"]
            scene = self.scene
        else:
            taken = {s["id"] for s in scenes}
            n = len(scenes) + 1
            while f"scene{n}" in taken:
                n += 1
            scene = {"id": f"scene{n}", "name": name, **opts}
            scenes.append(scene)
        self.store.save()
        was_previewing = self._previewing
        self._previewing = False              # keep the light playing: it is now this scene
        Sheet.dismiss(self)
        if was_previewing and self.light.ip:
            self.light.start_effect("anim", {"colors": scene["colors"], "seconds": scene["seconds"]},
                                    effect_id=scene["id"])
        self.saved.emit()


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------
class MainWindow(QWidget):
    closedToTray = Signal()
    quitRequested = Signal()

    def __init__(self, light: Light, store: Store, routines: Routines):
        super().__init__()
        self.light, self.store, self.routines = light, store, routines
        self.setWindowTitle(APP_NAME.lower())
        self.setFixedSize(W, H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.really_quit = False

        # --- lamp column
        self.lamp = LampPanel(self)
        self.lamp.setGeometry(0, 0, LEFT, H)
        ll = QVBoxLayout(self.lamp)
        ll.setContentsMargins(20, 18, 20, 26)
        ll.setSpacing(0)
        top = QHBoxLayout()
        self.device = DeviceButton()
        top.addWidget(self.device)
        top.addStretch(1)
        self.gear = IconButton("settings", t("Settings"))
        top.addWidget(self.gear)
        ll.addLayout(top)
        ll.addStretch(3)
        self.orb = Orb()
        ll.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        ll.addSpacing(-36)
        self.title = label(t("Off"), 38, 600, T.TEXT, display=True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ll.addWidget(self.title)
        ll.addSpacing(4)
        self.sub = label("", 14, 400, T.MUTED, wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.sub.setFixedHeight(40)
        ll.addWidget(self.sub)
        ll.addStretch(4)
        self.bright = BrightnessSlider(t("Brightness"))
        self.bright.setAccessibleName(t("Brightness"))
        ll.addWidget(self.bright)
        self.find = Button(t("Find my light"), "primary", "search", height=48)
        ll.addWidget(self.find)

        # --- controls column
        self.panel = QWidget(self)
        self.panel.setGeometry(LEFT, 0, W - LEFT, H)
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(28, 20, 28, 24)
        pl.setSpacing(0)
        self.tabs = Segmented(["color", t("White"), t("Scenes"), t("Effects"), t("Routines")], height=42)
        self.tabs.setAccessibleName(t("Sections"))
        pl.addWidget(self.tabs)
        pl.addSpacing(22)
        self.pages = QStackedWidget()
        self.color_page = ColorPage(light, store)
        self.white_page = WhitePage(light, store)
        self.scenes_page = ScenesPage(light, store)
        self.effects_page = EffectsPage(light, store)
        self.routines_page = RoutinesPage(light, store, routines)
        for pg in (self.color_page, self.white_page, self.scenes_page, self.effects_page,
                   self.routines_page):
            self.pages.addWidget(pg)
        pl.addWidget(self.pages, 1)

        # --- sheets
        self.devices = DevicesSheet(self, light, store)
        self.settings = SettingsSheet(self, store)
        self.text_sheet = TextSheet(self)
        self.scene_editor = SceneEditor(self, light, store)
        self.scenes_page.editRequested.connect(self.scene_editor.open)
        self.scene_editor.saved.connect(self.scenes_page.rebuild_own)

        tab = int(store.settings.get("tab", 0))
        self.tabs.setIndex(tab, animate=False)
        self.pages.setCurrentIndex(self.tabs.index)

        self.tabs.changed.connect(self._tab)
        self.orb.clicked.connect(self._power)
        self.orb.nudged.connect(self.bright.nudge)
        self.orb.dialed.connect(self._dial)
        self.bright.valueChanged.connect(lambda v: light.update(brightness=int(v)))
        self.device.clicked.connect(self.devices.present)
        self.find.clicked.connect(self.devices.present)
        self.gear.clicked.connect(self.settings.present)
        light.changed.connect(self.refresh)
        light.connectionChanged.connect(self.refresh)
        light.effectChanged.connect(self._effect_changed)
        light.effectFrame.connect(self._frame)
        routines.changed.connect(self.refresh)
        self.refresh(animate=False)
        QTimer.singleShot(0, self._sync_lamp_center)

    # -- helpers ----------------------------------------------------------
    def ask_text(self, title, value, callback):
        self.text_sheet.ask(title, value, callback)

    def _sync_lamp_center(self):
        g = self.orb.geometry()
        self.lamp.center = QPointF(g.center().x() + 0.5, g.center().y() + 0.5)
        self.lamp.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), T.BG)
        p.end()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_lamp_center)
        _dark_title_bar(self)

    def _effect_changed(self, _error):
        self.refresh()

    def _tab(self, i):
        self.pages.setCurrentIndex(i)
        self.store.settings["tab"] = i
        self.store.save()

    def _dial(self, percent: int):
        """The ring around the lamp was dragged: same as moving the brightness bar."""
        if not self.light.info:
            return
        self.bright.setValue(percent, emit=True)

    def _power(self):
        if not self.light.info:
            self.devices.present()
            return
        self.light.toggle()

    def keyPressEvent(self, e):
        sheet_open = any(s.isVisible() for s in (self.devices, self.settings, self.text_sheet, self.scene_editor))
        if e.key() == Qt.Key.Key_Space and not sheet_open \
                and not isinstance(self.focusWidget(), QLineEdit):
            self._power()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.really_quit or not self.store.settings.get("close_to_tray", True) \
                or not getattr(self, "tray_available", False):
            self.quitRequested.emit()
            e.accept()
        else:
            e.ignore()
            self.hide()
            self.closedToTray.emit()

    # -- state --------------------------------------------------------------
    def _frame(self, frame):
        if self.light.runner is None:
            return
        r, g, b = frame["rgb"]
        master = self.light.state["brightness"] / 100.0
        T.theme().set(QColor(r, g, b), 1.0, max(0.1, frame["dim"] / 100.0 * master), animate=False)
        if frame.get("beat"):
            self.orb.pulse(1.0)

    def refresh(self, animate=True):
        light = self.light
        st = light.state
        info = light.info
        th = T.theme()
        has = info is not None
        offline = has and light.connected is False
        self.orb.available = not offline
        self.lamp.available = not offline
        self.device.set(t_name(info["name"]) if has else "", light.connected)
        self.bright.setVisible(has)
        self.find.setVisible(not has)
        if light.runner is None:
            th.set(QColor(*light.display_rgb()), 1.0 if (st["on"] and has and not offline) else 0.0,
                   st["brightness"] / 100.0, animate=animate)
        if not self.bright._drag:
            self.bright.setValue(st["brightness"])

        hk = (self.store.settings.get("hotkeys") or {}).get("toggle") or ""
        if not has:
            title, sub = t("No light"), t("Find your WiZ light to start controlling it.")
        elif offline:
            title, sub = t("Offline"), t("The light isn't responding. Check its power and Wi-Fi.")
        elif light.runner is not None:
            title = t("On")
            if light.effect_kind == "music":
                mode = self.store.effects["music"]["mode"]
                name = next((n for k, n, _d in MUSIC_MODES if k == mode), "")
                sub = t("Following the music: {mode}", mode=t(name).lower())
            elif light.effect_kind == "anim":
                scene = next((s for s in self.store.data["scenes"] if s["id"] == light.effect_id), None)
                sub = t("{name} scene", name=t_name(scene["name"])) if scene else t("Trying out a scene")
            else:
                sub = t("Following the screen")
        elif st["on"]:
            title = t("On")
            if st["mode"] == "rgb":
                fav = next((f for f in self.store.favorites["rgb"] if tuple(f["rgb"]) == tuple(st["rgb"])), None)
                sub = t(fav["name"]) if fav and not fav["name"].startswith("#") else t("Custom color")
            elif st["mode"] == "scene":
                sub = t("{name} scene", name=t(wiz.SCENE_NAMES.get(st["scene"], ""))).strip()
            else:
                sub = f'{temp_name(st["temp"])}, {st["temp"]} k'
        else:
            title = t("Off")
            sub = t("Click the circle or press {keys}", keys=hk.replace("+", " + ")) \
                if hk and sys.platform == "win32" else t("Click the circle to turn it on")
        if has and not offline and st["on"] and self.routines.sleep_active:
            sub += "\n" + t("Turns off in {n} min", n=self.routines.sleep_remaining())
        self.title.setText(title)
        self.sub.setText(sub)
        self.orb.setToolTip(t("Turn off") if st["on"] and has and not offline else t("Turn on"))
        self.orb.setAccessibleName(t("Turn the light off") if st["on"] else t("Turn the light on"))

        self.color_page.refresh()
        self.white_page.refresh()
        self.scenes_page.refresh()
        self.effects_page.refresh()
        self.routines_page.refresh()


def _dark_title_bar(widget: QWidget):
    """On Windows, paint the title bar the same color as the window."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        set_attr = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_attr.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        set_attr.restype = ctypes.c_long
        hwnd = wintypes.HWND(int(widget.winId()))
        one = ctypes.c_int(1)
        for attr in (20, 19):       # DWMWA_USE_IMMERSIVE_DARK_MODE (new and old)
            if set_attr(hwnd, attr, ctypes.byref(one), ctypes.sizeof(one)) == 0:
                break
        c = T.NIGHT
        colorref = wintypes.DWORD(c.red() | (c.green() << 8) | (c.blue() << 16))
        set_attr(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))    # title bar color (Windows 11)
        set_attr(hwnd, 34, ctypes.byref(colorref), ctypes.sizeof(colorref))    # border color (Windows 11)
    except Exception:
        pass
