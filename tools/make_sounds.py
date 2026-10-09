"""Builds Aura's on/off sounds from real keyboard recordings.

Sources (both MIT licensed), expected as checkouts in build/sources:
  git clone --depth 1 https://github.com/hainguyents13/mechvibes build/sources/mechvibes   (src/audio)
  git clone --depth 1 https://github.com/tplai/kbsim build/sources/kbsim                   (src/assets/audio)

"on" is one letter key, "off" is the space bar: a full keystroke, key down and back up.
The recordings are only cut, trimmed and levelled. Needs ffmpeg, numpy and, for --sheet, matplotlib.

Usage:  python tools/make_sounds.py [--sheet]      writes app/aura/sounds/*.wav
"""
import glob, json, os, subprocess, sys, wave
import numpy as np

SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "app", "aura", "sounds")
MV = os.path.join(ROOT, "build", "sources", "mechvibes", "src", "audio")
KB = os.path.join(ROOT, "build", "sources", "kbsim", "src", "assets", "audio")
os.makedirs(OUT, exist_ok=True)

def decode(path):
    """Any audio file -> float stereo array at 44.1 kHz."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ar", str(SR), "-ac", "2", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<i2").astype(np.float64).reshape(-1, 2) / 32768

def env(mono, ms=1.5):
    n = max(1, int(SR * ms / 1000))
    return np.sqrt(np.convolve(mono ** 2, np.ones(n) / n, mode="same"))

def highpass(x, hz):
    """Zero-phase, gentle: removes rumble and DC without touching the knock."""
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = 1 / np.sqrt(1 + (hz / np.maximum(f, 1e-9)) ** 4)
    return np.stack([np.fft.irfft(np.fft.rfft(x[:, c]) * g, n) for c in range(2)], 1)

def fades(x, in_ms, out_ms):
    x = x.copy()
    a = int(SR * in_ms / 1000); b = min(int(SR * out_ms / 1000), len(x) // 2)
    if a: x[:a] *= (0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a))[:, None]
    if b: x[-b:] *= (0.5 + 0.5 * np.cos(np.pi * np.arange(b) / b))[:, None]
    return x

def trim(x, lead_ms=1.5, thr=0.03):
    """Start just before the sound begins, so it answers the click without delay."""
    e = env(x.mean(1), 0.5)
    first = int(np.argmax(e > e.max() * thr))
    return x[max(0, first - int(SR * lead_ms / 1000)):]

def loud(x, target=0.085, ceiling=0.93):
    """Same perceived level for every sound: the loudest 30 ms sit at `target` RMS."""
    w = env(x.mean(1), 30).max()
    y = x * (target / max(w, 1e-9))
    peak = np.abs(y).max()
    if peak > ceiling * 2:                 # extremely spiky: do not squash it more than 6 dB
        y *= ceiling * 2 / peak
    knee = 0.55
    over = np.abs(y) > knee                # soft ceiling: only the tip of the transient is rounded
    room = ceiling - knee
    y[over] = np.sign(y[over]) * (knee + room * np.tanh((np.abs(y[over]) - knee) / room))
    return y

def finish(x, name):
    x = loud(fades(x, 0.6, 14))
    x = np.concatenate([x, np.zeros((int(SR * 0.012), 2))])      # a little silence so the tail is never cut
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return x

def describe(x):
    m = x.mean(1); e = env(m, 1.0); pk = e.max(); i = int(e.argmax())
    lead = np.argmax(e > pk * 0.1) / SR * 1000
    sp = np.abs(np.fft.rfft(m * np.hanning(len(m)))); fr = np.fft.rfftfreq(len(m), 1 / SR)
    cen = (sp * fr).sum() / sp.sum()
    later = e[i + int(SR * 0.05):]
    rel = (later.max() / pk, (later.argmax() + int(SR * 0.05)) / SR * 1000) if len(later) else (0, 0)
    return dict(ms=len(m) / SR * 1000, peak=np.abs(x).max(), lead=lead, centroid=cen, rel=rel[0], rel_ms=rel[1])

# ---------------------------------------------------------------- Mechvibes: one long recording per switch
LETTERS = list(range(16, 26)) + list(range(30, 39)) + list(range(44, 51))

def mv_slice(rec, e, floor, start, dur):
    """One whole keystroke around the slice Mechvibes defines."""
    i0 = int((start - 12) * SR / 1000); i1 = int((start + dur) * SR / 1000)
    pk = e[max(i0, 0):i1].max()
    quiet = max(floor * 2.5, pk * 0.012)
    stop = min(len(e), i1 + int(SR * 0.070))
    while i1 < stop and e[i1] > quiet:                 # let the tail ring out
        i1 += 1
    return rec[max(i0, 0):i1 + int(SR * 0.010)]

def mv_quality(seg, floor):
    m = seg.mean(1); e = env(m, 1.0); pk = e.max(); i = int(e.argmax())
    clipped = int((np.abs(seg) > 0.985).sum())
    t_pk = i / SR * 1000
    later = e[i + int(SR * 0.05):]
    rel = later.max() / pk if len(later) else 0
    head = e[:int(SR * 0.004)].mean()
    tail = e[-int(SR * 0.010):].mean()
    snr = 20 * np.log10(pk / max(floor, 1e-7))
    ok = clipped == 0 and t_pk < 75 and 0.12 < rel < 0.95 and head < pk * 0.08 and tail < pk * 0.05
    return ok, snr, dict(clipped=clipped, t_pk=round(t_pk), rel=round(rel, 2), snr=round(snr, 1))

def mechvibes(pack, out, prefer_off=(57, 28, 14)):
    cfg = json.load(open(f"{MV}/{pack}/config.json"))["defines"]
    rec = decode(glob.glob(f"{MV}/{pack}/*.ogg")[0])
    e = env(rec.mean(1)); floor = np.percentile(e, 15)
    best = None
    for code in LETTERS:
        v = cfg.get(str(code))
        if not v: continue
        seg = mv_slice(rec, e, floor, *v)
        ok, snr, info = mv_quality(seg, floor)
        if ok and (best is None or snr > best[0]):
            best = (snr, code, seg, info)
    assert best, pack
    off = None
    for code in prefer_off:
        v = cfg.get(str(code))
        if not v: continue
        seg = mv_slice(rec, e, floor, *v)
        ok, snr, info = mv_quality(seg, floor)
        if ok:
            off = (snr, code, seg, info); break
    assert off, pack + " off"
    print(f"  {pack}: on = key {best[1]} {best[3]}   off = key {off[1]} {off[3]}")
    return finish(trim(highpass(best[2], 35)), out + "_on"), finish(trim(highpass(off[2], 35)), out + "_off")

def mv_files(pack, out, on, off):
    return (finish(trim(highpass(decode(f"{MV}/{pack}/{on}.wav"), 35)), out + "_on"),
            finish(trim(highpass(decode(f"{MV}/{pack}/{off}.wav"), 35)), out + "_off"))

# ---------------------------------------------------------------- kbsim: separate key-down and key-up clips
def kb_clip(switch, part, name):
    return highpass(decode(f"{KB}/{switch}/{part}/{name}.mp3"), 70)

def kb_stroke(down, up, gap_ms, up_ratio=(0.30, 0.65)):
    """Key down, then key up `gap_ms` later, as in a real tap."""
    def tidy(x):
        """Cut the clip a little after its knock has died away, then fade: no leftover room noise."""
        x = trim(x)
        e = env(x.mean(1), 2.0)
        last = len(e) - 1 - int(np.argmax(e[::-1] > e.max() * 0.04))
        return fades(x[:last + int(SR * 0.030)], 0.5, 28)
    down = tidy(down); up = tidy(up)
    r = np.abs(up).max() / np.abs(down).max()
    up = up * (np.clip(r, *up_ratio) / r)
    start = int(SR * gap_ms / 1000)
    out = np.zeros((max(len(down), start + len(up)), 2))
    out[:len(down)] += down
    out[start:start + len(up)] += up
    return out

def kbsim(switch, out, row="GENERIC_R2", off_down="SPACE", off_up="SPACE"):
    on = kb_stroke(kb_clip(switch, "press", row), kb_clip(switch, "release", "GENERIC"), 105)
    off = kb_stroke(kb_clip(switch, "press", off_down), kb_clip(switch, "release", off_up), 118)
    return finish(on, out + "_on"), finish(off, out + "_off")

made = {}
print("Mechvibes")
made["cream"] = mv_files("nk-cream", "cream", "h", "space")
for pack, out in [("eg-oreo", "oreo"), ("eg-crystal-purple", "crystal"), ("topre-purple-hybrid-pbt", "topre"),
                  ("cherrymx-black-pbt", "mxblack"), ("cherrymx-red-pbt", "mxred"),
                  ("cherrymx-brown-pbt", "mxbrown"), ("cherrymx-blue-pbt", "mxblue")]:
    made[out] = mechvibes(pack, out)
print("kbsim")
for switch, out in [("holypanda", "holypanda"), ("blackink", "blackink"), ("buckling", "buckling"),
                    ("bluealps", "alps"), ("boxnavy", "boxnavy")]:
    made[out] = kbsim(switch, out)

print(f"\n{'sound':16} {'ms':>4} {'peak':>5} {'lead':>5} {'centroid':>8} {'release':>12}")
for k, pair in made.items():
    for kind, x in zip(("on", "off"), pair):
        d = describe(x)
        print(f"{k + '_' + kind:16} {d['ms']:4.0f} {d['peak']:5.2f} {d['lead']:5.1f} {d['centroid']:8.0f}   {d['rel']:.2f} @ {d['rel_ms']:3.0f} ms")

if "--sheet" in sys.argv:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = list(made)
    fig, ax = plt.subplots(len(keys), 4, figsize=(15, 1.55 * len(keys)), squeeze=False)
    for i, k in enumerate(keys):
        for j, x in enumerate(made[k]):
            m = x.mean(1)
            ax[i][j * 2].plot(np.arange(len(m)) / SR * 1000, m, lw=0.5, color="k")
            ax[i][j * 2].set_xlim(0, 340); ax[i][j * 2].set_ylim(-1, 1)
            ax[i][j * 2].set_title(f"{k} {'on' if j == 0 else 'off'}", fontsize=8)
            ax[i][j * 2 + 1].specgram(m, NFFT=256, Fs=SR, noverlap=224, cmap="magma", vmin=-110, vmax=-40)
            ax[i][j * 2 + 1].set_ylim(0, 12000); ax[i][j * 2 + 1].set_xlim(0, 0.34)
            for a in (ax[i][j * 2], ax[i][j * 2 + 1]): a.tick_params(labelsize=5)
    plt.tight_layout(); plt.savefig(os.path.join(ROOT, "build", "sounds-sheet.png"), dpi=68)
