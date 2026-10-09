"""Short feedback sounds for turning the light on and off.

Every sound is a real recording of a mechanical keyboard switch: one full
keystroke, key down and back up. Turning the light on plays a letter key;
turning it off plays the space bar, which is deeper.

The recordings come from two MIT-licensed projects, Mechvibes and kbsim
(see sounds/LICENSES.txt). They were only trimmed and levelled.

People can also use their own: a file named on.wav (and optionally off.wav)
in the "sounds" folder inside Aura's data folder shows up as "Custom".

Playback uses Windows' own player, so nothing extra is bundled.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

# (id, name, kind of switch). Names are product names and are never translated.
SOUNDS = (
    ("cream", "NK Cream", "Linear"),
    ("blackink", "Black Ink", "Linear"),
    ("mxblack", "MX Black", "Linear"),
    ("mxred", "MX Red", "Linear"),
    ("holypanda", "Holy Panda", "Tactile"),
    ("oreo", "EG Oreo", "Tactile"),
    ("crystal", "Crystal Purple", "Tactile"),
    ("topre", "Topre", "Tactile"),
    ("mxbrown", "MX Brown", "Tactile"),
    ("mxblue", "MX Blue", "Clicky"),
    ("boxnavy", "Box Navy", "Clicky"),
    ("alps", "Alps Blue", "Clicky"),
    ("buckling", "Buckling Spring", "Clicky"),
)
STYLES = tuple(s[0] for s in SOUNDS)
CUSTOM = "custom"
OFF = "off"
DEFAULT = "cream"


def normalize(style) -> str:
    """A saved choice, made valid. Choices from earlier versions fall back to the default."""
    return style if style in STYLES or style in (CUSTOM, OFF) else DEFAULT


def path_for(style: str, kind: str) -> str:
    return os.path.join(HERE, f"{style}_{kind}.wav")


class Player:
    """Plays the on/off sounds without blocking. Silent where there is no player (non-Windows)."""

    def __init__(self, data_dir: str | None = None, style: str = DEFAULT):
        self.style = normalize(style)
        self.custom_dir = os.path.join(data_dir, "sounds") if data_dir else None
        self.played: list[str] = []                  # what was asked to play (useful in tests)

    @property
    def enabled(self) -> bool:
        return self.style != OFF

    def has_custom(self) -> bool:
        return self.custom_path("on") is not None

    def custom_path(self, kind: str) -> str | None:
        """The person's own file. Without an off.wav, on.wav is used for both."""
        if not self.custom_dir:
            return None
        for name in (f"{kind}.wav", "on.wav"):
            p = os.path.join(self.custom_dir, name)
            if os.path.isfile(p):
                return p
        return None

    def file(self, kind: str) -> str | None:
        if self.style == OFF:
            return None
        p = self.custom_path(kind) if self.style == CUSTOM else path_for(self.style, kind)
        return p if p and os.path.isfile(p) else None

    def play(self, kind: str):
        path = self.file(kind)
        if not path:
            return
        self.played.append(f"{self.style}:{kind}")
        if sys.platform != "win32":
            return
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass
