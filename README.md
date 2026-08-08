# Hampstead Heath & Its Village – a walking audio guide

**https://hampstead-heath.blankm.workers.dev**

A twenty-stop loop from Hampstead Underground station, over the top of the
Heath to Kenwood and back down past the swimming ponds. 23 tracks, 36 minutes,
plus the full transcript.

Every track opens with where you should be standing and closes by telling you
where to walk next. Nothing auto-advances: between stops you are walking, not
listening.

- `index.html` – the page: map, transcript, a photograph and a play button on every stop
- `audio/` – the 23 tracks
- `images/` – one photograph per track, plus `credits.json`
- `map.json` – the shape of the Heath, its water and its roads, from OpenStreetMap
- `hampstead-heath-walk.gpx` – the twenty stops for a real navigation app
- `hampstead-heath-full-walk.m4a` – all of it as one continuous file, for offline
- `build.py` – the narration, and everything that is generated from it
- `fetch_images.py` – re-fetches the photographs from Wikimedia Commons
- `fetch_map.py` – re-fetches the map geometry from OpenStreetMap

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

## The map

Drawn as inline SVG from OpenStreetMap geometry: no tiles, no libraries, no
requests to anybody. That matters because the middle of the Heath has no
signal, and a slippy map is the first thing to fail there. Drag or pinch to
move it, tap a number to play that stop, and "Where am I" uses the browser's
own geolocation – nothing leaves the phone.

The dotted line is the order of the stops, not the path you walk. If you want
turn-by-turn, take the GPX.

Stop coordinates live in `STOPS_LL` in `fetch_map.py`. Hand-typed coordinates
were out by up to 300 metres, so check any you change against the drawn roads
and water rather than against memory. Map data © OpenStreetMap contributors,
ODbL.

Deployed from `main` to Cloudflare Workers.
