"""Local protocol of WiZ lights: JSON over UDP, port 38899.

No cloud involved. Everything travels over the Wi-Fi network the bulb is connected to.
"""

from __future__ import annotations

import json
import math
import socket
import threading
import time

PORT = 38899
MIN_TEMP = 2200
MAX_TEMP = 6500
MIN_DIM = 10

# Scenes built into the bulb. They run inside the bulb, without the PC.
# (id, name, dynamic, thumbnail colors)
SCENES = [
    (6, "Cozy", False, ("#ffb347", "#ff7b39")),
    (16, "Relax", False, ("#ffc98a", "#ff9d5c")),
    (15, "Focus", False, ("#f3f6ff", "#bcd4ff")),
    (18, "TV time", False, ("#8e7dff", "#3d5bff")),
    (10, "Bedtime", False, ("#ff8a3d", "#a8431c")),
    (14, "Night light", False, ("#ff7a2e", "#5a2410")),
    (9, "Wake up", True, ("#ffd27a", "#ff8f66")),
    (29, "Candlelight", True, ("#ffae42", "#d9611c")),
    (5, "Fireplace", True, ("#ff8c2b", "#d1361a")),
    (3, "Sunset", True, ("#ff9a4d", "#e2466f")),
    (2, "Romance", True, ("#ff5d8f", "#b3267a")),
    (1, "Ocean", True, ("#28c8ff", "#2b55e6")),
    (23, "Deep dive", True, ("#1f8fff", "#1a2fb8")),
    (7, "Forest", True, ("#5fd66a", "#1f8a55")),
    (24, "Jungle", True, ("#9be042", "#1f9a4a")),
    (25, "Mojito", True, ("#c8f24a", "#3fc48a")),
    (20, "Spring", True, ("#ffa3c7", "#8fe08a")),
    (21, "Summer", True, ("#ffd23f", "#ff8a3d")),
    (22, "Fall", True, ("#ff9736", "#b5451f")),
    (8, "Pastel colors", True, ("#ffb3d1", "#a8c8ff")),
    (4, "Party", True, ("#ff3d9a", "#7a4dff")),
    (26, "Club", True, ("#c13dff", "#2b6bff")),
    (31, "Pulse", True, ("#ff4d6d", "#ffb347")),
    (32, "Steampunk", True, ("#e0a04a", "#7a5230")),
    (27, "Christmas", True, ("#ff4040", "#2fb05a")),
    (28, "Halloween", True, ("#ff8a1f", "#7a2fd6")),
    (17, "True colors", False, ("#ffffff", "#ffe9c9")),
    (19, "Plant growth", False, ("#ff5db8", "#8f5dff")),
]
SCENE_NAMES = {sid: name for sid, name, _dyn, _c in SCENES}


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def kelvin_to_rgb(temp_k: float) -> tuple[int, int, int]:
    """Approximate a color temperature as RGB, for drawing the interface."""
    t = temp_k / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0
    return (int(clamp(r, 0, 255)), int(clamp(g, 0, 255)), int(clamp(b, 0, 255)))


def format_mac(mac: str | None) -> str:
    if not mac or len(mac) != 12:
        return mac or ""
    return ":".join(mac[i:i + 2] for i in range(0, 12, 2)).upper()


def is_valid_ip(text: str) -> bool:
    parts = text.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 and p == str(int(p)) for p in parts)
    except ValueError:
        return False


def _encode(method: str, params: dict | None) -> bytes:
    return json.dumps({"method": method, "params": params or {}},
                      separators=(",", ":")).encode("utf-8")


class Sender:
    """Reusable socket for sending commands without waiting for a reply."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._lock = threading.Lock()

    def send(self, ip: str, method: str, params: dict | None = None) -> bool:
        if not ip:
            return False
        try:
            with self._lock:
                self._sock.sendto(_encode(method, params), (ip, PORT))
            return True
        except OSError:
            return False

    def drain(self) -> int:
        """Discard the accumulated replies. Returns how many there were."""
        n = 0
        with self._lock:
            while True:
                try:
                    self._sock.recvfrom(4096)
                    n += 1
                except (BlockingIOError, OSError):
                    break
        return n

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


def request(ip: str, method: str, params: dict | None = None,
            timeout: float = 0.7, attempts: int = 2) -> dict | None:
    """Send a command and wait for the result. Returns None if there is no answer."""
    if not ip:
        return None
    payload = _encode(method, params)
    for _ in range(attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(timeout)
            sock.sendto(payload, (ip, PORT))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                data, _addr = sock.recvfrom(4096)
                try:
                    decoded = json.loads(data.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if decoded.get("method") == method and "result" in decoded:
                    return decoded.get("result") or {}
        except OSError:
            pass
        finally:
            sock.close()
    return None


def get_pilot(ip: str, **kw) -> dict | None:
    return request(ip, "getPilot", **kw)


def get_system_config(ip: str, **kw) -> dict | None:
    return request(ip, "getSystemConfig", **kw)


def local_ipv4_addresses() -> list[str]:
    """Local IPs of this machine (one per network adapter)."""
    found: list[str] = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    # The IP "normal" traffic leaves through: nothing is sent, it only asks the routing table.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.168.255.255", 9))
            ip = probe.getsockname()[0]
            if ip not in found:
                found.insert(0, ip)
        finally:
            probe.close()
    except OSError:
        pass
    return [ip for ip in found if not ip.startswith("127.") and not ip.startswith("169.254.")]


def _friendly_model(module_name: str | None) -> str:
    """ESP01_SHRGB1C_31 -> 'WiZ color light', etc. Just to show something readable."""
    if not module_name:
        return "WiZ light"
    m = module_name.upper()
    if "RGB" in m:
        return "WiZ color light"
    if "TW" in m:
        return "WiZ tunable white light"
    if "DW" in m:
        return "WiZ white light"
    if "SOCKET" in m or "PLUG" in m:
        return "WiZ plug"
    return "WiZ light"


def discover(timeout: float = 1.2, attempts: int = 3, on_found=None,
             stop: threading.Event | None = None) -> list[dict]:
    """Find WiZ lights on the local network.

    Broadcasts the query on every network adapter (so it works even with a VPN
    or virtual adapters) and collects the replies.
    Returns a list of {"ip", "mac", "module", "model"}.
    """
    found: dict[str, dict] = {}
    socks: list[socket.socket] = []
    targets: list[tuple[socket.socket, str]] = []

    def open_sock(bind_ip: str | None):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if bind_ip:
                s.bind((bind_ip, 0))
            s.setblocking(False)
        except OSError:
            s.close()
            return None
        socks.append(s)
        return s

    for ip in local_ipv4_addresses():
        s = open_sock(ip)
        if s is None:
            continue
        targets.append((s, "255.255.255.255"))
        targets.append((s, ip.rsplit(".", 1)[0] + ".255"))
    if not socks:
        s = open_sock(None)
        if s is not None:
            targets.append((s, "255.255.255.255"))

    queries = [_encode("getSystemConfig", {}), _encode("getPilot", {})]

    def handle(data: bytes, addr):
        try:
            decoded = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            return
        result = decoded.get("result")
        if not isinstance(result, dict):
            return
        ip = addr[0]
        entry = found.get(ip)
        is_new = entry is None
        if entry is None:
            entry = found[ip] = {"ip": ip, "mac": None, "module": None, "model": "WiZ light"}
        changed = is_new
        mac = result.get("mac")
        if mac and not entry["mac"]:
            entry["mac"] = str(mac).lower()
            changed = True
        module = result.get("moduleName")
        if module and not entry["module"]:
            entry["module"] = module
            entry["model"] = _friendly_model(module)
            changed = True
        if changed and on_found and entry["mac"]:
            on_found(dict(entry))

    try:
        for _ in range(attempts):
            if stop is not None and stop.is_set():
                break
            for s, target in targets:
                for q in queries:
                    try:
                        s.sendto(q, (target, PORT))
                    except OSError:
                        pass
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if stop is not None and stop.is_set():
                    break
                got = False
                for s in socks:
                    try:
                        data, addr = s.recvfrom(4096)
                    except (BlockingIOError, OSError):
                        continue
                    got = True
                    handle(data, addr)
                if not got:
                    time.sleep(0.03)
    finally:
        for s in socks:
            s.close()
    return [e for e in found.values() if e["mac"]]


def pilot_for(state: dict) -> dict:
    """Build the setPilot parameters from an app state."""
    if not state.get("on", True):
        return {"state": False}
    params: dict = {"state": True, "dimming": int(clamp(state.get("brightness", 100), MIN_DIM, 100))}
    mode = state.get("mode", "white")
    if mode == "rgb":
        r, g, b = state.get("rgb", (255, 255, 255))
        r, g, b = int(clamp(r, 0, 255)), int(clamp(g, 0, 255)), int(clamp(b, 0, 255))
        if r == 0 and g == 0 and b == 0:
            r = 1
        params.update({"r": r, "g": g, "b": b})
    elif mode == "scene":
        params["sceneId"] = int(state.get("scene", 6))
        params["speed"] = int(clamp(state.get("speed", 100), 20, 200))
    else:
        params["temp"] = int(clamp(state.get("temp", 4000), MIN_TEMP, MAX_TEMP))
    return params


def state_from_pilot(result: dict) -> dict:
    """Translate a getPilot reply into an app state."""
    out: dict = {"on": bool(result.get("state", True))}
    dim = result.get("dimming")
    if dim is not None:
        out["brightness"] = int(clamp(int(dim), MIN_DIM, 100))
    scene = int(result.get("sceneId") or 0)
    r, g, b = result.get("r"), result.get("g"), result.get("b")
    temp = result.get("temp")
    if scene and scene in SCENE_NAMES and temp is None and not (r or g or b):
        out["mode"] = "scene"
        out["scene"] = scene
        if result.get("speed") is not None:
            out["speed"] = int(result["speed"])
    elif r is not None and g is not None and b is not None and (r or g or b):
        out["mode"] = "rgb"
        out["rgb"] = (int(r), int(g), int(b))
    elif temp is not None:
        out["mode"] = "white"
        out["temp"] = int(clamp(int(temp), MIN_TEMP, MAX_TEMP))
    elif scene and scene in SCENE_NAMES:
        out["mode"] = "scene"
        out["scene"] = scene
    return out
