"""Fake WiZ bulb: answers getPilot / setPilot / getSystemConfig over UDP."""
import json, socket, threading, time

class FakeBulb(threading.Thread):
    def __init__(self, host="0.0.0.0", port=38899, mac="a8bb50aabbcc", module="ESP01_SHRGB1C_31"):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.mac, self.module = mac, module
        self.pilot = {"state": True, "sceneId": 0, "temp": 2700, "dimming": 80}
        self.log = []
        self.alive = True
    def run(self):
        while self.alive:
            try:
                data, addr = self.sock.recvfrom(4096)
            except OSError:
                break
            try:
                msg = json.loads(data.decode())
            except ValueError:
                continue
            m, params = msg.get("method"), msg.get("params") or {}
            self.log.append((time.monotonic(), m, params))
            if m == "getPilot":
                res = {"mac": self.mac, "rssi": -55, "src": "", **self.pilot}
            elif m == "getSystemConfig":
                res = {"mac": self.mac, "homeId": 1, "roomId": 1, "moduleName": self.module, "fwVersion": "1.31.0"}
            elif m == "setPilot":
                p = dict(self.pilot)
                if "state" in params: p["state"] = params["state"]
                if "dimming" in params: p["dimming"] = params["dimming"]
                if "temp" in params:
                    for k in ("r","g","b","c","w"): p.pop(k, None)
                    p["temp"] = params["temp"]; p["sceneId"] = 0
                if "r" in params:
                    p.pop("temp", None); p["sceneId"] = 0
                    p.update(r=params["r"], g=params["g"], b=params["b"], c=0, w=0)
                if "sceneId" in params:
                    for k in ("r","g","b","c","w","temp"): p.pop(k, None)
                    p["sceneId"] = params["sceneId"]; p["speed"] = params.get("speed", 100)
                self.pilot = p
                res = {"success": True}
            else:
                continue
            self.sock.sendto(json.dumps({"method": m, "env": "pro", "result": res}).encode(), addr)
    def stop(self):
        self.alive = False
        self.sock.close()

if __name__ == "__main__":
    b = FakeBulb(); b.start(); print("fake bulb on :38899")
    while True: time.sleep(1)
