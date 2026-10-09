"""Assembles the portable Windows folder and zips it.

Before running it:
    python tools/fetch_deps.py        downloads Python and the wheels into build/deps
    python tools/build_launcher.py    compiles build/Aura.exe

Result:  dist/Aura/                         the folder people unzip and run
         dist/aura-<version>-portable.zip   the release file
         dist/aura-<version>-portable.zip.sha256

It runs on Linux (it only copies files), and it checks that every DLL the bundled
binaries import is either in the folder or part of Windows.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import sys
import zipfile

import pefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS = os.path.join(ROOT, "build", "deps")
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, "Aura")
ZIP_TIME = (2026, 1, 1, 0, 0, 0)        # one fixed date for every entry, so equal inputs give an equal zip

with open(os.path.join(ROOT, "app", "aura", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)


def as_notepad_text(src: str, dst: str):
    """UTF-8 with a signature and Windows line endings, so Notepad shows it right everywhere."""
    with open(src, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n").replace("\n", "\r\n")
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)


def program():
    launcher = os.path.join(ROOT, "build", "Aura.exe")
    if not os.path.isfile(launcher):
        sys.exit("build/Aura.exe is missing: run tools/build_launcher.py first")
    shutil.copy(launcher, os.path.join(OUT, "Aura.exe"))
    shutil.copytree(os.path.join(ROOT, "app"), os.path.join(OUT, "app"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(os.path.join(ROOT, "launcher", "aura.ico"), os.path.join(OUT, "app", "aura.ico"))
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(OUT, "LICENSE.txt"))
    for name in ("README.txt", "CREDITS.txt"):
        as_notepad_text(os.path.join(ROOT, "packaging", name), os.path.join(OUT, name))
    sounds = os.path.join(OUT, "app", "aura", "sounds", "LICENSES.txt")
    as_notepad_text(sounds, sounds)
    # The launcher's source travels with the program.
    os.makedirs(os.path.join(OUT, "app", "launcher"))
    for name in ("launcher.c", "aura.rc", "aura.manifest"):
        shutil.copy(os.path.join(ROOT, "launcher", name), os.path.join(OUT, "app", "launcher", name))


def python_runtime() -> str:
    source = os.path.join(DEPS, "python")
    if not os.path.isdir(source):
        sys.exit("build/deps is missing: run tools/fetch_deps.py first")
    rt = os.path.join(OUT, "runtime")
    shutil.copytree(source, rt)
    for d in ("tcl", "include", "libs", "Scripts", "Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo",
              "Lib/ensurepip", "Lib/lib2to3", "Lib/venv", "Lib/pydoc_data", "Lib/site-packages"):
        shutil.rmtree(os.path.join(rt, d), ignore_errors=True)
    for f in ("DLLs/_tkinter.pyd", "DLLs/tcl86t.dll", "DLLs/tk86t.dll", "DLLs/zlib1.dll", "Lib/turtle.py",
              "DLLs/_testcapi.pyd", "DLLs/_testinternalcapi.pyd", "DLLs/_testbuffer.pyd", "DLLs/_testclinic.pyd",
              "DLLs/_testconsole.pyd", "DLLs/_testimportmultiple.pyd", "DLLs/_testmultiphase.pyd",
              "DLLs/_testsinglephase.pyd", "DLLs/_ctypes_test.pyd", "DLLs/_sqlite3.pyd", "DLLs/sqlite3.dll"):
        p = os.path.join(rt, f)
        if os.path.exists(p):
            os.remove(p)
    for base, dirs, _files in os.walk(os.path.join(rt, "Lib")):
        for d in list(dirs):
            if d in ("__pycache__", "tests", "test", "idle_test"):
                shutil.rmtree(os.path.join(base, d))
                dirs.remove(d)
    return rt


def packages(rt: str):
    """Only the parts of each package that Aura uses: Qt Core, Gui, Widgets, Svg and Network."""
    sp = os.path.join(rt, "Lib", "site-packages")
    os.makedirs(sp)
    w = os.path.join(DEPS, "wheels")
    for name in ("shiboken6", "shiboken6-6.12.0.dist-info", "mss", "mss-10.2.0.dist-info",
                 "pyaudiowpatch", "pyaudiowpatch-0.2.12.9.dist-info", "pyside6_essentials-6.12.0.dist-info"):
        shutil.copytree(os.path.join(w, name), os.path.join(sp, name))
    shutil.copy(os.path.join(w, "_portaudiowpatch.cp312-win_amd64.pyd"), sp)
    for base, _dirs, files in os.walk(sp):
        for f in files:
            if f.endswith((".pyi", ".lib", ".pdb")):
                os.remove(os.path.join(base, f))
    qt_src, qt_dst = os.path.join(w, "PySide6"), os.path.join(sp, "PySide6")
    os.makedirs(qt_dst)
    keep = ["__init__.py", "_config.py", "_git_pyside_version.py", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd",
            "QtSvg.pyd", "QtNetwork.pyd", "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Svg.dll",
            "Qt6Network.dll", "pyside6.abi3.dll", "msvcp140*.dll", "concrt140.dll", "vcruntime140*.dll", "support"]
    for f in sorted(os.listdir(qt_src)):
        if any(fnmatch.fnmatch(f, k) for k in keep):
            src = os.path.join(qt_src, f)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(qt_dst, f))
    plugins = {"platforms": ["qwindows.dll"], "styles": ["*"], "iconengines": ["qsvgicon.dll"],
               "imageformats": ["qsvg.dll", "qico.dll", "qjpeg.dll", "qgif.dll"]}
    for d, patterns in plugins.items():
        os.makedirs(os.path.join(qt_dst, "plugins", d))
        for f in sorted(os.listdir(os.path.join(qt_src, "plugins", d))):
            if any(fnmatch.fnmatch(f, p) for p in patterns):
                shutil.copy(os.path.join(qt_src, "plugins", d, f), os.path.join(qt_dst, "plugins", d, f))
    for base, dirs, _files in os.walk(OUT):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(base, d))
                dirs.remove(d)


# DLLs that ship with Windows; everything else a binary imports must be inside the folder.
SYSTEM = """kernel32 user32 gdi32 advapi32 shell32 ole32 oleaut32 ws2_32 winmm version dwmapi uxtheme imm32 d3d11 dxgi
dwrite d2d1 comdlg32 shlwapi userenv netapi32 iphlpapi dnsapi crypt32 secur32 bcrypt ncrypt wtsapi32 setupapi mpr authz
psapi powrprof shcore propsys avrt d3d9 d3d12 opengl32 winspool.drv rpcrt4 cfgmgr32 ntdll msvcrt comctl32 winhttp
wininet dbghelp pdh mswsock cryptbase sspicli normaliz winusb hid ksuser mfplat mf mfreadwrite uiautomationcore
dcomp dxva2 wintrust usp10 oleacc mscoree bcryptprimitives pathcch synchronization ucrtbase
cabinet msi d3dcompiler_47 icuuc icuin icu mscms""".split()


def check_imports() -> dict:
    have, binaries = {}, []
    for base, _dirs, files in os.walk(OUT):
        for f in files:
            if f.lower().endswith((".dll", ".pyd", ".exe")):
                have[f.lower()] = os.path.join(base, f)
                binaries.append(os.path.join(base, f))
    missing: dict[str, list[str]] = {}
    for path in binaries:
        try:
            pe = pefile.PE(path, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        except Exception as e:
            print("not a PE file:", path, e)
            continue
        assert pe.FILE_HEADER.Machine == 0x8664, f"{path} is not 64-bit"
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
            name = entry.dll.decode().lower()
            stem = name[:-4] if name.endswith(".dll") else name
            if name in have or stem in SYSTEM or name in SYSTEM or name.startswith(("api-ms-win-", "ext-ms-")):
                continue
            missing.setdefault(name, []).append(os.path.relpath(path, OUT))
    print(f"binaries: {len(binaries)} | unresolved DLLs: {missing if missing else 'none'}")
    return missing


def make_zip() -> str:
    path = os.path.join(DIST, f"aura-{VERSION}-portable.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for base, dirs, files in os.walk(OUT):
            dirs.sort()
            for f in sorted(files):
                full = os.path.join(base, f)
                info = zipfile.ZipInfo(os.path.join("Aura", os.path.relpath(full, OUT)).replace(os.sep, "/"), ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as src:
                    zf.writestr(info, src.read(), compresslevel=9)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(path + ".sha256", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(path)}\n")
    print(f"zip: {os.path.getsize(path) / 1e6:.1f} MB  sha256 {digest}")
    return path


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(OUT)
    program()
    packages(python_runtime())
    missing = check_imports()
    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(OUT) for f in fs)
    count = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"folder: {total / 1e6:.1f} MB in {count} files")
    make_zip()
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
