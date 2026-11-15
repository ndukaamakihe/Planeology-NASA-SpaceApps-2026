"""Planalogy demo recorder: drives the app with a virtual clock, one JPEG per frame at 30 fps.
Writes frames to /tmp/rec/frames and an event log (clicks, captions, camera) to /tmp/rec/events.json."""
import asyncio, json, math, os, sys, time
from playwright.async_api import async_playwright

FPS = 30
W, H = 1920, 1080
OUT = '/tmp/rec/frames'
URL = 'http://localhost:8765/#finder'
ONLY = int(sys.argv[1]) if len(sys.argv) > 1 else None   # test mode: stop after this many frames

CLOCK = r"""
(() => {
  let t = 0, id = 0; const q = [];
  const d0 = Date.now();
  performance.now = () => t; Date.now = () => d0 + t;
  window.requestAnimationFrame = cb => { q.push([++id, cb]); return id; };
  window.cancelAnimationFrame = i => { const k = q.findIndex(x => x[0] === i); if (k >= 0) q.splice(k, 1); };
  window.__vt = {
    step(ms){ t += ms; const cbs = q.splice(0); for (const [, cb] of cbs){ try { cb(t); } catch(e){ console.error(e); } } },
    now: () => t
  };
})();
"""

CURSOR = r"""
(() => {
  const c = document.createElement('div'); c.id = '__cur';
  c.innerHTML = '<svg width="30" height="36" viewBox="0 0 30 36"><path d="M3 2 L3 28 L10 21.5 L15 33 L19.5 31 L14.5 19.8 L24 19.8 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, {position:'fixed', left:'0', top:'0', zIndex:99999, pointerEvents:'none', filter:'drop-shadow(0 3px 6px rgba(0,0,0,.55))', transformOrigin:'3px 2px'});
  const r = document.createElement('div'); r.id = '__rip';
  Object.assign(r.style, {position:'fixed', left:'0', top:'0', width:'56px', height:'56px', margin:'-28px 0 0 -28px', borderRadius:'50%',
    border:'2px solid rgba(255,255,255,.9)', boxShadow:'0 0 18px rgba(120,170,255,.6)', zIndex:99998, pointerEvents:'none', opacity:'0'});
  document.body.append(r, c);
  window.__frame = (x, y, press, rx, ry, rk) => {
    __vt.step(1000 / 30);
    c.style.transform = `translate(${x - 3}px, ${y - 2}px) scale(${press ? .86 : 1})`;
    if (rk >= 0 && rk <= 1){ r.style.left = rx + 'px'; r.style.top = ry + 'px'; r.style.opacity = String(1 - rk); r.style.transform = `scale(${.3 + rk * 1.1})`; }
    else r.style.opacity = '0';
  };
})();
"""

ease = lambda t: t * t * (3 - 2 * t)


class Rec:
    def __init__(self, page, cdp):
        self.page, self.cdp = page, cdp
        self.n = 0; self.x, self.y = W * .72, H * .62
        self.rip = None; self.events = {'clicks': [], 'captions': [], 'camera': [], 'marks': {}}

    async def frame(self, press=False):
        rk, rx, ry = -1, 0, 0
        if self.rip:
            rx, ry, f0 = self.rip; rk = (self.n - f0) / 14
            if rk > 1: self.rip = None
        await self.page.evaluate('([x,y,p,rx,ry,rk]) => __frame(x,y,p,rx,ry,rk)', [self.x, self.y, press, rx, ry, rk])
        await self.page.screenshot(path=f'{OUT}/f_{self.n:05d}.jpg', type='jpeg', quality=92)
        self.n += 1
        if ONLY and self.n >= ONLY: raise SystemExit

    async def hold(self, sec):
        for _ in range(round(sec * FPS)): await self.frame()

    async def box(self, js):
        b = await self.page.evaluate(js)
        if not b: raise RuntimeError('target not found: ' + js[:80])
        return b

    async def move(self, x, y, sec=.7):
        x0, y0, n = self.x, self.y, max(1, round(sec * FPS))
        # a gentle arc, like a hand
        bend = .12 * math.hypot(x - x0, y - y0)
        for i in range(1, n + 1):
            t = ease(i / n)
            self.x = x0 + (x - x0) * t + math.sin(math.pi * t) * bend * .3
            self.y = y0 + (y - y0) * t - math.sin(math.pi * t) * bend * .5
            await self.frame()
        self.x, self.y = x, y

    async def click(self, x, y, sec=.7, settle=.9, label=None):
        await self.move(x, y, sec)
        await self.frame(press=True)
        self.events['clicks'].append({'frame': self.n, 'label': label})
        self.rip = (x, y, self.n)
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(int(settle * 1000))   # real time for data and scoring; the video clock stands still
        await self.frame()

    async def click_el(self, js, **kw):
        b = await self.box(js)
        await self.click(b['x'], b['y'], **kw)

    def caption(self, num, text, dur):
        self.events['captions'].append({'frame': self.n, 'frames': round(dur * FPS), 'num': num, 'text': text})

    def cam(self, zoom, cx, cy, sec):
        self.events['camera'].append({'frame': self.n, 'frames': round(sec * FPS), 'zoom': zoom, 'cx': cx, 'cy': cy})

    def mark(self, name): self.events['marks'][name] = self.n


def by_text(sel, text):
    return f"""(() => {{ const el = [...document.querySelectorAll({json.dumps(sel)})].find(e => e.textContent.includes({json.dumps(text)}));
      if (!el) return null; const r = el.getBoundingClientRect(); return {{x: r.left + r.width / 2, y: r.top + r.height / 2}}; }})()"""


def at(sel, fx=.5, fy=.5):
    return f"""(() => {{ const el = document.querySelector({json.dumps(sel)}); if (!el) return null;
      const r = el.getBoundingClientRect(); return {{x: r.left + r.width * {fx}, y: r.top + r.height * {fy}}}; }})()"""


async def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome',
                                    args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars'])
        ctx = await b.new_context(viewport={'width': W, 'height': H})
        # warm the HTTP cache with every data file so no step waits on the network
        warm = await ctx.new_page(); await warm.goto(URL); await warm.wait_for_timeout(5000)
        await warm.evaluate("""async () => { const m = await (await fetch('data/planalogy/manifest.json')).json();
            const fs = [m.files.mars, m.files.earth.now, ...m.scenarios.flatMap(s => Object.values(s.files))];
            await Promise.all(fs.map(f => fetch('data/planalogy/' + f).then(r => r.text()))); }""")
        await warm.close()

        page = await ctx.new_page()
        page.on('pageerror', lambda e: print('PAGE ERROR', e))
        await page.add_init_script(CLOCK)
        await page.goto(URL)
        await page.wait_for_function('document.querySelector(".tv")')
        await page.evaluate(CURSOR)
        cdp = await ctx.new_cdp_session(page)
        await cdp.send('Animation.enable')
        r = Rec(page, cdp)
        # let the opening flight to Gale settle off camera
        for _ in range(45): await page.evaluate('__vt.step(1000/30)')
        await page.wait_for_timeout(2500)
        # CSS animations run on the wall clock: slow them to the recording speed
        t0 = time.time(); await r.frame(); await r.frame(); per = (time.time() - t0) / 2
        await cdp.send('Animation.setPlaybackRate', {'playbackRate': max(.03, min(1, (1000 / FPS) / (per * 1000)))})
        print('seconds per frame', round(per, 3))

        canvas = await r.box(at('.s-globe canvas'))
        gx, gy = canvas['x'], canvas['y']

        # 1  Mars target
        r.mark('app')
        r.caption(1, 'Pick a target on Mars', 4.0)
        r.cam(1.08, gx, gy, 2.6)
        await r.hold(.5)
        await r.click(gx - 150, gy + 90, sec=.9, label='mars')
        await r.hold(.7)
        await r.click_el(by_text('.f-seg button', 'Gale'), sec=.6, label='gale')
        await r.hold(.6)

        # Moon, quickly
        r.cam(1.0, W / 2, H / 2, .8)
        r.caption(0, 'Works for the Moon too', 1.6)
        await r.click_el(at('.orb-b:nth-child(2) .orb'), sec=.6, label='moon')
        await r.hold(.7)
        await r.click_el(at('.orb-b:nth-child(3) .orb'), sec=.45, label='mars')
        await r.hold(.2)

        # 2  Earth
        r.caption(2, 'Find its analogs on Earth', 3.0)
        await r.click_el(at('.cta'), sec=.55, settle=1.4, label='cta')
        r.mark('flight')
        r.cam(1.06, gx + 40, gy, 1.6)
        await r.hold(1.6)

        # 3  mission
        r.caption(3, 'Choose a mission', 2.0)
        r.cam(1.0, W / 2, H / 2, .6)
        await r.click_el(by_text('.chip', 'Ice prospecting'), sec=.6, settle=1.2, label='mission')
        await r.hold(1.2)

        # 4  time
        r.caption(4, 'Move through time', 5.6)
        b5 = await r.box(by_text('.tl-scen button', 'SSP5-8.5'))
        r.cam(1.0, W / 2, H / 2, .4)
        await r.click(b5['x'], b5['y'], sec=.6, settle=1.6, label='scen')   # switching the scenario jumps to 2050
        r.cam(1.16, gx + 60, gy - 20, 1.8)
        await r.hold(1.5)
        await r.click_el(by_text('.tl-stop', '2090'), sec=.55, settle=1.3, label='2090')
        r.mark('reveal')
        await r.hold(2.0)

        # different mission in the same year
        r.cam(1.0, W / 2, H / 2, .7)
        await r.click_el(by_text('.chip', 'Thermal testing'), sec=.6, settle=1.2, label='mission')
        await r.hold(1.5)

        # 5  parameters
        r.caption(5, 'Tune the parameters', 2.6)
        await r.click_el(f"""(() => {{ const l = [...document.querySelectorAll('.pr label')].find(e => e.textContent === 'Albedo');
            const i = l && l.parentElement.querySelector('input[type=checkbox]'); if (!i) return null; const q = i.getBoundingClientRect();
            return {{x: q.left + q.width / 2, y: q.top + q.height / 2}}; }})()""", sec=.6, settle=1.0, label='param')
        await r.hold(.35)
        await r.click_el(f"""(() => {{ const l = [...document.querySelectorAll('.pr label')].find(e => e.textContent === 'Terrain');
            const i = l && l.parentElement.querySelector('input[type=range]'); if (!i) return null; const q = i.getBoundingClientRect();
            return {{x: q.left + q.width * .82, y: q.top + q.height / 2}}; }})()""", sec=.45, settle=1.0, label='param')
        await r.hold(.7)

        # 1-km site card
        r.caption(0, 'Atacama, 1 km detail from today to 2090', 3.2)
        sc = await page.evaluate("""() => { const el = [...document.querySelectorAll('.f-site')].find(e => e.textContent.includes('Atacama'));
            const s = document.querySelector('.fp-scroll'); if (!el || !s) return 0; const r = el.getBoundingClientRect(), b = s.getBoundingClientRect();
            return Math.max(0, r.bottom - b.bottom + 12); }""")
        if sc > 0:
            for i in range(1, 9):
                await page.evaluate(f"document.querySelector('.fp-scroll').scrollTop += {sc / 8}"); await r.frame()
        await r.click_el(by_text('.f-site', 'Atacama'), sec=.6, settle=1.4, label='site')
        r.cam(1.05, W * .36, H * .55, 1.4)
        await r.hold(2.7)
        r.mark('end')
        print('frames', r.n)
        json.dump(r.events, open('/tmp/rec/events.json', 'w'), indent=1)
        await b.close()

asyncio.run(main())
