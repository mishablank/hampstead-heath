#!/usr/bin/env python3
"""Build map.json: the shape of the Heath, its water, its roads, and the twenty stops.

Geometry comes from OpenStreetMap via Overpass and is simplified hard, because
the map on the page is inline SVG and has to stay small enough to ship inside
the HTML. Stop coordinates live in STOPS_LL below rather than being looked up
at build time, so the map cannot silently move when somebody edits an OSM node.

    python3 fetch_map.py

Output is committed. OSM data is ODbL; the page credits OpenStreetMap.
"""

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# lat, lon. Most of these are what OpenStreetMap holds for the named feature
# itself, read back through Nominatim; the rest were placed by hand and then
# checked against the drawn roads and water, which is half of what the map is
# for. Hand-typed coordinates were out by up to 300 metres, so do not trust
# memory here.
STOPS_LL = {
 1:  (51.55654, -0.17812),   # Hampstead Underground station
 2:  (51.55618, -0.18108),   # Church Row / St John-at-Hampstead
 3:  (51.55690, -0.18029),   # St Mary's, Holly Walk
 4:  (51.55800, -0.17946),   # Holly Bush Hill / Romney's House
 5:  (51.55888, -0.17970),   # Fenton House
 6:  (51.55976, -0.18001),   # Admiral's House
 7:  (51.56057, -0.18004),   # Hampstead Observatory, on the reservoir
 8:  (51.56056, -0.17920),   # Whitestone Pond
 9:  (51.56560, -0.18397),   # The Hill Garden and Pergola
 10: (51.56682, -0.18938),   # Golders Hill Park
 11: (51.56145, -0.18010),   # Jack Straw's Castle
 12: (51.56294, -0.17628),   # Vale of Health
 13: (51.57023, -0.17372),   # The Spaniards Inn
 14: (51.57155, -0.16734),   # Kenwood House
 15: (51.57155, -0.16734),   # Dido Belle, inside Kenwood
 16: (51.56699, -0.16042),   # Kenwood Ladies' Pond
 17: (51.56475, -0.15905),   # Highgate Men's Pond
 18: (51.56060, -0.15760),   # The Tumulus
 19: (51.55940, -0.15450),   # Parliament Hill summit
 20: (51.55644, -0.15131),   # Parliament Hill Lido
 21: (51.55758, -0.16554),   # Hampstead Ponds, and the Fleet under them
 22: (51.55552, -0.16794),   # Keats House
 23: (51.56018, -0.17455),   # the lock-up, in Cannon Hall's garden wall
 24: (51.55819, -0.17504),   # Well Walk and Burgh House
}

# a little wider than the stops, so nothing is cropped at a marker
BBOX = (51.5525, -0.1955, 51.5760, -0.1480)          # S, W, N, E

# the Heath is not one polygon. West Heath, Sandy Heath and the Extension are
# mapped separately, and leaving them out puts the Pergola in a white field.
HEATH = ("Hampstead Heath|West Heath|Sandy Heath|Golders Hill Park|"
         "Hampstead Heath Extension|Parliament Hill Fields")

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
UA = {"User-Agent": "hampstead-heath-audio-guide/1.0 "
                    "(https://github.com/mishablank/hampstead-heath)"}
HERE = os.path.dirname(os.path.abspath(__file__))

# the roads a walker actually navigates by, and no others
ROADS = ["Spaniards Road", "East Heath Road", "Hampstead Lane", "North End Way",
         "Heath Street", "West Heath Road", "Highgate West Hill", "Millfield Lane",
         "Gordon House Road", "Well Walk", "Willow Road", "Hampstead High Street",
         "Rosslyn Hill", "Highgate Road", "Swains Lane", "South End Road",
         "Fitzjohn's Avenue", "Frognal", "Platts Lane", "Finchley Road"]


def overpass(query):
    """Overpass times out under load; try the main instance, then the mirror."""
    for endpoint in OVERPASS:
        for attempt in range(3):
            try:
                data = urllib.parse.urlencode({"data": query}).encode()
                req = urllib.request.Request(endpoint, data=data, headers=UA)
                return json.load(urllib.request.urlopen(req, timeout=180))
            except Exception as e:                      # 504s, resets, timeouts
                print("  retry (%s): %s" % (endpoint.split("/")[2], e), file=sys.stderr)
                time.sleep(8 * (attempt + 1))
    sys.exit("Overpass would not answer; try again later")


def rings(elements):
    """Ways, and multipolygon members, as lists of (lat, lon)."""
    out = []
    for el in elements:
        if el["type"] == "way" and el.get("geometry"):
            out.append([(p["lat"], p["lon"]) for p in el["geometry"] if p.get("lat")])
        elif el["type"] == "relation":
            for m in el.get("members", []):
                if m.get("geometry") and m.get("role") in ("outer", "", None):
                    out.append([(p["lat"], p["lon"]) for p in m["geometry"] if p.get("lat")])
    return out


def simplify(pts, tol):
    """Douglas-Peucker, in degrees. Iterative, because some of these ways are
    long enough to blow the recursion limit."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        a, b = pts[lo], pts[hi]
        dx, dy = b[1] - a[1], b[0] - a[0]
        n = math.hypot(dx, dy)
        worst, idx = 0.0, -1
        for i in range(lo + 1, hi):
            p = pts[i]
            d = (abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / n if n else
                 math.hypot(p[1] - a[1], p[0] - a[0]))
            if d > worst:
                worst, idx = d, i
        if idx > 0 and worst > tol:
            keep[idx] = True
            stack += [(lo, idx), (idx, hi)]
    return [p for p, k in zip(pts, keep) if k]


def inside(pts):
    s, w, n, e = BBOX
    pad = 0.004
    return [(lat, lon) for lat, lon in pts
            if s - pad < lat < n + pad and w - pad < lon < e + pad]


def main():
    s, w, n, e = BBOX
    box = "%f,%f,%f,%f" % (s, w, n, e)

    print("heath and parks...")
    heath = overpass(
        '[out:json][timeout:120];('
        'relation["leisure"~"park|nature_reserve"]["name"~"%s"](%s);'
        'way["leisure"~"park|nature_reserve"]["name"~"%s"](%s);'
        'way["natural"~"heath|scrub|wood"]["name"~"%s"](%s);'
        ');out geom;' % (HEATH, box, HEATH, box, HEATH, box))

    print("water...")
    water = overpass(
        '[out:json][timeout:120];('
        'way["natural"="water"](%s);relation["natural"="water"](%s);'
        ');out geom;' % (box, box))

    print("roads...")
    names = "|".join(r.replace("'", ".") for r in ROADS)
    roads = overpass(
        '[out:json][timeout:120];way["highway"]["name"~"^(%s)$"](%s);out geom;'
        % (names, box))

    out = {
        "bbox": list(BBOX),
        "stops": {str(k): list(v) for k, v in STOPS_LL.items()},
        "heath": [r for r in (simplify(inside(x), 0.00020) for x in rings(heath["elements"]))
                  if len(r) > 3],
        "water": [r for r in (simplify(inside(x), 0.00008) for x in rings(water["elements"]))
                  if len(r) > 3],
        "roads": [r for r in (simplify(inside(x), 0.00014) for x in rings(roads["elements"]))
                  if len(r) > 1],
    }
    for key in ("heath", "water", "roads"):
        out[key] = [[[round(a, 5), round(b, 5)] for a, b in ring] for ring in out[key]]

    path = os.path.join(HERE, "map.json")
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print("map.json  heath %d, water %d, roads %d  (%dkB)"
          % (len(out["heath"]), len(out["water"]), len(out["roads"]),
             os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main()
