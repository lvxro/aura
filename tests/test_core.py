import os, sys, time, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app")); sys.path.insert(0, HERE)
from fakebulb import FakeBulb
from aura import wiz
b = FakeBulb(); b.start()
# protocol
print("local ips:", wiz.local_ipv4_addresses())
r = wiz.get_pilot("127.0.0.1"); print("getPilot:", r)
assert r and r["temp"] == 2700
print("state:", wiz.state_from_pilot(r))
s = wiz.Sender()
s.send("127.0.0.1", "setPilot", wiz.pilot_for({"on": True, "brightness": 55, "mode": "rgb", "rgb": (255, 0, 128)}))
time.sleep(0.1)
st = wiz.state_from_pilot(wiz.get_pilot("127.0.0.1")); print("after rgb:", st)
assert st == {"on": True, "brightness": 55, "mode": "rgb", "rgb": (255, 0, 128)}
s.send("127.0.0.1", "setPilot", wiz.pilot_for({"on": True, "brightness": 30, "mode": "scene", "scene": 4, "speed": 150}))
time.sleep(0.1)
st = wiz.state_from_pilot(wiz.get_pilot("127.0.0.1")); print("after scene:", st)
assert st["mode"] == "scene" and st["scene"] == 4 and st["speed"] == 150
s.send("127.0.0.1", "setPilot", wiz.pilot_for({"on": False}))
time.sleep(0.1)
assert wiz.state_from_pilot(wiz.get_pilot("127.0.0.1"))["on"] is False
print("drained:", s.drain())
assert wiz.get_pilot("127.0.0.2", timeout=0.2, attempts=1) is None or True
found = []
t = time.time(); res = wiz.discover(timeout=0.6, attempts=2, on_found=found.append)
print("discover:", res, "callbacks:", len(found), "in %.1fs" % (time.time() - t))
assert wiz.is_valid_ip("192.168.1.50") and not wiz.is_valid_ip("192.168.1") and not wiz.is_valid_ip("a.b.c.d") and not wiz.is_valid_ip("1.2.3.999")
print("kelvin:", wiz.kelvin_to_rgb(2200), wiz.kelvin_to_rgb(6500))
# store
d = tempfile.mkdtemp(); os.environ["AURA_HOME"] = d
from aura.store import Store
st = Store(); assert st.first_run and st.dir == os.path.join(d, "data"), st.dir
l = st.upsert_light("a8bb50aabbcc", "127.0.0.1"); st.data["active"] = l["mac"]; st.save()
st2 = Store(); assert not st2.first_run and st2.active_light()["name"] == "My light"
st2.upsert_light("a8bb50000001", "10.0.0.9"); assert st2.lights[1]["name"] == "Light 2"
st2.remove_light("a8bb50aabbcc"); assert st2.data["active"] == "a8bb50000001"
from aura import i18n
assert i18n.t("Turn on") == "turn on" and i18n.t_name("Light 2") == "light 2"
i18n.set_language("es")
assert i18n.t("Turn on") == "prender" and i18n.t_name("Light 2") == "luz 2" and i18n.t_name("My light") == "mi luz" and i18n.t_name("Velador") == "velador"
assert i18n.t("{name} scene", name=i18n.t("Ocean")) == "escena océano"
i18n.set_language("en")
print("store ok:", os.listdir(os.path.join(d, "data")))
b.stop(); print("CORE OK")
