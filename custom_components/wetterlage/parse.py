"""Einlesen der DWD-Rohdaten. Reine Funktionen ohne Netzwerk und ohne Home Assistant."""

from __future__ import annotations

from datetime import datetime
import io
import math
import re
from typing import Any
import zipfile

SEVERITY_LEVEL = {"Minor": 1, "Moderate": 2, "Severe": 3, "Extreme": 4}


def _dm_to_deg(value: float) -> float:
    """Der Stationskatalog gibt Grad.Minuten an (48.42 = 48° 42')."""
    sign = -1 if value < 0 else 1
    a = abs(value)
    deg = math.trunc(a)
    return sign * (deg + (a - deg) * 100 / 60)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.radians
    h = math.sin(rad(lat2 - lat1) / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def parse_station_catalog(text: str) -> list[dict[str, Any]]:
    """MOSMIX-Stationskatalog (feste Spaltenbreiten) einlesen."""
    stations = []
    for line in text.splitlines()[2:]:
        sid = line[0:5].strip()
        if not sid:
            continue
        try:
            lat = _dm_to_deg(float(line[32:38]))
            lon = _dm_to_deg(float(line[39:47]))
            elev = int(float(line[47:].strip() or 0))
        except ValueError:
            continue
        stations.append({"id": sid, "name": line[11:32].strip(), "lat": lat, "lon": lon, "elev": elev})
    return stations


def nearest_stations(stations: list[dict[str, Any]], lat: float, lon: float, count: int = 6) -> list[dict[str, Any]]:
    ranked = [{**s, "km": round(haversine_km(lat, lon, s["lat"], s["lon"]), 1)} for s in stations]
    ranked.sort(key=lambda s: s["km"])
    return ranked[:count]


def _num(v: str) -> float | None:
    return None if v == "-" else float(v)


def parse_mosmix_kmz(data: bytes) -> dict[str, Any]:
    """MOSMIX-L-Datei (KMZ) einer Station in Stundenwerte umwandeln."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        kml = zf.read(zf.namelist()[0]).decode("latin-1")
    times = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in re.findall(r"<dwd:TimeStep>([^<]+)<", kml)]
    elements: dict[str, list[float | None]] = {}
    for name, values in re.findall(r'elementName="([^"]+)">\s*<dwd:value>([^<]+)<', kml):
        elements[name] = [_num(v) for v in values.split()]
    issue_match = re.search(r"<dwd:IssueTime>([^<]+)<", kml)
    name_match = re.search(r"<kml:description>([^<]+)<", kml)

    def col(key: str, i: int) -> float | None:
        vals = elements.get(key)
        return vals[i] if vals and i < len(vals) else None

    def kelvin(v: float | None) -> float | None:
        return None if v is None else round(v - 273.15, 2)

    def mul(v: float | None, f: float) -> float | None:
        return None if v is None else round(v * f, 2)

    hours = []
    for i, t in enumerate(times):
        hours.append({
            "t": t,
            "T": kelvin(col("TTT", i)),
            "Td": kelvin(col("Td", i)),
            "T5": kelvin(col("T5cm", i)),
            "ff": mul(col("FF", i), 3.6),  # m/s -> km/h
            "fx": mul(col("FX1", i), 3.6),
            "dd": col("DD", i),
            "rr": col("RR1c", i),
            "pRain": col("R101", i),
            "ww": col("ww", i),
            "neff": col("Neff", i),
            "thunder": col("wwT", i),
            "sun": col("SunD1", i),  # Sekunden in der Stunde
            "rad": mul(col("Rad1h", i), 1 / 3.6),  # kJ/m² pro Stunde -> W/m²
            "p": mul(col("PPPP", i), 0.01),  # Pa -> hPa
        })
    return {
        "issue": datetime.fromisoformat(issue_match.group(1).replace("Z", "+00:00")) if issue_match else None,
        "name": name_match.group(1).strip() if name_match else None,
        "hours": hours,
    }


def _warning(props: dict[str, Any], quelle: str) -> dict[str, Any]:
    return {
        "id": props.get("IDENTIFIER"),
        "event": props.get("EVENT"),
        "headline": props.get("HEADLINE"),
        "description": props.get("DESCRIPTION"),
        "instruction": props.get("INSTRUCTION"),
        "level": SEVERITY_LEVEL.get(props.get("SEVERITY"), 0),
        "group": props.get("EC_GROUP") or "",
        "onset": props.get("ONSET"),
        "expires": props.get("EXPIRES"),
        "gebiet": quelle,
    }


def merge_warnings(gemeinde: list[dict[str, Any]], kreis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gemeinde- und Kreiswarnungen zusammenführen.

    Gemeindewarnungen sind genauer und haben Vorrang. Eine Kreiswarnung kommt nur dazu,
    wenn es für dieselbe Gruppe und denselben Beginn keine Gemeindewarnung gibt
    (z. B. Hitzewarnungen, die nur auf Kreisebene erscheinen).
    """
    out = [_warning(p, "Gemeinde") for p in gemeinde]
    seen = {(w["group"], w["onset"]) for w in out}
    for p in kreis:
        w = _warning(p, "Kreis")
        if (w["group"], w["onset"]) not in seen:
            out.append(w)
            seen.add((w["group"], w["onset"]))
    out.sort(key=lambda w: (-w["level"], w["onset"] or ""))
    return out


def parse_pollen(data: dict[str, Any]) -> dict[str, Any]:
    """Pollenflug-Gefahrenindex (s31fg.json) einlesen."""
    regions = []
    for c in data.get("content", []):
        rid = c["partregion_id"] if c.get("partregion_id", -1) != -1 else c["region_id"]
        regions.append({"id": rid, "region_id": c["region_id"], "bundesland": c.get("region_name"),
                        "name": c.get("partregion_name") or c.get("region_name"), "pollen": c.get("Pollen", {})})
    return {"update": data.get("last_update"), "regions": regions}


# Bundesland-Schlüssel (Stellen 2–3 der Warncell-ID einer Gemeinde) -> Pollenregion des DWD
STATE_TO_POLLEN_REGION = {
    "01": 10, "02": 10, "03": 30, "04": 30, "05": 40, "06": 90, "07": 100, "08": 110,
    "09": 120, "10": 100, "11": 50, "12": 50, "13": 20, "14": 80, "15": 60, "16": 70,
}


def pollen_region_for_warncell(warncell_id: int | None) -> int | None:
    """Pollen-Hauptregion aus der Warncell-ID einer Gemeinde (8SSKKKGGG) ableiten."""
    if not warncell_id:
        return None
    s = str(warncell_id)
    return STATE_TO_POLLEN_REGION.get(s[1:3]) if len(s) == 9 and s[0] == "8" else None
