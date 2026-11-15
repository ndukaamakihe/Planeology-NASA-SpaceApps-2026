"""Optional: sharper globe textures (8192 x 4096) for Mars, the Moon and Earth.

    python web/app/tex/get_textures.py            all three (about 25 MB)
    python web/app/tex/get_textures.py mars       only one body

The files go to web/app/tex/hi/ and tex/hi.js is rewritten so the app uses them; the relief shading
(MOLA, WorldClim) stays on top as a bump map. Without this script the app uses the textures in the repo.
Source: Solar System Scope, https://www.solarsystemscope.com/textures/ , licence CC BY 4.0
(based on NASA imagery). Needs only the Python standard library.
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://www.solarsystemscope.com/textures/download/"
FILES = {"mars": "8k_mars.jpg", "moon": "8k_moon.jpg", "earth": "8k_earth_daymap.jpg"}


def main():
    want = [b for b in sys.argv[1:] if b in FILES] or list(FILES)
    out = HERE / "hi"
    out.mkdir(exist_ok=True)
    for body in want:
        dest = out / f"{body}_8k.jpg"
        if dest.exists() and dest.stat().st_size > 500_000:
            print(f"ok (already there) {dest.name}")
            continue
        url = BASE + FILES[body]
        print(f"downloading {url} ...", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Planalogy student prototype)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if data[:2] != b"\xff\xd8":
                raise ValueError("not a JPEG (the site may have changed)")
            dest.write_bytes(data)
            print(f"{len(data) / 1e6:.1f} MB")
        except Exception as ex:  # noqa: BLE001
            print(f"FAILED: {ex}")
    have = {b: f"tex/hi/{b}_8k.jpg" for b in FILES if (out / f"{b}_8k.jpg").exists()}
    (HERE / "hi.js").write_text(
        "/* written by tex/get_textures.py: sharper globe textures (Solar System Scope, CC BY 4.0) */\n"
        f"window.PLANALOGY_HI = {json.dumps(have)};\n", encoding="utf-8")
    print(f"tex/hi.js now lists: {', '.join(have) or 'nothing'}. Reload the app.")


if __name__ == "__main__":
    main()
