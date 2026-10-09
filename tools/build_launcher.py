"""Compiles Aura.exe, the small launcher that starts the bundled Python without a console window.

It cross-compiles with zig (pip install ziglang), so it works from Linux, macOS or Windows.
The result goes to build/Aura.exe.

Usage:  python tools/build_launcher.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "launcher")
OUT = os.path.join(ROOT, "build", "Aura.exe")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subprocess.check_call(
        [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-s",
         "-Wl,--subsystem,windows",
         "-o", OUT, "launcher.c", "aura.rc", "-lshell32"],
        cwd=SRC)
    for leftover in ("Aura.pdb",):
        path = os.path.join(os.path.dirname(OUT), leftover)
        if os.path.exists(path):
            os.remove(path)
    print("built", os.path.relpath(OUT, ROOT), os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
