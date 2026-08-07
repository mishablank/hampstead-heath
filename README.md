# Hampstead Heath & Its Village – a walking audio guide

A twenty-stop loop from Hampstead Underground station, over the top of the
Heath to Kenwood and back down past the swimming ponds. 23 tracks, 36 minutes,
plus the full transcript.

Every track opens with where you should be standing and closes by telling you
where to walk next. Nothing auto-advances: between stops you are walking, not
listening.

- `index.html` – the page: transcript plus a play button on every stop
- `audio/` – the 23 tracks
- `hampstead-heath-full-walk.m4a` – all of it as one continuous file, for offline
- `build.py` – the narration, and everything that is generated from it

Narration is synthesised speech (Jamie (Premium) at 168 wpm). Opening hours were
checked in August 2026 and are the first thing that will change.

## Rebuilding

Needs macOS (`say`) and `mutagen`; the cover also needs `pillow`.

```bash
python3 build.py            # audio, then the page
python3 build.py --page     # page only, re-timed from the audio already there
python3 build.py --cover    # redraw cover.jpg
```

The text lives in one place, `STOPS` in `build.py`, so the transcript on the
page cannot drift out of step with the recording. Change `VOICE` and `RATE` at
the top and the whole set rebuilds in about a minute.

Deployed from `main` to Cloudflare.
