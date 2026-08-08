#!/usr/bin/env python3
"""Fetch one photograph per track from Wikimedia Commons.

Every file listed in PICKS is freely licensed. This script downloads it,
resizes it to something a phone on the Heath can actually load, and writes
images/credits.json with the photographer, the licence and the source page.
build.py reads that manifest and puts the credit under the picture, which is
what the licences require.

    python3 fetch_images.py

Re-run it only when you want to change a picture. The output is committed.
"""

import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

# track index -> Commons file. Chosen to show the thing you are standing in
# front of, rather than the prettiest available photograph of it.
PICKS = {
 0:  "File:Hampstead Heath, London - geograph.org.uk - 3924668.jpg",
 1:  "File:Hampstead station building.JPG",
 2:  "File:Church Row, Hampstead.jpg",
 3:  "File:Fenton House, Hampstead - geograph.org.uk - 1271918.jpg",
 4:  "File:Hampstead Scientific Society - geograph.org.uk - 609321.jpg",
 5:  "File:Whitestone Pond Hampstead Heath London 134m190 20220423 1928.jpg",
 6:  "File:Hampstead , Hill Garden and Pergola - geograph.org.uk - 8084698.jpg",
 7:  "File:Golders Hill Park in 2006.jpg",
 8:  "File:Jack Straw's Castle.jpg",
 9:  "File:Vale of Health, Hampstead - geograph.org.uk - 3711963.jpg",
 10: "File:The Spaniards Inn - geograph.org.uk - 1003208.jpg",
 11: "File:Kenwood House, south front - geograph.org.uk - 1472942.jpg",
 12: "File:Dido Elizabeth Belle.jpg",
 13: "File:Kenwood Ladies Bathing Pond - geograph.org.uk - 1841422.jpg",
 14: "File:Highgate Men's Bathing Pond - geograph.org.uk - 1570343.jpg",
 15: "File:Boudicca's Grave, Hampstead Heath (South Face - 01).jpg",
 16: "File:Parliament Hill view of Central London - geograph.org.uk - 1568116.jpg",
 17: "File:Parliament Hill Lido (6448960385).jpg",
 18: "File:Pond on Hampstead Heath - geograph.org.uk - 1850332.jpg",
 19: "File:Keats' House, Hampstead - geograph.org.uk - 221032.jpg",
 20: "File:Burgh House in New End Square - geograph.org.uk - 674944.jpg",
 21: "File:Path on Hampstead Heath - geograph.org.uk - 1916802.jpg",
 22: "File:The Isokon building, Lawn Road - geograph.org.uk - 673713.jpg",
}

# fraction of the original kept, as (left, top, right, bottom). The pergola is
# shot upright and would otherwise be a metre tall on the page.
CROPS = {6: (0.0, 0.02, 1.0, 0.60)}

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "hampstead-heath-audio-guide/1.0 "
                    "(https://github.com/mishablank/hampstead-heath)"}
MAXW = 1400
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "images")


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def fetch(url):
    """Commons rate-limits hard; back off rather than hammer it."""
    for attempt in range(6):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read()
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("rate limited: " + url)


def main():
    sys.path.insert(0, HERE)
    import build

    os.makedirs(OUT, exist_ok=True)
    credits = {}
    for i, title in sorted(PICKS.items()):
        q = urllib.parse.urlencode({
            "action": "query", "titles": title, "prop": "imageinfo",
            "iiprop": "url|extmetadata|size", "iiurlwidth": MAXW,
            "format": "json", "formatversion": 2})
        page = json.loads(fetch(API + "?" + q))["query"]["pages"][0]
        if "imageinfo" not in page:
            sys.exit("no such file on Commons: " + title)
        ii = page["imageinfo"][0]
        meta = ii["extmetadata"]

        im = Image.open(io.BytesIO(fetch(ii.get("thumburl") or ii["url"]))).convert("RGB")
        if i in CROPS:
            l, t, r, b = CROPS[i]
            im = im.crop((int(l * im.width), int(t * im.height),
                          int(r * im.width), int(b * im.height)))
        if im.width > MAXW:
            im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)

        name = "%02d-%s.jpg" % (i, build.slug(build.STOPS[i]["title"]))
        im.save(os.path.join(OUT, name), quality=80, optimize=True, progressive=True)
        credits[str(i)] = {
            "file": name,
            "w": im.width, "h": im.height,
            "by": strip(meta.get("Artist", {}).get("value")) or "Unknown",
            "lic": strip(meta.get("LicenseShortName", {}).get("value")),
            "licurl": strip(meta.get("LicenseUrl", {}).get("value")),
            "src": ii["descriptionurl"],
            "edit": "cropped and resized" if i in CROPS else "resized",
        }
        print("%2d  %-46s %4dx%-4d %5dkB  %s"
              % (i, name, im.width, im.height,
                 os.path.getsize(os.path.join(OUT, name)) // 1024, credits[str(i)]["lic"]))
        time.sleep(1.2)

    json.dump(credits, open(os.path.join(OUT, "credits.json"), "w"), indent=1, sort_keys=True)
    print("  images/credits.json")


if __name__ == "__main__":
    main()
