"""Aura entry point. Usage: pythonw main.py [--toggle | --on | --off | --hidden]"""

import os
import sys
import traceback

# No console (windowed program) means no stdout or stderr: give them somewhere to go.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _log_crash():
    """Without a console there is nowhere to see an error: it is written to data/error.log."""
    try:
        from aura.store import data_dir
        with open(os.path.join(data_dir(), "error.log"), "a", encoding="utf-8") as f:
            import datetime
            f.write(f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} ---\n")
            traceback.print_exc(file=f)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from aura.app import main
        code = main()
    except SystemExit:
        raise
    except Exception:
        _log_crash()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "Aura couldn't start. The details are in data\\error.log, next to the program.\n\n"
                    "Aura no pudo iniciar. El detalle quedó en data\\error.log, al lado del programa.",
                    "Aura", 0x10)
            except Exception:
                pass
        else:
            traceback.print_exc()
        code = 1
    sys.exit(code)
