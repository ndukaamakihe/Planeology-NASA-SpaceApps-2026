# Demo video (about 26 s)

Records the Analog Finder frame by frame with a virtual clock, so the video is smooth even on a slow machine.

```
cd web/app && python -m http.server 8765        # in a second terminal
python tools/demo_video/record.py               # clicks through the app, writes /tmp/rec/frames + events.json
python tools/demo_video/compose.py              # title card, camera moves, step captions, end card
python tools/demo_video/music.py                # synthesised soundtrack
ffmpeg -i /tmp/rec/video_tmp.mp4 -i /tmp/rec/music.wav -map 0:v -map 1:a -c:v copy -c:a aac -shortest planalogy_demo.mp4
```

Needs playwright with Chrome, Pillow, numpy and ffmpeg. Paths in the scripts point to /tmp/rec and /usr/bin/google-chrome; change them for Windows.
