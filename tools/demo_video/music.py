"""Synthesised soundtrack: ambient pad, a pulse that starts with the flight to Earth, a riser into the 2090 reveal,
soft ticks on every click and a whoosh for the flight. Writes /tmp/rec/music.wav (48 kHz stereo)."""
import json, wave
import numpy as np

SR, FPS = 48000, 30
lay = json.load(open('/tmp/rec/layout.json')); ev = json.load(open('/tmp/rec/events.json'))
T = lay['total'] / FPS; N = int(T * SR); t = np.arange(N) / SR
off = lay['intro']
sec = lambda f: (off + f) / FPS
rng = np.random.default_rng(3)
L = np.zeros(N); R = np.zeros(N)

def env(start, dur, a=.02, r=.3):
    e = np.zeros(N); i0, i1 = int(start * SR), min(N, int((start + dur) * SR))
    if i1 <= i0: return e
    x = np.arange(i1 - i0) / SR
    e[i0:i1] = np.minimum(1, x / max(a, 1e-4)) * np.clip((dur - x) / max(r, 1e-4), 0, 1)
    return e

def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s = (1 - a) * x[i] + a * s; y[i] = s
    return y

note = lambda n: 440 * 2 ** ((n - 69) / 12)

# --- pad: A minor progression, warm saw-like stacks, slow swells
chords = [[45, 57, 60, 64, 71], [41, 53, 57, 60, 67], [48, 55, 60, 64, 67], [43, 55, 59, 62, 69]]
seg = T / 4
for k, ch in enumerate(chords):
    e = env(k * seg - .6 if k else 0, seg + 1.2, a=1.6, r=1.6)
    for j, n in enumerate(ch):
        f = note(n)
        for det, pan in ((-.0035, .25), (.0035, .75)):
            w = sum(np.sin(2 * np.pi * f * (1 + det) * h * t + j) / h ** 1.6 for h in range(1, 6))
            amp = (.055 if j else .08) * e
            L += w * amp * (1 - pan); R += w * amp * pan

# --- pulse: soft kick + shaker from the flight to the end, denser after the reveal
bpm = 96; beat = 60 / bpm
t_flight, t_reveal = sec(ev['marks']['flight']), sec(ev['marks']['reveal'])
b = t_flight
while b < T - 1.6:
    i0 = int(b * SR); n = int(.35 * SR); x = np.arange(min(n, N - i0)) / SR
    kick = np.sin(2 * np.pi * (48 + 70 * np.exp(-x * 30)) * x) * np.exp(-x * 9) * (.33 if b > t_reveal else .22)
    L[i0:i0 + len(x)] += kick; R[i0:i0 + len(x)] += kick
    h0 = int((b + beat / 2) * SR); m = int(.06 * SR)
    if h0 + m < N:
        sh = rng.standard_normal(m) * np.exp(-np.arange(m) / SR * 60) * (.05 if b > t_reveal else .03)
        sh = sh - lowpass(sh, 5000)
        L[h0:h0 + m] += sh * .8; R[h0:h0 + m] += sh * 1.2
    b += beat

# --- riser into the reveal, then an impact
r0 = t_reveal - 2.4; i0, i1 = int(r0 * SR), int(t_reveal * SR)
x = np.linspace(0, 1, i1 - i0)
noise = rng.standard_normal(i1 - i0)
rise = (noise - lowpass(noise, 300 + 6000 * x[0])) * x ** 2 * .12
tone = np.sin(2 * np.pi * (220 + 660 * x ** 2) * np.arange(i1 - i0) / SR) * x ** 3 * .05
L[i0:i1] += rise + tone; R[i0:i1] += rise + tone
n = int(2.4 * SR); x = np.arange(min(n, N - i1)) / SR
boom = np.sin(2 * np.pi * (36 + 50 * np.exp(-x * 6)) * x) * np.exp(-x * 2.2) * .55
tail = rng.standard_normal(len(x)); tail = lowpass(tail, 2500) * np.exp(-x * 1.6) * .06
L[i1:i1 + len(x)] += boom + tail; R[i1:i1 + len(x)] += boom + tail * .9

# --- whoosh for the flight to Earth
i0 = int((t_flight - .2) * SR); n = int(1.4 * SR); x = np.linspace(0, 1, n)
w = rng.standard_normal(n); w = lowpass(w, 1800) * np.sin(np.pi * x) ** 2 * .22
L[i0:i0 + n] += w * (1 - x); R[i0:i0 + n] += w * x

# --- ticks on clicks
for c in ev['clicks']:
    i0 = int(sec(c['frame']) * SR); m = int(.03 * SR)
    if i0 + m >= N: continue
    xs = np.arange(m) / SR
    tick = (np.sin(2 * np.pi * 2600 * xs) * .5 + rng.standard_normal(m) * .3) * np.exp(-xs * 260) * .16
    L[i0:i0 + m] += tick; R[i0:i0 + m] += tick

# --- master: gentle fade in/out, soft limiter
fade = np.clip(t / 1.2, 0, 1) * np.clip((T - t) / 1.8, 0, 1)
mix = np.stack([L, R], 1) * fade[:, None]
mix = np.tanh(mix * 1.4) / np.tanh(1.4)
mix *= .89 / np.max(np.abs(mix))
pcm = (mix * 32767).astype('<i2')
with wave.open('/tmp/rec/music.wav', 'wb') as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm.tobytes())
print('audio seconds', round(T, 2))
