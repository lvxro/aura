import os, sys, time, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app")); sys.path.insert(0, HERE)
from array import array
from aura import effects as fx
from fakebulb import FakeBulb

def shot(w, h, fn):
    """Fake BGRA capture: fn(x, y) -> (r, g, b)."""
    raw = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            r, g, b = fn(x, y); i = (y * w + x) * 4
            raw[i] = b; raw[i + 1] = g; raw[i + 2] = r; raw[i + 3] = 255
    return raw, w, h
W, H = 320, 180
# edges: red center, blue border -> blue
raw = shot(W, H, lambda x, y: (0, 0, 255) if (x < 60 or x >= W - 60 or y < 36 or y >= H - 36) else (255, 0, 0))
grid = fx.sample_grid(*raw); assert len(grid[0]) == grid[3] * grid[4] and grid[3] * (-(-W // 128)) > W - 4, (len(grid[0]), grid[3], grid[4])
rgb, lum = fx.analyze_screen(*grid, "edges"); print("edges", [round(v) for v in rgb], round(lum, 3)); assert rgb[2] > 240 and rgb[0] < 15
rgb, lum = fx.analyze_screen(*grid, "average"); print("average", [round(v) for v in rgb]); assert rgb[0] > 60 and rgb[2] > 60
# dominant: 70% gray, 30% green -> green
grid = fx.sample_grid(*shot(W, H, lambda x, y: (20, 220, 40) if x < 96 else (120, 120, 120)))
rgb, lum = fx.analyze_screen(*grid, "dominant"); print("dominant", [round(v) for v in rgb]); assert rgb[1] > 200 and rgb[0] < 40
grid = fx.sample_grid(*shot(W, H, lambda x, y: (128, 128, 128)))
rgb, lum = fx.analyze_screen(*grid, "dominant"); print("dominant gray", [round(v) for v in rgb]); assert abs(rgb[0] - rgb[2]) < 2
grid = fx.sample_grid(*shot(W, H, lambda x, y: (0, 0, 0)))
rgb, lum = fx.analyze_screen(*grid, "edges"); print("black", rgb, lum); assert lum == 0
# small, oddly sized screen
g2 = fx.sample_grid(*shot(50, 31, lambda x, y: (10, 200, 30))); assert len(g2[0]) == g2[3] * g2[4]; assert round(fx.analyze_screen(*g2, "average")[0][1]) == 200
print("boost", [round(x, 2) for x in fx.boost_saturation((200, 150, 150), 1.6)], [round(x, 2) for x in fx.boost_saturation((200, 198, 199), 1.6)])
# FFT against a direct DFT
f = fx._FFT(64); x = [random.uniform(-1, 1) for _ in range(64)]
ref = [abs(sum(x[n] * complex(math.cos(2 * math.pi * k * n / 64), -math.sin(2 * math.pi * k * n / 64)) for n in range(64))) for k in range(32)]
got = f.magnitudes(x); assert max(abs(a - b) for a, b in zip(ref, got)) < 1e-9; print("FFT ok")
# analyzer: bass vs mid vs treble tone, silence
def tone(freq, amp=0.5, rate=48000, n=1024):
    return array("h", [int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)])
for freq, name in ((80, "bass"), (1000, "mids"), (8000, "treble")):
    an = fx.AudioAnalyzer(48000, 0.0)
    for _ in range(5): r = an.process(tone(freq))
    top = max(("bass", "mids", "treble"), key=lambda k: r[k]); print(freq, "Hz ->", top, {k: round(r[k], 2) for k in ("bass", "mids", "treble", "level", "centroid")}); assert top == name
    assert len(r["bars"]) == 24 and max(r["bars"]) > 0.9
an = fx.AudioAnalyzer(48000, 0.0); rng = random.Random(1)
for _ in range(20): r = an.process(array("h", [int(rng.gauss(0, 3)) for _ in range(1024)]))
print("background noise ->", {k: round(r[k], 3) for k in ("bass", "mids", "treble", "level")}); assert r["level"] < 0.02 and r["bass"] < 0.2
for _ in range(20): r = an.process(array("h", bytes(2048)))
assert r["level"] == 0 and not r["beat"]
an = fx.AudioAnalyzer(48000, 0.3); buf = tone(440); t0 = time.perf_counter()
for _ in range(200): an.process(buf)
ms = (time.perf_counter() - t0) / 200 * 1000; print(f"analysis: {ms:.2f} ms per frame -> {ms * 30 / 10:.1f}% of one core at 30 frames/s")
big = bytearray(1920 * 1080 * 4); t0 = time.perf_counter()
for _ in range(20): g = fx.sample_grid(big, 1920, 1080); fx.analyze_screen(*g, "dominant"); fx.analyze_screen(*g, "edges")
print(f"1080p screen: {(time.perf_counter() - t0) / 20 * 1000:.2f} ms per frame (sampling + 2 analyses)")
assert fx._to_mono(array("h", [100, 300, -50, 50]).tobytes(), 2).tolist() == [200, 0]
# real screen capture (Xvfb) with the effect thread
if os.environ.get("DISPLAY"):
    bulb = FakeBulb(port=38899); bulb.start()
    frames = []; stops = []
    r = fx.EffectRunner("screen", {"mode": "average", "smoothing": 0.0, "boost": 1.3}, "127.0.0.1", (255, 200, 100), lambda: 100, frames.append, stops.append)
    r.start(); time.sleep(1.5); r.stop(); r.join(2)
    print("screen:", len(frames), "frames; error:", stops, "last:", frames[-1]["rgb"] if frames else None, "sent:", len([x for x in bulb.log if x[1] == "setPilot"]))
    assert stops == [""] and len(frames) > 10
print("SCREEN/AUDIO OK")
