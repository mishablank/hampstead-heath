# Hampstead Heath & Its Village – a walking audio guide

**https://hampstead-heath.blankm.workers.dev**

A twenty-four-stop loop from Hampstead Underground station, over the top of the
Heath to Kenwood and back down past the swimming ponds. 27 tracks, plus the
full transcript.

Every track opens with where you should be standing and closes by telling you
where to walk next. Nothing auto-advances: between stops you are walking, not
listening.

- `index.html` – the page: map, transcript, a photograph and a play button on every stop
- `audio/` – the 27 tracks
- `images/` – one photograph per track, plus `credits.json`
- `map.json` – the shape of the Heath, its water and its roads, from OpenStreetMap
- `hampstead-heath-walk.gpx` – the stops for a real navigation app
- `hampstead-heath-full-walk.m4a` – all of it as one continuous file, for offline
- `build.py` – the narration, and everything that is generated from it
- `fetch_images.py` – re-fetches the photographs from Wikimedia Commons
- `fetch_map.py` – re-fetches the map geometry from OpenStreetMap

Narration is synthesised speech. Opening hours were checked in August 2026 and
are the first thing that will change.

## The voice, and why it is not a Mac voice

The macOS system voices are licensed for personal, non-commercial use only
(macOS SLA §2.F), and the same clause forbids publishing or public sharing of
their output. That rules them out for anything on a website, commercial or
not.

The build uses Google Cloud Chirp 3: HD instead. Commercial use is covered by
the standard Google Cloud terms, and the monthly free allowance for HD voices
is roughly thirty times the size of this script, so a rebuild is usually free.

```bash
export GOOGLE_API_KEY=...         # or GOOGLE_ACCESS_TOKEN for a bearer token
python3 build.py --voices         # the en-GB Chirp 3: HD voices
export GOOGLE_VOICE=en-GB-Chirp3-HD-Charon
python3 build.py --sample         # one track, to hear it before committing
python3 build.py                  # all 27 tracks, then rebuilds the page
```

Two other engines are available. `TTS_ENGINE=elevenlabs` (with
`ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`) costs about 36,000 credits per
rebuild and sounds better; every paid ElevenLabs plan grants commercial
rights, and they survive cancelling the plan. `TTS_ENGINE=say` is the Mac
voice, for drafting only. Do not publish it.

`--sample` names its output after the engine and voice, so you can render the
same track on two of them and compare.

The continuous full-walk file is spliced from the finished tracks rather than
synthesised again, which halves the credits and guarantees it matches. Pace,
model and stability are the `EL_*` constants at the top of `build.py`.
`voice.json` records which voice actually made the audio in the repo, and the
colophon reads from it, so the page cannot claim a voice it did not use.

## Rebuilding

Needs macOS (`afconvert`) and `mutagen`; the cover also needs `pillow`.

```bash
python3 build.py            # audio, then the page
python3 build.py --page     # page only, re-timed from the audio already there
python3 build.py --cover    # redraw cover.jpg
```

The text lives in one place, `STOPS` in `build.py`, so the transcript on the
page cannot drift out of step with the recording. Change the voice settings at
the top and the whole set rebuilds in one pass.

## Adding or moving a stop

Stop numbers are assigned from walking order in `build.py`, not written into
each entry, so inserting one renumbers the guide by itself. Three things do
need doing by hand: the spoken cross-references in neighbouring `walk` texts,
a coordinate in `STOPS_LL` in `fetch_map.py`, and a picture in `PICKS` in
`fetch_images.py`.

Be aware that inserting a stop changes the index prefix on every audio and
image file after it, so the whole set has to be re-rendered and re-fetched
before the page will build. Do that on a branch: a half-renumbered `main`
deploys a page whose photographs and audio all 404.

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
