"""Downloads what the portable build bundles, and checks every file against a pinned SHA-256.

  - CPython 3.12.10 for Windows (python-build-standalone, "install_only_stripped")
  - the Windows wheels of PySide6-Essentials, shiboken6, mss and PyAudioWPatch

Everything lands in build/deps. Nothing here is committed to the repository.

Usage:  python tools/fetch_deps.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS = os.path.join(ROOT, "build", "deps")
DOWNLOADS = os.path.join(DEPS, "downloads")

PYTHON = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20250409/"
    "cpython-3.12.10%2B20250409-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    "python-3.12.10-windows.tar.gz",
    "08670ab68f041481b8127b2ea27e01ddf56131e61fcf845f489024fddcd3deec",
)
# (requirement, wheel file name, sha256)
WHEELS = (
    ("PySide6-Essentials==6.12.0", "pyside6_essentials-6.12.0-cp310-abi3-win_amd64.whl",
     "c9a95102aa23c1f86516a30d5a9be37552d324eee7e567eb7508973f1218cb42"),
    ("shiboken6==6.12.0", "shiboken6-6.12.0-cp310-abi3-win_amd64.whl",
     "a1906cb8116869178c64b6bab52623bbc8b4ceed7b30bfc3c9aa0f6e67f6438e"),
    ("mss==10.2.0", "mss-10.2.0-py3-none-any.whl",
     "e79f428899280e7e64e38365b5bfed683851ebea807eeaeadaf06eb8e0d67197"),
    ("PyAudioWPatch==0.2.12.9", "pyaudiowpatch-0.2.12.9-cp312-cp312-win_amd64.whl",
     "963376e94f46c84e994eda4d25ffd62b712881ad5d611a4f4433bb5aa0bf7fa4"),
)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check(path: str, expected: str):
    got = sha256(path)
    if got != expected:
        sys.exit(f"checksum mismatch for {os.path.basename(path)}\n  expected {expected}\n  got      {got}")
    print(f"  ok  {os.path.basename(path)}")


def main():
    os.makedirs(DOWNLOADS, exist_ok=True)

    url, name, digest = PYTHON
    archive = os.path.join(DOWNLOADS, name)
    if not os.path.isfile(archive):
        print("downloading", name)
        urllib.request.urlretrieve(url, archive)
    check(archive, digest)
    target = os.path.join(DEPS, "python")
    shutil.rmtree(target, ignore_errors=True)
    with tarfile.open(archive) as tar:
        tar.extractall(DEPS, filter="data")          # the archive holds a single "python" folder

    wheels = os.path.join(DEPS, "wheels")
    shutil.rmtree(wheels, ignore_errors=True)
    os.makedirs(wheels)
    for requirement, filename, digest in WHEELS:
        path = os.path.join(DOWNLOADS, filename)
        if not os.path.isfile(path):
            print("downloading", requirement)
            subprocess.check_call([sys.executable, "-m", "pip", "download", "--quiet", "--no-deps",
                                   "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.12",
                                   "--implementation", "cp", "--dest", DOWNLOADS, requirement])
        check(path, digest)
        with zipfile.ZipFile(path) as z:
            z.extractall(wheels)
    print("dependencies ready in", os.path.relpath(DEPS, ROOT))


if __name__ == "__main__":
    main()
