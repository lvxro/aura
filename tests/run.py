"""Runs every test file, each in its own process, and reports which ones passed.

The tests need no real light: tests/fakebulb.py answers the WiZ protocol on this machine
(UDP port 38899, so close Aura first). They open the real interface on Qt's "offscreen"
platform, so they also run on a machine without a display.

Usage:  python tests/run.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["test_core.py", "test_ui.py", "test_features.py", "test_effects.py"]

failed = []
for name in FILES:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, os.path.join(HERE, name)], env=env, capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    ok = result.returncode == 0 and not any(line.startswith("FAIL ") for line in lines)
    print(f"{'pass' if ok else 'FAIL'}  {name}  ({sum(line.startswith('ok ') for line in lines)} checks)")
    if not ok:
        failed.append(name)
        print("\n".join(line for line in lines if line.startswith("FAIL ")))
        print(result.stderr[-2000:])
sys.exit(1 if failed else 0)
