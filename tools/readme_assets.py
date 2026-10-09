"""Builds the graphics used by the README: banner, section titles, dividers,
download button and the mounted screenshots.

GitHub does not let a README choose fonts, so every piece of text is drawn as
outlines. The README is dark only: every graphic is a black sheet, whatever
theme the reader uses. Everything is set in lowercase, like the README itself.

The screenshots come from tools/shots.py (run it first); this script only
mounts them on a sheet with a dot grid and labels them.

Fonts (both SIL Open Font License, see docs/fonts), the same two the app uses:
  Doto            dot-matrix headlines and numbers
  JetBrains Mono  everything else

Usage:  python tools/readme_assets.py            everything
        python tools/readme_assets.py banner     only what is named
"""

from __future__ import annotations

import math
import os
import sys

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "docs", "fonts")
OUT = os.path.join(ROOT, "docs", "assets")
SHOTS = os.path.join(ROOT, "docs", "shots")
CACHE = os.path.join(ROOT, "build", "fonts")

VERSION = "1.0"
ACCENT = "#8B5CF6"          # the one color; everything else is black, white or grey
THEMES = {
    "dark": dict(bg="#000000", fg="#FFFFFF", mid="#8C8C8C", low="#5A5A5A", line="#2A2A2A", dot="#262626"),
    "light": dict(bg="#FFFFFF", fg="#000000", mid="#6B6B6B", low="#A3A3A3", line="#DADADA", dot="#DFDFDF"),
}


# ------------------------------------------------------------------ text as outlines
class Face:
    """A font whose text can be turned into SVG path data."""

    def __init__(self, path: str, name: str, **axes):
        font = TTFont(path)
        if axes:
            font = instancer.instantiateVariableFont(font, axes)
        self.font = font
        self.name = name
        self.glyphs = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm

    def static_file(self) -> str:
        """The same instance saved as a file, for drawing into bitmaps."""
        os.makedirs(CACHE, exist_ok=True)
        p = os.path.join(CACHE, self.name + ".ttf")
        if not os.path.isfile(p):
            self.font.save(p)
        return p

    def _contours(self, glyph: str) -> list[list]:
        """A glyph split into its separate shapes (in Doto, one per dot)."""
        pen = DecomposingRecordingPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        out, cur = [], []
        for op, args in pen.value:
            cur.append((op, args))
            if op in ("closePath", "endPath"):
                out.append(cur)
                cur = []
        return out

    @staticmethod
    def _center(contour) -> tuple[float, float]:
        pts = [p for _op, args in contour for p in args]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    def _draw(self, contour, transform) -> str:
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        tp = TransformPen(pen, transform)
        for op, args in contour:
            getattr(tp, op)(*args)
        return pen.getCommands()

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        s = size / self.upm
        return sum(self.glyphs[self.cmap[ord(c)]].width * s + tracking for c in text) - tracking

    def paths(self, text: str, x: float, y: float, size: float, tracking: float = 0.0,
              anchor: str = "start", single_dot_period: bool = False) -> list[list[tuple[str, float, float]]]:
        """Per character, its shapes as (path data, center x, center y), with the baseline at y."""
        s = size / self.upm
        if anchor == "end":
            x -= self.width(text, size, tracking)
        elif anchor == "middle":
            x -= self.width(text, size, tracking) / 2
        out = []
        for c in text:
            name = self.cmap[ord(c)]
            contours = self._contours(name)
            if single_dot_period and c == "." and len(contours) > 1:
                # Doto draws the period as a small cross; one dot reads better next to digits.
                cx = sum(self._center(k)[0] for k in contours) / len(contours)
                cy = sum(self._center(k)[1] for k in contours) / len(contours)
                contours = [min(contours, key=lambda k: (self._center(k)[0] - cx) ** 2 + (self._center(k)[1] - cy) ** 2)]
            t = (s, 0, 0, -s, x, y)
            shapes = []
            for k in contours:
                kx, ky = self._center(k)
                shapes.append((self._draw(k, t), x + kx * s, y - ky * s))
            out.append(shapes)
            x += self.glyphs[name].width * s + tracking
        return out

    def text(self, text: str, x: float, y: float, size: float, fill: str, **kw) -> str:
        d = " ".join(shape[0] for ch in self.paths(text, x, y, size, **kw) for shape in ch)
        return f'<path fill="{fill}" d="{d}"/>'


_faces: dict[str, Face] = {}


def face(key: str) -> Face:
    if key not in _faces:
        doto = os.path.join(FONTS, "Doto.ttf")
        mono = os.path.join(FONTS, "JetBrainsMono.ttf")
        _faces[key] = {
            "dot": lambda: Face(doto, "Doto-Black", wght=900, ROND=100),
            "mono": lambda: Face(mono, "JetBrainsMono-Regular", wght=400),
            "mono-medium": lambda: Face(mono, "JetBrainsMono-Medium", wght=500),
        }[key]()
    return _faces[key]


def dots(text: str, x: float, y: float, size: float, fill: str, **kw) -> str:
    """Dot-matrix text."""
    return face("dot").text(text.lower(), x, y, size, fill, single_dot_period=True, **kw)


def label(text: str, x: float, y: float, fill: str, size: float = 12.5, anchor: str = "start") -> str:
    """Small letter-spaced label, like the ones on a spec sheet."""
    return face("mono").text(text.lower(), x, y, size, fill, tracking=size * 0.10, anchor=anchor)


def svg(w: int, h: int, c: dict, body: str, grid: bool = True, title: str = "", back: bool = True) -> str:
    defs = ""
    bg = f'<rect width="{w}" height="{h}" fill="{c["bg"]}"/>' if back else ""
    if grid:
        defs = (f'<defs><pattern id="g" width="16" height="16" patternUnits="userSpaceOnUse">'
                f'<circle cx="8" cy="8" r="0.9" fill="{c["dot"]}"/></pattern></defs>')
        bg += f'<rect width="{w}" height="{h}" fill="url(#g)"/>'
    name = f"<title>{title}</title>" if title else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img">{name}{defs}{bg}{body}</svg>\n')


def hline(x1: float, x2: float, y: float, color: str, width: float = 1) -> str:
    return f'<path d="M{x1} {y}H{x2}" stroke="{color}" stroke-width="{width}"/>'


def save(name: str, text: str):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"  {name}  {len(text) / 1024:.1f} KB")


# ------------------------------------------------------------------ pieces
def lamp(cx: float, cy: float, r: float, c: dict, level: float = 0.8) -> str:
    """The app's power button as a flat drawing: a matrix of dots inside a ring of brightness dots."""
    out = []
    n, ring = 60, r + 23                                       # the brightness dial
    lit = round(level * n)
    for i in range(n):
        a = math.radians(135 + 270 * i / (n - 1))
        x, y = cx + ring * math.cos(a), cy + ring * math.sin(a)
        if i < lit:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3.6 if i == lit - 1 else 1.9}" fill="{c["fg"]}"/>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.3" fill="{c["low"]}"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c["fg"]}" stroke-width="1.1"/>')
    pitch, cap = 9.5, 27                                        # the matrix
    steps = int(r / pitch) + 1
    for j in range(-steps, steps + 1):
        for i in range(-steps, steps + 1):
            x, y = i * pitch, j * pitch
            d = math.hypot(x, y)
            if d > r - 5.5 or d < cap + 5:
                continue
            rad = 3.3 * (1 - 0.52 * (d / r) ** 1.7)
            out.append(f'<circle cx="{cx + x:.1f}" cy="{cy + y:.1f}" r="{rad:.2f}" fill="{c["fg"]}"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{cap}" fill="{c["fg"]}"/>')          # the key, with the power symbol
    pr = 9.5
    a1, a2 = math.radians(-60), math.radians(240)
    out.append(f'<path d="M{cx + pr * math.cos(a1):.1f} {cy + pr * math.sin(a1):.1f}'
               f'A{pr} {pr} 0 1 1 {cx + pr * math.cos(a2):.1f} {cy + pr * math.sin(a2):.1f}" '
               f'fill="none" stroke="{c["bg"]}" stroke-width="2" stroke-linecap="round"/>')
    out.append(f'<path d="M{cx} {cy - pr * 1.25:.1f}V{cy - pr * 0.1:.1f}" stroke="{c["bg"]}" stroke-width="2" stroke-linecap="round"/>')
    return "".join(out)


def banner(theme: str) -> str:
    c = THEMES[theme]
    w, h, m = 1280, 440, 56
    b = [label("desktop app for wiz lights", m, 52, c["mid"]),
         label(f"v{VERSION}  /  windows  /  gpl-3.0", w - m, 52, c["mid"], anchor="end"),
         hline(m, w - m, 72, c["line"])]
    # Wordmark: one single dot carries the accent.
    chars = face("dot").paths("aura", m - 8, 258, 220)
    shapes = [s for ch in chars for s in ch]
    first = chars[0]
    mid_x = sum(k[1] for k in first) / len(first)
    top = min(first, key=lambda s: (round(s[2]), abs(s[1] - mid_x)))
    b.append(f'<path fill="{c["fg"]}" d="{" ".join(s[0] for s in shapes if s is not top)}"/>')
    b.append(f'<path fill="{ACCENT}" d="{top[0]}"/>')
    b.append(lamp(1088, 200, 76, c))
    b.append(face("mono").text("control your wiz lights from the pc, over the local network.", m, 330, 21, c["fg"]))
    b.append(hline(m, w - m, 364, c["line"]))
    col = (w - 2 * m) / 4
    for i, (k, v) in enumerate((("protocol", "udp 38899"), ("network", "local only"),
                                ("account", "none"), ("format", "portable zip"))):
        x = m + i * col
        b.append(label(k, x, 390, c["mid"], 11.5))
        b.append(dots(v, x - 1, 420, 27, c["fg"]))
    return svg(w, h, c, "".join(b), title="aura. control your wiz lights from the pc, over the local network.")


def section(theme: str, number: int, title: str) -> str:
    """A section title: index, dot-matrix name and a hairline."""
    c = THEMES[theme]
    w, h, m = 1280, 104, 56
    b = [f'<circle cx="{m + 5}" cy="35" r="3.2" fill="{ACCENT}"/>',
         label(f"{number:02d}", m + 18, 39, c["mid"], 12),
         dots(title, m - 2, 78, 36, c["fg"]),
         hline(m + face("dot").width(title.lower(), 36) + 22, w - m, 67, c["line"])]
    return svg(w, h, c, "".join(b), title=title.lower())


def divider(theme: str) -> str:
    c = THEMES[theme]
    w, h = 1280, 32
    row = "".join(f'<circle cx="{x}" cy="16" r="1.1" fill="{c["low"]}"/>' for x in range(64, w - 56, 16))
    return svg(w, h, c, row, grid=False)


def button(theme: str, text: str, note: str) -> str:
    """The download button: an inverted block on the black sheet, arrow drawn with lines."""
    c = THEMES[theme]
    w, h, m = 1280, 140, 56
    bw, bh = 470, 76
    x, y = m, (h - bh) // 2
    b = [f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="{c["fg"]}"/>',
         f'<path d="M{x + 34} {y + 25}V{y + 47}M{x + 24} {y + 38}L{x + 34} {y + 48}L{x + 44} {y + 38}M{x + 22} {y + 54}H{x + 46}" '
         f'fill="none" stroke="{c["bg"]}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
         dots(text, x + 66, y + 37, 26, c["bg"]),
         label(note, x + 68, y + 58, c["bg"], 11)]
    return svg(w, h, c, "".join(b), title=text.lower())


# ------------------------------------------------------------------ mounted screenshots (bitmaps)
def mount(shot: str, out: str, fig: int, caption: str, note: str = "rendered from source / tools/shots.py"):
    """A screenshot on a black sheet with a dot grid, framed and labelled like a figure."""
    from PIL import Image, ImageDraw, ImageFont

    c = THEMES["dark"]
    im = Image.open(os.path.join(SHOTS, shot)).convert("RGB")
    pad_x, pad_top, pad_bottom = 144, 150, 132
    w, h = im.width + 2 * pad_x, im.height + pad_top + pad_bottom
    sheet = Image.new("RGB", (w, h), c["bg"])
    d = ImageDraw.Draw(sheet)
    for gy in range(16, h, 32):
        for gx in range(16, w, 32):
            d.ellipse((gx - 2, gy - 2, gx + 2, gy + 2), fill=c["dot"])
    x0, y0 = pad_x, pad_top
    x1, y1 = x0 + im.width, y0 + im.height
    d.rectangle((x0 - 32, y0 - 118, x1 + 31, y1 + 105), fill=c["bg"])        # no grid behind the figure and its labels
    sheet.paste(im, (x0, y0))
    d.rectangle((x0 - 2, y0 - 2, x1 + 1, y1 + 1), outline=c["line"], width=2)
    for cx, cy, sx, sy in ((x0, y0, -1, -1), (x1, y0, 1, -1), (x0, y1, -1, 1), (x1, y1, 1, 1)):   # crop marks
        d.line((cx + sx * 14, cy, cx + sx * 44, cy), fill=c["low"], width=2)
        d.line((cx, cy + sy * 14, cx, cy + sy * 44), fill=c["low"], width=2)

    mono = ImageFont.truetype(face("mono").static_file(), 24)
    dot = ImageFont.truetype(face("dot").static_file(), 44)

    def spaced(x, y, text, font, fill, gap, anchor="l"):
        widths = [d.textlength(ch, font=font) + gap for ch in text]
        if anchor == "r":
            x -= sum(widths) - gap
        for ch, wd in zip(text, widths):
            d.text((x, y), ch, font=font, fill=fill)
            x += wd
        return x

    ty = y0 - 100
    end = spaced(x0 - 2, ty - 12, f"fig {fig:02d}", dot, c["fg"], 1)
    d.ellipse((end + 22, ty + 10, end + 34, ty + 22), fill=ACCENT)
    spaced(end + 58, ty + 1, caption.lower(), mono, c["mid"], 2)
    spaced(x1, ty + 1, f"{im.width // 2} x {im.height // 2} px", mono, c["mid"], 2, anchor="r")
    by = y1 + 60
    spaced(x0, by, note.lower(), mono, c["low"], 2)
    spaced(x1, by, f"aura {VERSION}", mono, c["low"], 2, anchor="r")
    os.makedirs(OUT, exist_ok=True)
    sheet.save(os.path.join(OUT, out), optimize=True)
    print(f"  {out}  {os.path.getsize(os.path.join(OUT, out)) / 1024:.0f} KB  {w}x{h}")


SECTIONS = ["screens", "why", "install", "use", "shortcuts and commands", "compared", "trust",
            "compatibility", "faq", "roadmap", "contributing", "credits and license"]

# (screenshot from tools/shots.py, caption)
FIGURES = [
    ("hero", "main window / color"),
    ("white", "white / 2200 to 6500 k"),
    ("scenes", "scenes / your own and the 28 in the light"),
    ("music", "effects / music"),
    ("screen", "effects / screen"),
    ("routines", "routines"),
    ("settings", "settings / sound"),
]


def slug(title: str) -> str:
    return title.lower().replace(" ", "-")


def main(only: list[str]):
    def want(name):
        return not only or name in only

    theme = "dark"                  # the readme is dark only
    if want("banner"):
        save("banner.svg", banner(theme))
    if want("sections"):
        for i, title in enumerate(SECTIONS, 1):
            save(f"title-{i:02d}-{slug(title)}.svg", section(theme, i, title))
        save("divider.svg", divider(theme))
        save("download.svg", button(theme, "download for windows", "portable zip  /  no installer  /  windows 11"))
    if want("figures"):
        for i, (shot, caption) in enumerate(FIGURES, 1):
            mount(f"{shot}.png", f"fig-{i:02d}-{shot}.png", i, caption)


if __name__ == "__main__":
    main(sys.argv[1:])
