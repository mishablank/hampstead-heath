# Hampstead Heath & Its Village – a walking audio guide

**https://hampstead-heath.blankm.workers.dev**

A twenty-stop loop from Hampstead Underground station, over the top of the
Heath to Kenwood and back down past the swimming ponds. 23 tracks, 36 minutes,
plus the full transcript.

Every track opens with where you should be standing and closes by telling you
where to walk next. Nothing auto-advances: between stops you are walking, not
listening.

- `index.html` – the page: transcript, a photograph and a play button on every stop
- `audio/` – the 23 tracks
- `images/` – one photograph per track, plus `credits.json`
- `hampstead-heath-full-walk.m4a` – all of it as one continuous file, for offline
- `build.py` – the narration, and everything that is generated from it
- `fetch_images.py` – re-fetches the photographs from Wikimedia Commons

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

## Pictures

Every track has one photograph, chosen to show the thing you are standing in
front of rather than the prettiest view of it. All are Creative Commons or
public domain, from Wikimedia Commons. Each is credited under the picture with
its photographer, licence and source, and `images/credits.json` carries the
same information in full. To change one, edit `PICKS` in `fetch_images.py` and
re-run it, then `python3 build.py --page`.

If you reuse these photographs elsewhere, the CC BY-SA terms come with them.

Deployed from `main` to Cloudflare Workers.
