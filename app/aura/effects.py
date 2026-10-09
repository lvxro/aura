"""Live effects: the light reacts to music or mirrors the colors on the screen.

The ideas (frequency bands to RGB, pulse, strobe, DIY Ambilight) come from
wiz-hack by Shravan Revanna (MIT). They are rewritten here to run inside the
app: audio is taken straight from what the PC is playing (WASAPI loopback), no
microphone needed, and the screen is captured live instead of reading a video file.

Everything here is plain Python (no NumPy): the signal work is small enough
that a 512-point FFT a few dozen times a second costs very little.
"""

from __future__ import annotations

import cmath
import colorsys
import math
import os
import random
import sys
import threading
import time
from array import array

from . import wiz
from .i18n import t

MUSIC_MODES = [
    ("spectrum", "Spectrum", "Red on the bass, blue on the treble"),
    ("pulse", "Pulse", "Your color beats with the volume"),
    ("rainbow", "Rainbow", "Hue follows the dominant note"),
    ("energy", "Energy", "Cool when calm, warm when loud"),
    ("spectrum_pulse", "Color + pulse", "Color by band, punchy brightness"),
    ("strobe", "Strobe", "Bright flashes on every beat"),
]
SCREEN_MODES = [
    ("edges", "Edges", "Uses the colors at the screen edges, like Ambilight"),
    ("dominant", "Dominant", "The color that stands out most on screen"),
    ("average", "Average", "A blend of the whole screen, softer"),
]
BARS = 24


class EffectError(Exception):
    """An error whose message is ready to show to the person."""


# --------------------------------------------------------------------------
# Audio capture
# --------------------------------------------------------------------------
class _Ring:
    """The most recent mono samples (16-bit), shared between two threads."""

    KEEP = 8192

    def __init__(self):
        self.buf = array("h")
        self.lock = threading.Lock()
        self.last_write = 0.0

    def write(self, samples: array):
        with self.lock:
            self.buf.extend(samples)
            extra = len(self.buf) - self.KEEP
            if extra > self.KEEP:              # trim in big steps, not on every write
                del self.buf[:extra]
            self.last_write = time.monotonic()

    def latest(self, n: int) -> array:
        with self.lock:
            # With loopback, no data arrives while nothing is playing: that is silence.
            if time.monotonic() - self.last_write > 0.25 or len(self.buf) < n:
                return array("h", bytes(2 * n))
            return self.buf[-n:]


def _to_mono(data: bytes, channels: int) -> array:
    a = array("h")
    a.frombytes(data[:len(data) - len(data) % (2 * max(1, channels))])
    if channels <= 1:
        return a
    return array("h", [(left + right) >> 1 for left, right in zip(a[0::channels], a[1::channels])])


# PortAudio cannot be initialized or terminated from two threads at once.
_PA_LOCK = threading.Lock()


class WasapiCapture:
    """Windows audio through PyAudioWPatch: what the PC is playing, or the microphone."""

    def __init__(self, source: str = "pc"):
        self.source = source
        self.rate = 48000
        self.ring = _Ring()
        self._pa = None
        self._stream = None
        self._channels = 2

    def _pick_device(self, pa, pyaudio):
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            raise EffectError(t("Windows reports no audio devices."))
        if self.source == "mic":
            idx = wasapi.get("defaultInputDevice", -1)
            if idx is None or idx < 0:
                raise EffectError(t("No microphone is connected."))
            return pa.get_device_info_by_index(idx)
        idx = wasapi.get("defaultOutputDevice", -1)
        if idx is None or idx < 0:
            raise EffectError(t("This PC has no active audio output."))
        speakers = pa.get_device_info_by_index(idx)
        if speakers.get("isLoopbackDevice"):
            return speakers
        for loop in pa.get_loopback_device_info_generator():
            if speakers["name"] in loop["name"]:
                return loop
        raise EffectError(t("Couldn't listen to this PC's audio output."))

    def start(self):
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            raise EffectError(t("The audio component (PyAudioWPatch) is missing."))
        _PA_LOCK.acquire()
        try:
            self._pa = pyaudio.PyAudio()
        except Exception as e:
            _PA_LOCK.release()
            raise EffectError(t("Couldn't start the audio: {e}", e=e))
        try:
            dev = self._pick_device(self._pa, pyaudio)
            self._channels = max(1, int(dev.get("maxInputChannels") or 2))
            self.rate = int(dev.get("defaultSampleRate") or 48000)
            channels = self._channels
            ring = self.ring

            def callback(in_data, frame_count, time_info, status):
                ring.write(_to_mono(in_data, channels))
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=channels, rate=self.rate,
                frames_per_buffer=512, input=True, input_device_index=dev["index"],
                stream_callback=callback)
        except EffectError:
            self._close()
            raise
        except Exception as e:  # PortAudio raises OSError with unhelpful codes
            self._close()
            raise EffectError(t("Couldn't open the audio: {e}", e=e))
        finally:
            _PA_LOCK.release()

    def read(self, n: int) -> array:
        return self.ring.latest(n)

    def stop(self):
        with _PA_LOCK:
            self._close()

    def _close(self):
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = None
        self._pa = None


class SoundDeviceCapture:
    """Fallback for Linux/macOS: microphone (or monitor) through sounddevice."""

    def __init__(self, source: str = "pc"):
        self.rate = 44100
        self.ring = _Ring()
        self._stream = None

    def start(self):
        try:
            import sounddevice as sd
        except Exception:
            raise EffectError(t("The music effect needs Windows (or the sounddevice package)."))
        ring = self.ring

        def callback(indata, frames, time_info, status):
            ring.write(_to_mono(bytes(indata), 1))

        try:
            self._stream = sd.RawInputStream(samplerate=self.rate, channels=1, blocksize=512,
                                             dtype="int16", callback=callback)
            self._stream.start()
        except Exception as e:
            raise EffectError(t("Couldn't open the audio: {e}", e=e))

    def read(self, n):
        return self.ring.latest(n)

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None


class SyntheticCapture:
    """Fake music (kick + bass + hi-hats) for testing without real audio."""

    def __init__(self, source: str = "pc"):
        self.rate = 44100
        self.t0 = time.monotonic()
        self.rng = random.Random(7)

    def start(self):
        pass

    def read(self, n: int) -> array:
        now = time.monotonic() - self.t0
        rate = self.rate
        sin, exp, tau = math.sin, math.exp, 2 * math.pi
        gauss = self.rng.gauss
        out = array("h", bytes(2 * n))
        for i in range(n):
            ts = now - (n - 1 - i) / rate
            beat = ts % 0.5
            kick = sin(tau * 55 * beat * exp(-beat * 3)) * exp(-beat * 9)
            note = 110 * (2 ** (int(ts % 4.0) * 3 / 12))
            bass = 0.25 * sin(tau * note * ts)
            lead = 0.2 * sin(tau * (440 + 220 * sin(ts * 0.7)) * ts) * (0.5 + 0.5 * sin(ts * 2.1))
            hat = 0.18 * gauss(0, 1) * exp(-((ts + 0.25) % 0.5) * 30)
            v = (0.8 * kick + bass + lead + hat) * 0.6
            out[i] = int(max(-1.0, min(1.0, v)) * 32767)
        return out

    def stop(self):
        pass


def make_capture(source: str):
    if os.environ.get("AURA_FAKE_AUDIO"):
        return SyntheticCapture(source)
    if sys.platform == "win32":
        return WasapiCapture(source)
    return SoundDeviceCapture(source)


# --------------------------------------------------------------------------
# Audio analysis
# --------------------------------------------------------------------------
class _FFT:
    """Small radix-2 FFT with precomputed tables. Returns magnitudes of the lower half."""

    def __init__(self, n: int):
        bits = n.bit_length() - 1
        assert 1 << bits == n
        self.n = n
        self.rev = [int(format(i, f"0{bits}b")[::-1], 2) for i in range(n)]
        self.tw = [cmath.exp(-2j * cmath.pi * k / n) for k in range(n // 2)]

    def magnitudes(self, x: list[float]) -> list[float]:
        n = self.n
        tw = self.tw
        a = [x[i] for i in self.rev]
        for j in range(0, n, 2):                  # first stage: the twiddle is 1
            u, v = a[j], a[j + 1]
            a[j], a[j + 1] = u + v, u - v
        size = 4
        while size <= n:
            half = size >> 1
            step = n // size
            for start in range(0, n, size):
                k = 0
                for j in range(start, start + half):
                    v = tw[k] * a[j + half]
                    u = a[j]
                    a[j] = u + v
                    a[j + half] = u - v
                    k += step
            size <<= 1
        return [abs(a[i]) for i in range(n >> 1)]


class AudioAnalyzer:
    """Split the audio into bass, mids and treble with an FFT, with automatic gain.

    The input is averaged in pairs first (half the sample rate), which keeps the
    FFT small while still covering everything up to about 12 kHz.
    """

    RAW = 1024          # raw samples taken from the capture each frame
    N = 512             # FFT size after halving the sample rate

    def __init__(self, rate: int, smoothing: float = 0.3):
        self.rate = rate / 2.0
        n = self.N
        self.fft = _FFT(n)
        self.window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
        bin_hz = self.rate / n
        self.freqs = [i * bin_hz for i in range(n // 2)]
        top = n // 2

        def span(lo, hi):
            a = max(1, int(math.ceil(lo / bin_hz)))
            b = min(top, max(a + 1, int(math.ceil(hi / bin_hz))))
            return a, b

        self.bands = [span(30, 250), span(250, 4000), span(4000, 12000)]
        hi = min(12000.0, self.rate / 2 - 1)
        edges = [40.0 * (hi / 40.0) ** (i / BARS) for i in range(BARS + 1)]
        self.bar_spans = [span(lo, hi_) for lo, hi_ in zip(edges[:-1], edges[1:])]
        self.bar_gain = [1.0 + 5.0 * i / (BARS - 1) for i in range(BARS)]   # treble carries less energy
        self.set_smoothing(smoothing)
        self.max = [1e-3, 1e-3, 1e-3]
        self.max_rms = 0.02
        self.max_bar = 1e-3
        self.sm = [0.0, 0.0, 0.0]
        self.level = 0.0
        self.bars = [0.0] * BARS
        self.centroid = 0.5
        self.hist: list[float] = []
        self.last_beat = 0.0

    def set_smoothing(self, smoothing: float):
        # 0 = dry and immediate, 1 = very smooth
        self.alpha = 1.0 - 0.88 * wiz.clamp(smoothing, 0.0, 1.0)

    def process(self, raw) -> dict:
        n = self.N
        k = 1.0 / 65536.0                       # average of two 16-bit samples, scaled to -1..1
        x = [(raw[i] + raw[i + 1]) * k for i in range(0, 2 * n, 2)]
        rms = math.sqrt(sum(v * v for v in x) / n)
        w = self.window
        scale = 4.0 / n
        mag = [m * scale for m in self.fft.magnitudes([x[i] * w[i] for i in range(n)])]

        raw_bands = [sum(mag[a:b]) / (b - a) for a, b in self.bands]

        # Automatic gain: the recent maximum decays slowly, with a floor so that
        # silence is not amplified until it looks like music.
        floor = (2e-3, 6e-4, 1.5e-4)
        a = self.alpha
        for i in range(3):
            self.max[i] = max(raw_bands[i], self.max[i] * 0.997, floor[i])
            band = min(1.0, raw_bands[i] / self.max[i])
            self.sm[i] = a * band + (1 - a) * self.sm[i]
        self.max_rms = max(rms, self.max_rms * 0.9985, 0.02)
        level = min(1.0, rms / self.max_rms)
        self.level = a * level + (1 - a) * self.level

        # Beat: the bass clearly exceeds its recent average.
        now = time.monotonic()
        energy = raw_bands[0]
        avg = (sum(self.hist) / len(self.hist)) if self.hist else 0.0
        self.hist.append(energy)
        if len(self.hist) > 30:
            self.hist.pop(0)
        beat = False
        if energy > 2e-3 and energy > 1.45 * avg and now - self.last_beat > 0.16:
            beat = True
            self.last_beat = now

        # Spectral centroid (how "bright" the mix sounds), on a log scale.
        total = sum(mag[2:])
        if total > 1e-4 and rms > 1e-3:
            freqs = self.freqs
            c = sum(mag[i] * freqs[i] for i in range(2, n // 2)) / total
            lo, hi = math.log10(60.0), math.log10(8000.0)
            c = (math.log10(max(60.0, min(c, 8000.0))) - lo) / (hi - lo)
            self.centroid = 0.12 * c + 0.88 * self.centroid

        gains = self.bar_gain
        bars = [sum(mag[a_:b_]) / (b_ - a_) * gains[i] for i, (a_, b_) in enumerate(self.bar_spans)]
        self.max_bar = max(max(bars), self.max_bar * 0.995, 1e-3)
        old = self.bars
        new = []
        for i in range(BARS):
            v = min(1.0, bars[i] / self.max_bar) ** 0.7
            new.append(v if v > old[i] else old[i] * 0.82 + v * 0.18)
        self.bars = new

        return {
            "bass": self.sm[0], "mids": self.sm[1], "treble": self.sm[2],
            "level": self.level, "beat": beat, "centroid": self.centroid, "bars": list(new),
        }


def _vivid(r: float, g: float, b: float) -> tuple[int, int, int]:
    """Push the color to its most intense version; brightness is handled separately."""
    m = max(r, g, b)
    if m <= 1e-6:
        return (255, 255, 255)
    return (int(255 * r / m), int(255 * g / m), int(255 * b / m))


class MusicMapper:
    """Turn the audio analysis into color + brightness, depending on the mode."""

    def __init__(self, mode: str, sensitivity: float, base_rgb: tuple[int, int, int]):
        self.mode = mode
        self.sens = wiz.clamp(sensitivity, 0.3, 3.0)
        self.base = tuple(base_rgb)
        self.flash = 0.0
        self.hue = 0.0
        self.rgb = [float(c) for c in base_rgb]

    def _dim(self, energy: float, power: float = 1.0, lo: int = 10) -> int:
        e = wiz.clamp(energy, 0.0, 1.0) ** (power / self.sens)
        return int(lo + e * (100 - lo))

    def map(self, a: dict) -> tuple[int, int, int, int]:
        bass, mids, treb, level = a["bass"], a["mids"], a["treble"], a["level"]
        mode = self.mode
        if mode == "pulse":
            r, g, b = self.base
            return r, g, b, self._dim(level, 1.5)

        if mode == "strobe":
            if a["beat"]:
                self.flash = 1.0
            else:
                self.flash *= 0.45
            r, g, b = self.base
            dim = 100 if self.flash > 0.5 else int(10 + min(1.0, level * 0.4) * 25 * self.flash)
            return r, g, b, max(10, dim)

        if mode == "energy":
            e = wiz.clamp(((bass + mids + treb) / 3) ** (1.0 / self.sens), 0, 1)
            # from blue (calm) to violet, red and orange (loud)
            hue = (0.66 + e * 0.42) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            return int(r * 255), int(g * 255), int(b * 255), self._dim(e, 1.0)

        if mode == "rainbow":
            target = (a["centroid"] * 0.83) % 1.0
            d = ((target - self.hue + 0.5) % 1.0) - 0.5
            self.hue = (self.hue + d * 0.25) % 1.0
            r, g, b = colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)
            return int(r * 255), int(g * 255), int(b * 255), self._dim(level, 1.2)

        if mode == "spectrum_pulse":
            bands = {"bass": bass, "mids": mids, "treble": treb}
            dom = max(bands, key=bands.get)
            target = {"bass": (255, 40, 170), "mids": (255, 170, 30), "treble": (40, 150, 255)}[dom]
            self.rgb = [c + (tc - c) * 0.35 for c, tc in zip(self.rgb, target)]
            r, g, b = (int(c) for c in self.rgb)
            return r, g, b, self._dim(level, 0.5, lo=10)

        # "spectrum": bass -> red, mids -> green, treble -> blue
        r, g, b = _vivid(bass ** 1.5, mids ** 1.5, treb ** 1.5)
        return r, g, b, self._dim(level, 0.9)


# --------------------------------------------------------------------------
# Screen analysis
# --------------------------------------------------------------------------
GRID_W, GRID_H = 128, 72


def sample_grid(raw, width: int, height: int, cols: int = GRID_W, rows: int = GRID_H):
    """Pick a cols x rows grid of pixels out of a BGRA screenshot.

    Returns (r, g, b, cols, rows) with one byte per sampled pixel in each channel;
    cols and rows are the actual grid size, at most the requested one.
    Uses stepped slices, so the per-pixel work happens in C.
    """
    # Whole-pixel steps that span the full image (the grid may end up a bit smaller).
    sx = max(1, -(-width // max(1, cols)))
    sy = max(1, -(-height // max(1, rows)))
    cols = max(1, width // sx)
    rows = max(1, height // sy)
    mv = memoryview(raw)
    step = 4 * sx
    stride = 4 * width
    r, g, b = bytearray(), bytearray(), bytearray()
    for j in range(rows):
        base = (j * sy + sy // 2) * stride + (sx // 2) * 4
        end = base + cols * step
        b += mv[base:end:step].tobytes()
        g += mv[base + 1:end:step].tobytes()
        r += mv[base + 2:end:step].tobytes()
    return bytes(r), bytes(g), bytes(b), cols, rows


def analyze_screen(r: bytes, g: bytes, b: bytes, cols: int, rows: int, mode: str):
    """Returns ((r, g, b) 0..255 floats, luminance 0..1) for a sampled grid."""
    n = cols * rows

    def lum_of(rgb):
        return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0

    avg = (sum(r) / n, sum(g) / n, sum(b) / n)
    if mode == "edges":
        eh, ew = max(1, int(rows * 0.16)), max(1, int(cols * 0.16))
        totals = [0, 0, 0]
        count = 0
        for ch, data in enumerate((r, g, b)):
            s = sum(data[:eh * cols]) + sum(data[(rows - eh) * cols:])
            for j in range(eh, rows - eh):
                row = j * cols
                s += sum(data[row:row + ew]) + sum(data[row + cols - ew:row + cols])
            totals[ch] = s
        count = 2 * eh * cols + max(0, rows - 2 * eh) * 2 * ew
        rgb = tuple(v / count for v in totals)
        return rgb, lum_of(rgb)
    if mode == "dominant":
        hist = [0.0] * 24
        acc = [[0.0, 0.0, 0.0, 0.0] for _ in range(24)]
        total_w = 0.0
        seen = 0
        for j in range(0, rows, 2):
            row = j * cols
            for i in range(row, row + cols, 2):
                pr, pg, pb = r[i], g[i], b[i]
                mx = pr if pr > pg else pg
                if pb > mx:
                    mx = pb
                mn = pr if pr < pg else pg
                if pb < mn:
                    mn = pb
                delta = mx - mn
                seen += 1
                if delta < 12:
                    continue
                weight = delta * mx                 # saturation x brightness
                if mx == pr:
                    h = ((pg - pb) / delta) % 6.0
                elif mx == pg:
                    h = (pb - pr) / delta + 2.0
                else:
                    h = (pr - pg) / delta + 4.0
                k = int(h * 4) % 24
                hist[k] += weight
                bucket = acc[k]
                bucket[0] += pr * weight
                bucket[1] += pg * weight
                bucket[2] += pb * weight
                bucket[3] += weight
                total_w += weight
        if total_w < 0.004 * 65025 * max(1, seen):      # nearly gray image
            return avg, lum_of(avg)
        smooth = [hist[k] + 0.5 * (hist[k - 1] + hist[(k + 1) % 24]) for k in range(24)]
        top = max(range(24), key=smooth.__getitem__)
        tot = [0.0, 0.0, 0.0, 0.0]
        for k in (top - 1, top, (top + 1) % 24):
            for c in range(4):
                tot[c] += acc[k][c]
        rgb = (tot[0] / tot[3], tot[1] / tot[3], tot[2] / tot[3]) if tot[3] > 0 else avg
        return rgb, lum_of(avg)
    return avg, lum_of(avg)


def boost_saturation(rgb, boost: float) -> tuple[float, float, float]:
    r, g, b = (wiz.clamp(float(x) / 255.0, 0.0, 1.0) for x in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.08:                      # nearly white/gray: don't invent a color
        return r, g, b
    s = min(1.0, s * boost)
    return colorsys.hsv_to_rgb(h, s, v)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class EffectRunner(threading.Thread):
    """Thread that runs an effect and sends the colors to the light.

    on_frame(dict) and on_stop(str) are called from this thread: whoever receives
    them has to hand them over to the interface thread (Qt signals are used here).
    """

    def __init__(self, kind: str, options: dict, ip: str, base_rgb, master, on_frame, on_stop,
                 after: threading.Thread | None = None):
        super().__init__(daemon=True, name="aura-effect")
        self.kind = kind
        self.options = dict(options)     # sensitivity, smoothing and intensity are read live
        self.after = after               # previous effect: wait until it releases the audio
        self.ip = ip
        self.base_rgb = tuple(base_rgb)
        self.master = master              # function: overall brightness 10..100
        self.on_frame = on_frame
        self.on_stop = on_stop
        self._halt = threading.Event()
        self.sender = wiz.Sender()
        self._last_sent = None
        self._last_time = 0.0
        self.sent = 0

    def stop(self):
        self._halt.set()

    # Only send when there is a visible change, and never more than ~16 times a second:
    # beyond that the bulb gets flooded and the changes arrive in bursts.
    def _send(self, r: int, g: int, b: int, dim: int, min_gap: float, min_change: int = 10):
        now = time.monotonic()
        if self._halt.is_set() or now - self._last_time < min_gap:
            return
        dim = int(wiz.clamp(round(dim * self.master() / 100.0), wiz.MIN_DIM, 100))
        cur = (r, g, b, dim)
        last = self._last_sent
        if last is not None and now - self._last_time < 1.0:
            if (abs(cur[0] - last[0]) + abs(cur[1] - last[1]) + abs(cur[2] - last[2]) < min_change
                    and abs(cur[3] - last[3]) < 3):
                return
        if r == 0 and g == 0 and b == 0:
            r = 1
        self.sender.send(self.ip, "setPilot", {"state": True, "r": r, "g": g, "b": b, "dimming": dim})
        self._last_sent = cur
        self._last_time = now
        self.sent += 1
        if self.sent % 40 == 0:
            self.sender.drain()

    def run(self):
        error = ""
        if self.after is not None:
            self.after.join(timeout=3.0)
            self.after = None
        try:
            if self._halt.is_set():
                return
            if self.kind == "music":
                self._run_music()
            elif self.kind == "anim":
                self._run_anim()
            else:
                self._run_screen()
        except EffectError as e:
            error = str(e)
        except Exception as e:  # never let the thread die silently
            error = t("The effect stopped because of an error: {e}", e=e)
        finally:
            self.sender.close()
            self.on_stop(error)

    def _run_anim(self):
        """A scene made by the person: the light glides from one color to the next, forever."""
        opt = self.options
        t0 = time.monotonic()
        period = 0.1
        nxt = t0
        while not self._halt.is_set():
            colors = [tuple(c) for c in opt.get("colors") or [self.base_rgb]]
            seconds = wiz.clamp(float(opt.get("seconds", 4.0)), 0.5, 60.0)
            pos = (time.monotonic() - t0) / seconds
            i = int(pos) % len(colors)
            f = pos - int(pos)
            f = f * f * (3.0 - 2.0 * f)                 # ease in and out of each color
            a, b = colors[i], colors[(i + 1) % len(colors)]
            r, g, bl = (int(round(a[k] + (b[k] - a[k]) * f)) for k in range(3))
            self._send(r, g, bl, 100, 0.09, min_change=3)      # small steps keep the glide smooth
            self.on_frame({"rgb": (r, g, bl), "dim": 100, "bars": None, "level": 1.0, "beat": False})
            nxt += period
            delay = nxt - time.monotonic()
            if delay > 0:
                self._halt.wait(delay)
            else:
                nxt = time.monotonic()

    def _run_music(self):
        opt = self.options
        cap = make_capture(opt.get("source", "pc"))
        cap.start()
        try:
            analyzer = AudioAnalyzer(cap.rate, opt.get("smoothing", 0.3))
            mapper = MusicMapper(opt.get("mode", "spectrum"), opt.get("sensitivity", 1.0), self.base_rgb)
            period = 1.0 / 30.0
            nxt = time.monotonic()
            while not self._halt.is_set():
                analyzer.set_smoothing(opt.get("smoothing", 0.3))
                mapper.sens = wiz.clamp(opt.get("sensitivity", 1.0), 0.3, 3.0)
                a = analyzer.process(cap.read(AudioAnalyzer.RAW))
                r, g, b, dim = mapper.map(a)
                self._send(r, g, b, dim, 0.06)
                self.on_frame({"rgb": (r, g, b), "dim": dim, "bars": a["bars"],
                               "level": a["level"], "beat": a["beat"]})
                nxt += period
                delay = nxt - time.monotonic()
                if delay > 0:
                    self._halt.wait(delay)
                else:
                    nxt = time.monotonic()
        finally:
            cap.stop()

    def _run_screen(self):
        opt = self.options
        try:
            import mss
        except ImportError:
            raise EffectError(t("The screen capture component (mss) is missing."))
        mode = opt.get("mode", "edges")
        use_audio = bool(opt.get("audio_brightness"))
        cap = analyzer = None
        if use_audio:
            try:
                cap = make_capture("pc")
                cap.start()
                analyzer = AudioAnalyzer(cap.rate, 0.3)
            except EffectError:
                cap = analyzer = None
        cur = [c / 255.0 for c in self.base_rgb]
        cur_dim = 60.0
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                idx = int(opt.get("monitor", 1))
                mon = mons[idx] if 0 < idx < len(mons) else mons[min(1, len(mons) - 1)]
                period = 1.0 / 15.0
                nxt = time.monotonic()
                while not self._halt.is_set():
                    alpha = 1.0 - 0.9 * wiz.clamp(opt.get("smoothing", 0.6), 0.0, 0.95)
                    boost = opt.get("boost", 1.3)
                    shot = sct.grab(mon)
                    grid = sample_grid(shot.raw, shot.width, shot.height)
                    rgb, lum = analyze_screen(*grid, mode)
                    target = boost_saturation(rgb, boost)
                    if lum > 0.015:                       # on black, keep the last color
                        cur = [c + (tc - c) * alpha for c, tc in zip(cur, target)]
                    if analyzer is not None:
                        a = analyzer.process(cap.read(AudioAnalyzer.RAW))
                        dim_t = 10 + (a["level"] ** 0.8) * 90
                        cur_dim += (dim_t - cur_dim) * 0.6
                    else:
                        dim_t = 10 + (min(1.0, lum * 1.6) ** 0.6) * 90
                        cur_dim += (dim_t - cur_dim) * alpha
                    r, g, b = _vivid(*cur) if max(cur) > 0.02 else (255, 255, 255)
                    self._send(r, g, b, int(cur_dim), 0.08)
                    self.on_frame({"rgb": (r, g, b), "dim": int(cur_dim), "bars": None,
                                   "level": lum, "beat": False})
                    nxt += period
                    delay = nxt - time.monotonic()
                    if delay > 0:
                        self._halt.wait(delay)
                    else:
                        nxt = time.monotonic()
        except EffectError:
            raise
        except Exception as e:
            raise EffectError(t("Couldn't capture the screen: {e}", e=e))
        finally:
            if cap is not None:
                cap.stop()
