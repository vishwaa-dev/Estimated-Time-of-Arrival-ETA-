"""One-off generator: writes the 8 synthetic train_*.json seed files (RailRadar snapshot shape).

Along with the two real provided snapshots (12637, 12168) these make up the
10 tracked trains.
"""
from datetime import datetime, timedelta
from pathlib import Path
import json

BASE = datetime.fromisoformat("2026-09-28T00:00:00+05:30")
OUT = Path(__file__).resolve().parents[1] / "data"

TRAINS = [
    ("12952", "Mumbai Rajdhani Express", "Rajdhani", ("NDLS", "New Delhi", 28.6425, 77.2199), ("BCT", "Mumbai Central", 18.9703, 72.8193), 985),
    ("12841", "Coromandel Express", "Superfast", ("SHM", "Sealdah", 22.5839, 88.3425), ("MAS", "MGR Chennai Central", 13.0827, 80.2757), 890),
    ("12626", "Kerala Express", "Superfast", ("TVC", "Thiruvananthapuram Central", 8.4875, 76.9525), ("NDLS", "New Delhi", 28.6425, 77.2199), 675),
    ("12723", "Telangana Express", "Superfast", ("HYB", "Hyderabad Deccan", 17.3850, 78.4867), ("NDLS", "New Delhi", 28.6425, 77.2199), 385),
    ("12903", "Golden Temple Mail", "Mail/Express", ("BCT", "Mumbai Central", 18.9703, 72.8193), ("ASR", "Amritsar Jn", 31.6340, 74.8723), 1285),
    ("12676", "Kovai Express", "Superfast", ("CBE", "Coimbatore Jn", 11.0018, 76.9628), ("MS", "Chennai Egmore", 13.0777, 80.2613), 370),
    ("12801", "Purushottam Express", "Express", ("PURI", "Puri", 19.8135, 85.8312), ("NDLS", "New Delhi", 28.6425, 77.2199), 1300),
    ("12137", "Punjab Mail", "Mail/Express", ("CSMT", "Mumbai CSMT", 18.9401, 72.8355), ("FZR", "Firozpur Cantt", 30.9165, 75.8496), 1175),
]

ROUTES = {
    "12952": [("NDLS", "New Delhi", None, 0, 0, "1"), ("KOTA", "Kota Jn", 295, 300, 458, "2"), ("RTM", "Ratlam Jn", 515, 520, 821, "3"), ("BRC", "Vadodara Jn", 695, 705, 1089, "1"), ("BCT", "Mumbai Central", 950, None, 1384, "6")],
    "12841": [("SHM", "Sealdah", None, 0, 0, "9"), ("KGP", "Kharagpur Jn", 165, 170, 166, "3"), ("BBS", "Bhubaneswar", 437, 442, 437, "1"), ("VSKP", "Visakhapatnam", 847, 857, 847, "2"), ("BZA", "Vijayawada Jn", 1316, 1321, 1316, "5"), ("MAS", "MGR Chennai Central", 1560, None, 1662, "9")],
    "12626": [("TVC", "Thiruvananthapuram Central", None, 0, 0, "1"), ("ERS", "Ernakulam Jn", 170, 175, 220, "2"), ("CBE", "Coimbatore Jn", 425, 430, 425, "3"), ("JTJ", "Jolarpettai Jn", 738, 743, 738, "1"), ("SBC", "KSR Bengaluru", 953, 963, 953, "9"), ("SC", "Secunderabad Jn", 1339, 1349, 1339, "10"), ("BZA", "Vijayawada Jn", 1731, 1736, 1731, "5"), ("BPQ", "Balharshah", 1968, 1973, 1968, "2"), ("NGP", "Nagpur Jn", 2378, 2383, 2378, "1"), ("BPL", "Bhopal Jn", 2713, 2718, 2713, "2"), ("AGC", "Agra Cantt", 2946, 2948, 2946, "3"), ("NDLS", "New Delhi", 3054, None, 3054, "1")],
    "12723": [("HYB", "Hyderabad Deccan", None, 0, 0, "1"), ("KZJ", "Kazipet Jn", 209, 214, 209, "2"), ("NGP", "Nagpur Jn", 749, 754, 749, "1"), ("BPL", "Bhopal Jn", 1128, 1133, 1128, "1"), ("AGC", "Agra Cantt", 1467, 1469, 1467, "3"), ("NDLS", "New Delhi", 1661, None, 1661, "1")],
    "12903": [("BCT", "Mumbai Central", None, 0, 0, "1"), ("ST", "Surat", 102, 104, 263, "2"), ("BRC", "Vadodara Jn", 247, 252, 392, "1"), ("RTM", "Ratlam Jn", 457, 462, 730, "3"), ("KOTA", "Kota Jn", 680, 685, 1068, "2"), ("AGC", "Agra Cantt", 1010, 1015, 1350, "2"), ("NDLS", "New Delhi", 1205, 1220, 1441, "1"), ("LDH", "Ludhiana Jn", 1665, 1675, 1745, "1"), ("ASR", "Amritsar Jn", 1910, None, 1893, "1")],
    "12676": [("CBE", "Coimbatore Jn", None, 0, 0, "1"), ("TPJ", "Tiruchchirappalli Jn", 215, 220, 215, "2"), ("VM", "Villupuram Jn", 351, 356, 351, "1"), ("MS", "Chennai Egmore", 425, None, 496, "4")],
    "12801": [("PURI", "Puri", None, 0, 0, "1"), ("BBS", "Bhubaneswar", 90, 95, 63, "1"), ("KGP", "Kharagpur Jn", 320, 325, 318, "3"), ("ASN", "Asansol Jn", 532, 537, 577, "1"), ("MGS", "Pt DD Upadhyaya Jn", 890, 900, 882, "1"), ("ALD", "Prayagraj Jn", 1085, 1090, 1082, "3"), ("CNB", "Kanpur Central", 1335, 1340, 1339, "6"), ("NDLS", "New Delhi", 1990, None, 2028, "1")],
    "12137": [("CSMT", "Mumbai CSMT", None, 0, 0, "18"), ("NK", "Nashik Road", 193, 195, 187, "3"), ("BSL", "Bhusaval Jn", 385, 390, 586, "2"), ("ET", "Itarsi Jn", 560, 565, 808, "1"), ("BPL", "Bhopal Jn", 740, 745, 1002, "1"), ("JHS", "Jhansi Jn", 975, 980, 1313, "2"), ("NDLS", "New Delhi", 1250, 1270, 1541, "1"), ("UMB", "Ambala Cantt Jn", 1490, 1500, 1818, "2"), ("LDH", "Ludhiana Jn", 1560, 1570, 1907, "1"), ("FZR", "Firozpur Cantt", 1755, None, 1931, "2")],
}


def speed_between(a, b):
    dist = (b["distance"] or 0) - (a["distance"] or 0)
    ta = a["dep"] or a["arr"]
    tb = b["arr"] or b["dep"]
    if ta is None or tb is None:
        return None
    hours = (tb - ta).total_seconds() / 3600.0
    if hours <= 0 or dist <= 0:
        return None
    return round(max(25.0, min(130.0, dist / hours)), 1)


for number, name, category, src, dst, dep_offset in TRAINS:
    dep_origin = BASE + timedelta(minutes=dep_offset)
    halts = [
        {
            "code": code, "name": sname,
            "arr": dep_origin + timedelta(minutes=arr_m) if arr_m is not None else None,
            "dep": dep_origin + timedelta(minutes=dep_m) if dep_m is not None else None,
            "distance": dist, "platform": platform,
        }
        for code, sname, arr_m, dep_m, dist, platform in ROUTES[number]
    ]

    route_items = []
    for i, h in enumerate(halts):
        nxt = halts[i + 1] if i + 1 < len(halts) else None
        item = {
            "sequence": i + 1,
            "stationCode": h["code"],
            "stationName": h["name"],
            "isHalt": True,
            "status": "at-station" if i == 0 else "upcoming",
            "distance": h["distance"],
        }
        if h["arr"] is not None:
            item["scheduledArrival"] = h["arr"].isoformat()
        if h["dep"] is not None:
            item["scheduledDeparture"] = h["dep"].isoformat()
        if h["platform"]:
            item["platform"] = h["platform"]
        sp = speed_between(h, nxt) if nxt else None
        if sp:
            item["speedToNextStationKmph"] = sp
        route_items.append(item)

    duration = int((halts[-1]["arr"] - halts[0]["dep"]).total_seconds() / 60)
    payload = {
        "success": True,
        "data": {
            "trainNumber": number,
            "trainName": name,
            "startDate": dep_origin.date().isoformat(),
            "lastUpdatedAt": dep_origin.isoformat(),
            "status": "not-started",
            "train": {
                "number": number, "name": name, "type": category.upper(), "category": category,
                "source": {"code": src[0], "name": src[1], "lat": src[2], "lng": src[3]},
                "destination": {"code": dst[0], "name": dst[1], "lat": dst[2], "lng": dst[3]},
                "runDays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                "distance": float(halts[-1]["distance"]),
                "duration": duration,
                "totalHalts": len(halts),
            },
            "isLive": False,
            "trackingMode": "off",
            "currentLocation": {
                "stationCode": halts[0]["code"], "stationName": halts[0]["name"],
                "sequence": 1, "status": "at-station", "isHalt": True,
                "isActualPosition": True, "positionSource": "station-code",
                "distanceFromOriginKm": 0, "distanceFromLastStationKm": 0, "delayMinutes": 0,
            },
            "delayMinutes": 0,
            "route": route_items,
        },
    }
    (OUT / f"train_{number}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote train_{number}.json  {name:38s} {src[0]}->{dst[0]}  {duration // 60}h{duration % 60:02d}m  {len(halts)} halts")
