"""Checks that every interface string has a Spanish translation, and that no translation is unused.

Usage:  python tools/check_i18n.py      (needs the same packages as the tests)
"""
import ast, glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
from aura import i18n
used = set()
for f in glob.glob(os.path.join(ROOT, "app", "aura", "*.py")):
    tree = ast.parse(open(f, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("t", "t_name") and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                used.add(a.value)
# constants that are translated when shown
from aura import effects, wiz, store, sound
from aura.window import SettingsSheet
for _i, _n, kind in sound.SOUNDS: used.add(kind)
used.update([SettingsSheet.SOUND_INTRO, SettingsSheet.SOUND_CUSTOM_HELP])
for _k, n, d in effects.MUSIC_MODES + effects.SCREEN_MODES: used.update((n, d))
for _i, n, _d, _c in wiz.SCENES: used.add(n)
for f in store.DEFAULTS["favorites"]["rgb"] + store.DEFAULTS["favorites"]["white"]: used.add(f["name"])
for s in store.DEFAULTS["scenes"]: used.add(s["name"])
used.update(["Candlelight", "Warm light", "Neutral light", "Daylight", "Cool light", "My light", "WiZ light", "WiZ color light", "WiZ tunable white light", "WiZ white light", "WiZ plug", "Turn on and off", "Brighter", "Dimmer", "Next favorite"])
same = {"Color", "Normal", "Natural", "Relax", "Aqua", "Mojito", "Club", "Steampunk", "Halloween", "Romance", "Aurora", "Mono", "min", "Clicky", "General", "Color {n}", "{n} s"}
missing = sorted(u for u in used if u not in i18n.ES and u not in same)
unused = sorted(k for k in i18n.ES if k not in used)
print("missing:", len(missing)); [print("  ", repr(m)) for m in missing]
print("unused:", len(unused)); [print("  ", repr(m)) for m in unused]
sys.exit(1 if missing or unused else 0)
