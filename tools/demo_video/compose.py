"""Compose the Planalogy demo: title card, recorded app with camera moves and step captions, end card.
Frames are piped into one ffmpeg encode; audio is muxed afterwards."""
import json, math, random, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
F = '/usr/share/fonts/opentype/inter/'
font = lambda name, size: ImageFont.truetype(F + name, size)
ev = json.load(open('/tmp/rec/events.json'))
N_APP = ev['marks']['end']
INTRO, XF_IN, OUTRO, XF_OUT = 50, 12, 70, 16
ACCENT = (79, 123, 255)
MARS = (224, 138, 82)
ease = lambda t: t * t * (3 - 2 * t)
TEST = sys.argv[1:]  # frame numbers to dump as stills instead of encoding


# ---------------- camera: each move eases from the current state to its target
def camera_track():
    cam = [(1.0, W / 2, H / 2)] * N_APP
    cur = (1.0, W / 2, H / 2)
    moves = sorted(ev['camera'], key=lambda c: c['frame'])
    for i, m in enumerate(moves):
        start, n = m['frame'], max(1, m['frames'])
        end_hold = moves[i + 1]['frame'] if i + 1 < len(moves) else N_APP
        tgt = (m['zoom'], m['cx'], m['cy'])
        for f in range(start, min(end_hold, N_APP)):
            t = ease(min(1, (f - start) / n))
            cam[f] = tuple(a + (b - a) * t for a, b in zip(cur, tgt))
        if end_hold > start: cur = cam[min(end_hold, N_APP) - 1]
    return cam


def crop(img, z, cx, cy):
    if z <= 1.0005: return img
    w, h = W / z, H / z
    x0 = min(max(cx - w / 2, 0), W - w); y0 = min(max(cy - h / 2, 0), H - h)
    return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


# ---------------- captions: lower left of the globe area
F_NUM, F_TXT = font('InterDisplay-SemiBold.otf', 22), font('InterDisplay-Medium.otf', 40)
def caption_layer(num, text, k, slide):
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = 520, 862 + slide
    tw = d.textlength(text, font=F_TXT)
    lab = f'{num:02d}' if num else None
    pad_l = 66 if lab else 26
    box = (x - 22, y - 18, x + pad_l + tw + 28, y + 62)
    shade = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rounded_rectangle(box, 10, fill=(0, 0, 0, int(150 * k)))
    shade = shade.filter(ImageFilter.GaussianBlur(14))
    layer = Image.alpha_composite(layer, shade); d = ImageDraw.Draw(layer)
    d.rectangle((x - 22, y - 6, x - 19, y + 50), fill=ACCENT + (int(255 * k),))
    if lab: d.text((x, y + 14), lab, font=F_NUM, fill=(169, 188, 255, int(255 * k)))
    d.text((x + pad_l - 26 + (0 if lab else 0), y + 2), text, font=F_TXT, fill=(255, 255, 255, int(255 * k)))
    return layer


def captions_at(f):
    out = []
    for c in ev['captions']:
        a, n = c['frame'], c['frames']
        if a <= f < a + n:
            t = f - a
            k = min(1, t / 8, (n - t) / 8)
            slide = round((1 - ease(min(1, t / 10))) * 14)
            out.append((c['num'], c['text'], max(0, k), slide))
    return out[-1:]  # one at a time


# ---------------- title and end cards
random.seed(7)
STARS = [(random.random() * W, random.random() * H, random.random() ** 3 * 1.6 + .4, random.random()) for _ in range(420)]
def space(drift=0.0):
    img = Image.new('RGB', (W, H), (0, 0, 0)); d = ImageDraw.Draw(img)
    for x, y, r, b in STARS:
        xx = (x + drift * (r * 40)) % W; c = int(90 + 150 * b)
        d.ellipse((xx - r, y - r, xx + r, y + r), fill=(c, c, min(255, c + 20)))
    glow = Image.new('RGB', (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W / 2 - 520, H / 2 - 360, W / 2 + 520, H / 2 + 360), fill=(18, 28, 60))
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), .55)

def logo(d, cx, cy, r, a):
    w = max(1, round(r / 11))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, a), width=w)
    d.ellipse((cx - r * .44, cy - r, cx + r * .44, cy + r), outline=(255, 255, 255, int(a * .5)), width=max(1, w - 1))
    d.line((cx - r, cy, cx + r, cy), fill=(255, 255, 255, int(a * .5)), width=max(1, w - 1))
    mx, my, mr = cx + r * .56, cy - r * .52, r * .24
    d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=MARS + (a,))

def card(lines, t, drift):
    """lines: list of (text, font, color, dy); t: 0..1 reveal"""
    base = space(drift).convert('RGBA')
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    a = int(255 * min(1, t))
    s = .92 + .08 * ease(min(1, t))
    logo(d, W / 2, H / 2 - 150, 54 * s, a)
    for text, fnt, col, dy in lines:
        tw = d.textlength(text, font=fnt)
        d.text((W / 2 - tw / 2, H / 2 + dy + (1 - ease(min(1, t))) * 16), text, font=fnt, fill=col + (a,))
    return Image.alpha_composite(base, lay).convert('RGB')

TITLE = [('Planalogy', font('InterDisplay-Light.otf', 104), (255, 255, 255), -70),
         ('Where on Earth is Mars?', font('InterDisplay-Regular.otf', 36), (194, 194, 198), 62),
         ('NASA Space Apps Challenge 2026', font('Inter-Medium.otf', 20), (139, 139, 146), 140)]
END = [('Pick a place on Mars.', font('InterDisplay-Light.otf', 64), (255, 255, 255), -64),
       ('Find it on Earth, today and in 2090.', font('InterDisplay-Light.otf', 64), (255, 255, 255), 16),
       ('Planalogy  |  NASA Space Apps Challenge 2026', font('Inter-Medium.otf', 20), (139, 139, 146), 130)]


# ---------------- frames
cam = camera_track()
def app_frame(f):
    img = Image.open(f'/tmp/rec/frames/f_{min(f, N_APP - 1):05d}.jpg').convert('RGB')
    img = crop(img, *cam[min(f, N_APP - 1)])
    caps = captions_at(f)
    if caps:
        img = Image.alpha_composite(img.convert('RGBA'), caption_layer(*caps[0])).convert('RGB')
    return img

def frames():
    for i in range(INTRO):                       # title card, the last XF_IN frames dissolve into the app
        c = card(TITLE, i / 22, i / FPS)
        if i >= INTRO - XF_IN:
            c = Image.blend(c, app_frame(0), ease((i - (INTRO - XF_IN) + 1) / (XF_IN + 1)))
        yield c
    for f in range(N_APP):
        yield app_frame(f)
    last = app_frame(N_APP - 1)
    for i in range(OUTRO):
        c = card(END, max(0, i - 6) / 20, (INTRO + N_APP + i) / FPS)
        yield Image.blend(last, c, ease(min(1, (i + 1) / XF_OUT)))

TOTAL = INTRO + N_APP + OUTRO
if TEST:
    want = set(int(x) for x in TEST)
    for i, im in enumerate(frames()):
        if i in want: im.save(f'/tmp/rec/test_{i:04d}.jpg', quality=90)
        if i >= max(want): break
    sys.exit()

json.dump({'intro': INTRO, 'app': N_APP, 'outro': OUTRO, 'total': TOTAL}, open('/tmp/rec/layout.json', 'w'))
ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                       '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                       '/tmp/rec/video_tmp.mp4'], stdin=subprocess.PIPE)
for i, im in enumerate(frames()):
    ff.stdin.write(im.tobytes())
ff.stdin.close(); rc = ff.wait()
print('frames', TOTAL, 'seconds', round(TOTAL / FPS, 2), 'ffmpeg', rc)
