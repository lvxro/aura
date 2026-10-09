"""Prepares the fonts the app ships: static files cut from the variable originals in docs/fonts,
each weight under its own family name so it resolves the same on every system.

Sources (SIL Open Font License): Doto and JetBrains Mono, from github.com/google/fonts.

Usage:  python tools/make_fonts.py
"""
import os

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "fonts")
d = os.path.join(ROOT, "app", "aura", "fonts") + os.sep


def _contours(glyphs, name):
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    out, cur = [], []
    for op, args in pen.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur); cur = []
    return out


def _center(contour):
    pts = [p for _op, args in contour for p in args]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def single_dots(font, names=("period", "colon")):
    """Doto draws '.' and ':' as small crosses of five dots. Next to digits (1.0, 07:30)
    a single dot per mark reads better, so only the middle dot of each cross is kept."""
    glyphs = font.getGlyphSet()
    for name in names:
        contours = _contours(glyphs, name)
        if len(contours) < 5:
            continue
        ys = sorted(_center(c)[1] for c in contours)
        split = (ys[0] + ys[-1]) / 2
        groups = [contours] if name == "period" else [[c for c in contours if _center(c)[1] < split],
                                                       [c for c in contours if _center(c)[1] >= split]]
        keep = []
        for g in groups:
            cx = sum(_center(c)[0] for c in g) / len(g); cy = sum(_center(c)[1] for c in g) / len(g)
            keep.append(min(g, key=lambda c: (_center(c)[0] - cx) ** 2 + (_center(c)[1] - cy) ** 2))
        pen = TTGlyphPen(None)
        for c in keep:
            for op, args in c:
                getattr(pen, op)(*args)
        font["glyf"][name] = pen.glyph()


def make_static(src, axes, family, out, weight, fix=None):
    f = instancer.instantiateVariableFont(TTFont(src), axes)
    if fix:
        fix(f)
    name = f["name"]
    for rec in list(name.names):
        if rec.nameID in (16, 17, 25, 21, 22):
            name.removeNames(nameID=rec.nameID)
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(family, 1, pid, eid, lid)
        name.setName("Regular", 2, pid, eid, lid)
        name.setName(family, 4, pid, eid, lid)
        name.setName(family.replace(" ", "") + "-Regular", 6, pid, eid, lid)
        name.setName(f"{family};aura", 3, pid, eid, lid)
    f["OS/2"].usWeightClass = weight
    f["OS/2"].fsSelection = (f["OS/2"].fsSelection & ~0x61) | 0x40
    f["head"].macStyle = 0
    if "STAT" in f: del f["STAT"]
    f.save(out)
    print(os.path.relpath(out, ROOT), axes)


make_static(os.path.join(SRC, "Doto.ttf"), {"wght": 900, "ROND": 100}, "Doto", d + "Doto-Black.ttf", 400, fix=single_dots)
for wght, style in ((400, "Regular"), (500, "Medium"), (600, "SemiBold")):
    family = "JetBrains Mono" if style == "Regular" else f"JetBrains Mono {style}"
    make_static(os.path.join(SRC, "JetBrainsMono.ttf"), {"wght": wght}, family, d + f"JetBrainsMono-{style}.ttf", 400)
