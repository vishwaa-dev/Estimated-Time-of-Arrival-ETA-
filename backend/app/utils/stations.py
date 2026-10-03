"""Approximate station coordinates for weather lookups.

Route items from RailRadar do not carry lat/lng, so we keep a small registry
of known stations (values approximate; area-level accuracy is sufficient for
weather) and fall back to linear interpolation along the route, weighted by
cumulative distance between the nearest known stations.
"""

STATION_COORDS: dict[str, tuple[float, float]] = {
    # 12637 Pandian SF Express (Chennai Egmore -> Madurai Jn)
    "MS": (13.0777, 80.2613),
    "TBM": (12.9247, 80.1007),
    "CGL": (12.6929, 79.9812),
    "VM": (11.9401, 79.4861),
    "VRI": (11.5127, 79.6523),
    "TPJ": (10.7905, 78.6868),
    "MPA": (10.6007, 78.4192),
    "DG": (10.3673, 77.9803),
    "ABI": (10.2207, 77.8442),
    "KQN": (10.1434, 77.7732),
    "MDU": (9.9206, 78.1100),
    # 12168 Mumbai LTT SF Express (Banaras -> Mumbai LTT)
    "BNRS": (25.2993, 82.9718),
    "BSB": (25.3176, 82.9739),
    "PCOI": (25.3772, 81.8930),
    "MKP": (25.0749, 80.9079),
    "STA": (24.5745, 80.8322),
    "MYR": (24.2645, 80.7510),
    "KTE": (23.8375, 80.3946),
    "JBP": (23.1685, 79.9339),
    "ET": (22.6127, 77.7626),
    "KNW": (21.8256, 76.3390),
    "BAU": (21.3090, 76.2300),
    "BSL": (20.0464, 75.7863),
    "NK": (19.9475, 73.8378),
    "KYN": (19.2403, 73.1305),
    "LTT": (19.0695, 72.8920),
}


def resolve_coords(
    points: list[dict],
    source_coords: tuple[float, float] | None,
    dest_coords: tuple[float, float] | None,
) -> dict[int, tuple[float, float]]:
    """Assign a (lat, lng) to each route point.

    `points` are parsed route dicts (in sequence order) each carrying
    `sequence`, `station_code`, `distance_km`. Known stations use the registry;
    unknown stations are linearly interpolated between the nearest known
    neighbours by distance. Returns {sequence: (lat, lng)}.
    """
    known: list[tuple[float, int, tuple[float, float]]] = []  # (distance, index, coords)
    for i, p in enumerate(points):
        code = p.get("station_code")
        coords = STATION_COORDS.get(code)
        if coords is None and i == 0 and source_coords:
            coords = source_coords
        if coords is None and i == len(points) - 1 and dest_coords:
            coords = dest_coords
        if coords:
            known.append((p.get("distance_km") or 0.0, i, coords))

    out: dict[int, tuple[float, float]] = {}
    for i, p in enumerate(points):
        code = p.get("station_code")
        if code in STATION_COORDS:
            out[p["sequence"]] = STATION_COORDS[code]
            continue
        if i == 0 and source_coords:
            out[p["sequence"]] = source_coords
            continue
        if i == len(points) - 1 and dest_coords:
            out[p["sequence"]] = dest_coords
            continue
        if not known:
            continue
        dist = p.get("distance_km")
        if dist is None:
            continue
        prev = max([k for k in known if k[1] <= i], key=lambda k: k[1], default=None)
        nxt = min([k for k in known if k[1] >= i], key=lambda k: k[1], default=None)
        if prev and nxt and prev[1] != nxt[1]:
            d0, d1 = prev[0], nxt[0]
            if d1 - d0 > 0:
                t = max(0.0, min(1.0, (dist - d0) / (d1 - d0)))
                lat = prev[2][0] + t * (nxt[2][0] - prev[2][0])
                lng = prev[2][1] + t * (nxt[2][1] - prev[2][1])
                out[p["sequence"]] = (round(lat, 5), round(lng, 5))
    return out
