# contributing

thanks for looking. aura is a small project with one maintainer, so the process is short.

## reporting a problem

open an issue and include:

- your windows version and the model of your wiz light (the name on the box, or what aura shows under the light's name in "your lights")
- what you did, what you expected, what happened
- the file `data\error.log` from the aura folder, if it exists

a report from a windows version or a wiz model that is not in the [compatibility table](README.md#compatibility) is useful even when everything works: say so and it gets added.

## running from source

```
python -m venv .venv
.venv\Scripts\activate            (linux and macos: source .venv/bin/activate)
pip install -r requirements-dev.txt
python app/main.py
```

settings go to a `data` folder at the root of the repository, which git ignores.

## tests

```
python tests/run.py
```

no real light is needed: `tests/fakebulb.py` answers the wiz protocol on your machine. it listens on udp port 38899, so close aura first. the tests open the real interface on qt's "offscreen" platform, click it, and check what the simulated light received.

the tests cannot cover what only windows does: global shortcuts, lock and sleep events, the start-with-windows registry entry, and sound playback. if you touch those, try them by hand on windows and say so in the pull request.

## pull requests

- keep changes small and say what you tested, and on what.
- interface text goes through `t()` in `app/aura/i18n.py`, with a spanish translation. `python tools/check_i18n.py` tells you if one is missing.
- the interface is lowercase, monochrome, and uses two typefaces (doto for headlines and numbers, jetbrains mono for the rest). the only color on screen is the light's own.
- comments are in english and explain why, not what.
- no telemetry, no accounts, no network traffic beyond the local wiz protocol. a change that adds any of those will not be merged.

## building the portable zip

```
python tools/fetch_deps.py        downloads python and the wheels, checks their sha-256
python tools/build_launcher.py    compiles Aura.exe with zig
python tools/build_portable.py    assembles dist/Aura and zips it
```

this has only been run on linux. the scripts are plain python and should work elsewhere, but that is untested.

## license

by contributing you agree that your work is released under the gpl-3.0, the license of the project.
