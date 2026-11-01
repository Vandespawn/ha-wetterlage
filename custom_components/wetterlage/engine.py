"""Rechenkern: aus DWD-Daten, Stationswerten und Einstellungen alle Ergebnisse berechnen.

Reine Funktionen ohne Home Assistant. Jede Zahl, die hier eine Entscheidung trifft,
kommt aus den Einstellungen (siehe defaults.py).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
import math
from typing import Any

P_ORDER = ["0", "0-1", "1", "1-2", "2", "2-3", "3"]
P_LABEL = {"0": "keine", "0-1": "keine bis gering", "1": "gering", "1-2": "gering bis mittel",
           "2": "mittel", "2-3": "mittel bis hoch", "3": "hoch"}
P_NAME = {"Graeser": "Gräser", "Beifuss": "Beifuß"}
P_TAG = {"today": "heute", "tomorrow": "morgen", "dayafter_to": "übermorgen"}
HINT_KEYS = ["frost", "gewitter", "hitze", "sturm", "starkregen"]


@dataclass
class EngineInput:
    now: datetime
    tz: tzinfo
    hours: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    pollen_regions: list[dict[str, Any]] = field(default_factory=list)
    radar: list[dict[str, Any]] = field(default_factory=list)
    station: dict[str, float | None] = field(default_factory=dict)
    station_name: str = ""


def fmt(v: float | None, d: int = 1) -> str:
    """Zahl deutsch formatieren, ohne „-0“."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    if abs(v) < 0.5 * 10 ** -d:
        v = 0.0
    return f"{v:.{d}f}".replace(".", ",")


def signed(v: float, d: int = 1) -> str:
    return ("+" if v >= 0 else "−") + fmt(abs(v), d)


def _nmax(values, default=0.0):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else default


def _nmin(values, default=None):
    vals = [v for v in values if v is not None]
    return min(vals) if vals else default


# ---------- Wetterzustand ----------

def condition(h: dict[str, Any] | None, daylight: bool = True) -> tuple[str, str]:
    """(Text auf Deutsch, Home-Assistant-Zustand) aus DWD-Wettercode ww und Bewölkung."""
    if not h:
        return ("unbekannt", "exceptional")
    w = int(h.get("ww") or 0)
    n = h.get("neff") or 0
    if w >= 95:
        return ("Gewitter", "lightning-rainy")
    if w >= 85:
        return ("Schneeschauer", "snowy")
    if w >= 80:
        return ("Regenschauer", "pouring" if w >= 82 else "rainy")
    if w >= 70:
        return ("Schneefall", "snowy")
    if w in (56, 57, 66, 67, 68, 69):
        return ("gefrierender Regen" if w < 68 else "Schneeregen", "snowy-rainy")
    if w >= 61:
        return ("Regen", "pouring" if w >= 65 else "rainy")
    if w >= 51:
        return ("Sprühregen", "rainy")
    if w in (45, 49):
        return ("Nebel", "fog")
    if n < 20:
        return ("sonnig" if daylight else "klar", "sunny" if daylight else "clear-night")
    if n < 50:
        return ("heiter", "partlycloudy")
    if n < 85:
        return ("wolkig", "partlycloudy")
    return ("bedeckt", "cloudy")


def is_daylight(h: dict[str, Any]) -> bool:
    return (h.get("rad") or 0) > 1 or (h.get("sun") or 0) > 0


# ---------- Bausteine ----------

def _rh(t: float, td: float) -> float:
    return 100 * math.exp(17.625 * td / (243.04 + td)) / math.exp(17.625 * t / (243.04 + t))


def current(inp: EngineInput, S: dict[str, Any]) -> dict[str, Any]:
    h = inp.hours[0] if inp.hours else {}
    dwd = {
        "temperatur": h.get("T"),
        "feuchte": _rh(h["T"], h["Td"]) if h.get("T") is not None and h.get("Td") is not None else None,
        "wind": h.get("ff"), "boeen": h.get("fx"), "strahlung": h.get("rad"), "uv": None,
        "regenrate": h.get("rr"), "bodentemperatur": h.get("T5"), "luftdruck": h.get("p"),
    }
    out: dict[str, Any] = {}
    src: dict[str, str] = {}
    for key, d in dwd.items():
        s = inp.station.get(key)
        use_station = s is not None if S["station"]["vorrang"] == "station" else (d is None and s is not None)
        out[key] = s if use_station else d
        src[key] = "Station" if use_station else ("DWD MOSMIX" if d is not None else "–")
    # Stationen messen meist den absoluten Druck: auf Meereshöhe umrechnen.
    if src["luftdruck"] == "Station" and out["temperatur"] is not None:
        hgt = float(S["ort"]["hoehe_m"] or 0)
        t = out["temperatur"]
        out["luftdruck"] = out["luftdruck"] * (1 - 0.0065 * hgt / (t + 0.0065 * hgt + 273.15)) ** -5.257
        src["luftdruck"] = f"Station, auf Meereshöhe umgerechnet ({hgt:.0f} m)"
    out["taupunkt"] = h.get("Td")
    out["windrichtung"] = h.get("dd")
    out["bewoelkung"] = h.get("neff")
    out["src"] = src
    return out


def word_for(v: float | None, S: dict[str, Any]) -> str:
    if v is None:
        return "–"
    steps = []
    for part in str(S["gefuehlt"]["woerter"]).split(";"):
        if ":" not in part:
            continue
        x, w = part.split(":", 1)
        try:
            steps.append((float(x.strip().replace(",", ".").replace("−", "-")), w.strip()))
        except ValueError:
            continue
    steps.sort()
    for x, w in steps:
        if v < x:
            return w
    return steps[-1][1] if steps else ""


def feels_like(cur: dict[str, Any], station: dict[str, float | None], S: dict[str, Any]) -> dict[str, Any]:
    G = S["gefuehlt"]
    t, v, rh = cur["temperatur"], cur["wind"] or 0.0, cur["feuchte"] if cur["feuchte"] is not None else 50.0
    parts: list[dict[str, Any]] = []
    if t is None:
        return {"value": None, "word": "–", "parts": parts, "modell": "–"}
    m = G["modell"]
    if m == "keine":
        return {"value": t, "word": word_for(t, S), "parts": parts, "modell": "keine Korrektur"}
    if m == "station":
        s = station.get("gefuehlt_station")
        if s is None:
            return {"value": t, "word": word_for(t, S), "parts": parts, "modell": "Station (kein Sensor gewählt)"}
        return {"value": s, "word": word_for(s, S), "parts": [{"grund": "Wert der Station", "delta": s - t}], "modell": "Station"}
    auto = m == "auto"
    if auto:
        if t <= G["windchill_bis_c"] and v > 4.8 and G["wind"]:
            m = "windchill"
        elif t >= G["schwuele_ab_c"] and rh >= G["schwuele_ab_feuchte"]:
            m = "hitzeindex"
        else:
            m = "steadman"
    base = t
    if m == "windchill":
        if v > 4.8 and G["wind"]:
            wc = 13.12 + 0.6215 * t - 11.37 * v**0.16 + 0.3965 * t * v**0.16
            parts.append({"grund": "Wind", "delta": wc - t})
            base = wc
    elif m == "hitzeindex":
        f = t * 9 / 5 + 32
        hi = (-42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh - 6.83783e-3 * f * f
              - 5.481717e-2 * rh * rh + 1.22874e-3 * f * f * rh + 8.5282e-4 * f * rh * rh - 1.99e-6 * f * f * rh * rh)
        hic = (hi - 32) * 5 / 9
        parts.append({"grund": "Schwüle", "delta": hic - t})
        base = hic
    elif m == "steadman":
        e = rh / 100 * 6.105 * math.exp(17.27 * t / (237.7 + t))
        hum = 0.33 * e - 4.0
        parts.append({"grund": "Feuchte", "delta": hum})
        wnd = 0.0
        if G["wind"]:
            wnd = -0.7 * (v / 3.6)
            parts.append({"grund": "Wind", "delta": wnd})
        base = t + hum + wnd
    sun = 0.0
    if G["sonne"] and (cur["strahlung"] or 0) > 50:
        sun = 0.7 * (float(G["sonnen_faktor"]) * cur["strahlung"]) / (v / 3.6 + 10)
        parts.append({"grund": "Sonne", "delta": sun})
    names = {"windchill": "Windchill", "hitzeindex": "Hitzeindex", "steadman": "Steadman"}
    value = base + sun
    return {"value": value, "word": word_for(value, S), "parts": parts,
            "modell": ("automatisch → " if auto else "") + names[m]}


def daily(hours: list[dict[str, Any]], tz: tzinfo) -> list[dict[str, Any]]:
    groups: OrderedDict[Any, list[dict[str, Any]]] = OrderedDict()
    for h in hours:
        groups.setdefault(h["t"].astimezone(tz).date(), []).append(h)
    days = []
    for day, hs in groups.items():
        local = [(h["t"].astimezone(tz).hour, h) for h in hs]
        noon = next((h for hr, h in local if hr == 13), hs[len(hs) // 2])
        daytime = [h for hr, h in local if 8 <= hr <= 20] or hs
        worst = max(daytime, key=lambda h: h.get("ww") or 0)
        pick = worst if (worst.get("ww") or 0) >= 51 else noon
        text, cond = condition(pick, True)
        days.append({
            "date": day,
            "start": hs[0]["t"],
            "tx": _nmax((h["T"] for h in hs), None),
            "tn": _nmin(h["T"] for h in hs),
            "rr": sum(h.get("rr") or 0 for h in hs),
            "pRain": _nmax(h.get("pRain") for h in hs),
            "sunH": sum(h.get("sun") or 0 for h in hs) / 3600,
            "thunder": _nmax(h.get("thunder") for h in hs),
            "fx": _nmax(h.get("fx") for h in hs),
            "ff": _nmax(h.get("ff") for h in hs),
            "text": text,
            "condition": cond,
            "hours": len(hs),
        })
    return days


def rain_next(inp: EngineInput, S: dict[str, Any]) -> dict[str, Any]:
    if not S["quellen"]["radar"]:
        return {"aus": True, "sum": None, "text": "Radar ausgeschaltet", "steps": [], "span": ""}
    minutes = int(S["regen"]["zeitraum_min"])
    thr = float(S["regen"]["schwelle_mmh"])
    since = inp.now - timedelta(minutes=5)
    steps = [s for s in inp.radar if s["t"] >= since][: minutes // 5]
    ok = [s for s in steps if s.get("mmh") is not None]
    total = sum(s["mmh"] / 12 for s in ok)
    wet = [s for s in ok if s["mmh"] >= thr]
    span = f"{minutes // 60} h" if minutes >= 60 and minutes % 60 == 0 else f"{minutes} min"
    if minutes == 60:
        phrase = "der nächsten Stunde"
    elif minutes % 60 == 0:
        phrase = f"den nächsten {minutes // 60} Stunden"
    else:
        phrase = f"den nächsten {minutes} Minuten"
    text = f"Kein Regen in {phrase}"
    if wet:
        end = wet[-1]["t"].astimezone(inp.tz).strftime("%H:%M")
        if ok[0]["mmh"] >= thr:
            text = f"Regen jetzt, voraussichtlich bis {end} Uhr ({fmt(total)} mm)"
        else:
            text = f"Regen ab {wet[0]['t'].astimezone(inp.tz).strftime('%H:%M')} Uhr ({fmt(total)} mm)"
    ref = next((s.get("ref") for s in ok if s.get("ref")), None)
    return {"aus": False, "sum": round(total, 2) if ok else None, "text": text, "steps": steps, "span": span,
            "ref": ref, "beginn": wet[0]["t"] if wet else None, "ende": wet[-1]["t"] if wet else None}


def _official(warnings: list[dict[str, Any]], groups: list[str]) -> list[dict[str, Any]]:
    return [w for w in warnings if any(g in w["group"] for g in groups)]


def _apply_official(res: dict[str, Any], warnings: list[dict[str, Any]], groups: list[str]) -> dict[str, Any]:
    off = _official(warnings, groups)
    if off:
        # Der Tagesbericht nennt dann die amtliche Warnung statt der eigenen Einschätzung.
        res.update(stufe=max(res["stufe"], off[0]["level"]), text=off[0]["headline"], amtlich=True,
                   quelle="Amtliche DWD-Warnung", kurz=f"amtliche Warnung vor {off[0]['event']}")
    return res


def _hhmm(t: datetime | None, tz: tzinfo) -> str:
    return t.astimezone(tz).strftime("%H:%M") if t else "–"


def hint_frost(hours, warnings, station, S, tz):
    F = S["hinweise"]["frost"]
    nxt = hours[: int(F["vorlauf_h"])]
    min_t = _nmin((h["T"] for h in nxt), 99.0)
    min_t5 = _nmin((h["T5"] if h.get("T5") is not None else h["T"] for h in nxt), 99.0)
    at = next((h for h in nxt if h["T"] == min_t), None)
    glatt = F["glaette"] and any((h["T"] is not None and h["T"] <= 1) and (h.get("rr") or 0) >= 0.1 for h in nxt)
    stufe, text, kurz = 0, f"Kein Frost in den nächsten {F['vorlauf_h']} h", ""
    if min_t <= F["streng_ab_c"]:
        stufe, text, kurz = 3, f"Strenger Frost bis {fmt(min_t)} °C", "strenger Frost"
    elif min_t <= F["frost_ab_c"]:
        stufe, text, kurz = 2, f"Frost bis {fmt(min_t)} °C", "Frost"
    elif F["bodenfrost"] and min_t5 <= 0:
        stufe, text, kurz = 1, f"Bodenfrost möglich (5 cm über Boden {fmt(min_t5)} °C)", "Bodenfrost möglich"
    elif min_t <= F["frostgefahr_ab_c"]:
        stufe, text, kurz = 1, f"Frostgefahr in Bodennähe, Tiefstwert {fmt(min_t)} °C", "Frostgefahr"
    if glatt:
        stufe = max(stufe, 2)
        text += ", Glätte durch Niederschlag möglich"
        kurz = (kurz + ", " if kurz else "") + "Glättegefahr"
    soil = station.get("bodentemperatur")
    grund = f"Tiefstwert {fmt(min_t)} °C um {_hhmm(at['t'] if at else None, tz)} Uhr, 5 cm über Boden {fmt(min_t5)} °C"
    if soil is not None:
        grund += f", Boden (Station) {fmt(soil)} °C"
    res = {"key": "frost", "an": F["an"], "melden_ab": F["melden_ab"], "stufe": stufe, "text": text, "kurz": kurz,
           "grund": grund, "amtlich": False, "quelle": "DWD MOSMIX", "min_t": min_t, "min_t5": min_t5,
           "um": at["t"] if at else None}
    return _apply_official(res, warnings, ["FROST", "GLAZE"])


def hint_gewitter(hours, warnings, S):
    G = S["hinweise"]["gewitter"]
    p = _nmax(h.get("thunder") for h in hours[: int(G["vorlauf_h"])])
    stufe = 3 if p >= G["hoch_ab"] else 2 if p >= G["mittel_ab"] else 1 if p >= G["gering_ab"] else 0
    res = {"key": "gewitter", "an": G["an"], "melden_ab": G["melden_ab"], "stufe": stufe, "amtlich": False,
           "quelle": "DWD MOSMIX", "wahrscheinlichkeit": p,
           "text": f"Gewitter möglich ({fmt(p, 0)} %)" if stufe else f"Keine Gewitter erwartet (max. {fmt(p, 0)} %)",
           "grund": f"Gewitterwahrscheinlichkeit der nächsten {G['vorlauf_h']} h: max. {fmt(p, 0)} %"}
    return _apply_official(res, warnings, ["THUNDERSTORM", "HAIL", "TORNADO"])


def hint_hitze(days, warnings, S):
    H = S["hinweise"]["hitze"]
    ds = days[: int(H["tage"])]
    tx = _nmax((d["tx"] for d in ds), -99.0)
    tropen = any(d["tn"] is not None and d["tn"] >= H["tropennacht_ab"] for d in ds)
    stufe = 3 if tx >= H["extrem_ab"] else 2 if tx >= H["heiss_ab"] else 1 if (tx >= H["warm_ab"] or tropen) else 0
    res = {"key": "hitze", "an": H["an"], "melden_ab": H["melden_ab"], "stufe": stufe, "amtlich": False,
           "quelle": "DWD MOSMIX", "hoechstwert": tx, "tropennacht": tropen,
           "text": f"Hitze: bis {fmt(tx)} °C" + (", Tropennacht" if tropen else "") if stufe else f"Keine Hitze (max. {fmt(tx)} °C)",
           "grund": f"Höchstwert der nächsten {H['tage']} Tage: {fmt(tx)} °C" + (f", Nacht ≥ {H['tropennacht_ab']} °C" if tropen else "")}
    return _apply_official(res, warnings, ["HEAT"])


def hint_sturm(hours, warnings, S):
    W = S["hinweise"]["sturm"]
    fx = _nmax(h.get("fx") for h in hours[: int(W["vorlauf_h"])])
    stufe = 3 if fx >= W["orkan_ab_kmh"] else 2 if fx >= W["boeen_ab_kmh"] else 1 if fx >= W["boeen_ab_kmh"] * 0.8 else 0
    res = {"key": "sturm", "an": W["an"], "melden_ab": W["melden_ab"], "stufe": stufe, "amtlich": False,
           "quelle": "DWD MOSMIX", "boeen": fx,
           "text": f"Böen bis {fmt(fx, 0)} km/h" if stufe else f"Kein Sturm (Böen bis {fmt(fx, 0)} km/h)",
           "grund": f"Stärkste Böe der nächsten {W['vorlauf_h']} h: {fmt(fx, 0)} km/h"}
    return _apply_official(res, warnings, ["WIND"])


def hint_starkregen(hours, warnings, S):
    R = S["hinweise"]["starkregen"]
    rr = _nmax(h.get("rr") for h in hours[: int(R["vorlauf_h"])])
    ab = float(R["ab_mm_pro_h"])
    stufe = 3 if rr >= ab * 2 else 2 if rr >= ab else 1 if rr >= ab / 2 else 0
    res = {"key": "starkregen", "an": R["an"], "melden_ab": R["melden_ab"], "stufe": stufe, "amtlich": False,
           "quelle": "DWD MOSMIX", "max_mm_h": rr,
           "text": f"Starkregen bis {fmt(rr)} mm/h" if stufe else f"Kein Starkregen (max. {fmt(rr)} mm/h)",
           "grund": f"Stärkste Stunde der nächsten {R['vorlauf_h']} h: {fmt(rr)} mm"}
    return _apply_official(res, warnings, ["RAIN"])


def pollen_now(regions: list[dict[str, Any]], S: dict[str, Any]) -> dict[str, Any]:
    if not regions:
        return {"region": None, "arten": [], "belastet": [], "tag": P_TAG.get(S["pollen"]["tag"], "")}
    rid = int(S["quellen"]["pollen_region"] or 0)
    reg = next((r for r in regions if r["id"] == rid), regions[0])
    day = S["pollen"]["tag"]
    arten = [{"id": p, "name": P_NAME.get(p, p), "wert": reg["pollen"].get(p, {}).get(day, "0")} for p in S["pollen"]["arten"]]
    for a in arten:
        a["label"] = P_LABEL.get(a["wert"], a["wert"])
        a["index"] = P_ORDER.index(a["wert"]) / 2 if a["wert"] in P_ORDER else 0
    ab = P_ORDER.index(S["pollen"]["belastung_ab"]) if S["pollen"]["belastung_ab"] in P_ORDER else 2
    belastet = sorted((a for a in arten if a["wert"] in P_ORDER and P_ORDER.index(a["wert"]) >= ab),
                      key=lambda a: -P_ORDER.index(a["wert"]))
    return {"region": reg["name"], "region_id": reg["id"], "arten": arten, "belastet": belastet, "tag": P_TAG.get(day, day)}


def bericht(r: dict[str, Any], S: dict[str, Any], tz: tzinfo) -> str:
    B = S["bericht"]
    lang = B["stil"] == "ausfuehrlich"
    hours = r["hours"]
    if not hours:
        return ""
    loc = [(h["t"].astimezone(tz), h) for h in hours]
    d0 = loc[0][0].date()
    now_h = loc[0][0].hour

    def warnung():
        return f"Amtliche Warnung: {r['warnings'][0]['headline']}." if r["warnings"] else ""

    def heute():
        rest = [h for lt, h in loc if lt.date() == d0 and lt.hour <= B["tag_bis_uhr"]]
        if not rest:
            return ""
        tx = _nmax((h["T"] for h in rest), None)
        rain = [(lt, h) for lt, h in loc if lt.date() == d0 and lt.hour <= B["tag_bis_uhr"] and (h.get("rr") or 0) >= 0.1]
        cond = condition(rest[len(rest) // 2], True)[0]
        s = f"{'Heute' if now_h < 12 else 'Am Nachmittag'} {cond}, bis {fmt(tx, 0)} °C"
        if rain:
            s += f", Regen zwischen {rain[0][0].hour} und {rain[-1][0].hour + 1} Uhr ({fmt(sum(h['rr'] for _, h in rain))} mm)"
        else:
            s += ", trocken"
        if lang:
            sun = sum(h.get("sun") or 0 for h in rest) / 3600
            pr = _nmax(h.get("pRain") for h in rest)
            s += f", {fmt(sun)} Sonnenstunden, Regenrisiko {fmt(pr, 0)} %"
        return s + "."

    def nacht():
        night = [h for lt, h in loc if (lt.date() == d0 and lt.hour >= B["nacht_von_uhr"])
                 or (lt.date() == d0 + timedelta(days=1) and lt.hour <= B["nacht_bis_uhr"])][:24]
        if not night:
            return ""
        tn = _nmin(h["T"] for h in night)
        rain = sum(h.get("rr") or 0 for h in night)
        s = "In der Nacht " + (f"zeitweise Regen ({fmt(rain)} mm), " if rain >= 0.3 else "")
        if lang:
            s += condition(night[len(night) // 2], False)[0] + ", "
        s += f"Abkühlung auf {fmt(tn, 0)} °C"
        frost = r["hints"]["frost"]
        if frost["an"] and frost["stufe"] and frost.get("kurz"):
            s += f", {frost['kurz']}"
        return s + "."

    def wind():
        nxt = hours[:24]
        fx, ff = _nmax(h.get("fx") for h in nxt), _nmax(h.get("ff") for h in nxt)
        if not lang and fx < S["hinweise"]["sturm"]["boeen_ab_kmh"] * 0.8:
            return ""
        return f"Wind bis {fmt(ff, 0)} km/h, Böen bis {fmt(fx, 0)} km/h."

    def morgen():
        m = next((d for d in r["days"] if d["date"] == d0 + timedelta(days=1)), None)
        if not m:
            return ""
        s = f"Morgen {m['text']}, {fmt(m['tn'], 0)} bis {fmt(m['tx'], 0)} °C"
        if m["rr"] >= 0.5:
            s += f", {fmt(m['rr'])} mm Regen"
        if m["sunH"] >= 1 or lang:
            s += f", {fmt(m['sunH'], 0)} Sonnenstunden"
        return s + "."

    def pollen():
        p = r["pollen"]
        if not p["arten"]:
            return ""
        if not p["belastet"]:
            return f"Kaum Pollenflug ({p['tag']})."
        return f"Pollen {p['tag']}: " + ", ".join(f"{a['name']} {a['label']}" for a in p["belastet"][:3]) + "."

    parts = {"warnung": warnung, "heute": heute, "nacht": nacht, "wind": wind, "morgen": morgen, "pollen": pollen}
    texts = [parts[b["id"]]() for b in B["bausteine"] if b.get("an") and b.get("id") in parts]
    return " ".join(t for t in texts if t)


# ---------- Gesamtrechnung ----------

def compute(inp: EngineInput, S: dict[str, Any]) -> dict[str, Any]:
    """Alle Ergebnisse berechnen. S muss vollständig sein (defaults.merge_settings)."""
    hours = [h for h in inp.hours if h["t"] > inp.now - timedelta(hours=1)]
    inp_now = EngineInput(**{**inp.__dict__, "hours": hours})
    days = daily(hours, inp.tz)
    warnings = ([w for w in inp.warnings if w["level"] >= int(S["warnungen"]["mindeststufe"])]
                if S["warnungen"]["anzeigen"] else [])
    cur = current(inp_now, S)
    r: dict[str, Any] = {"hours": hours, "days": days, "warnings": warnings, "cur": cur}
    r["feel"] = feels_like(cur, inp.station, S)
    r["rain"] = rain_next(inp, S)
    r["hints"] = {
        "frost": hint_frost(hours, warnings, inp.station, S, inp.tz),
        "gewitter": hint_gewitter(hours, warnings, S),
        "hitze": hint_hitze(days, warnings, S),
        "sturm": hint_sturm(hours, warnings, S),
        "starkregen": hint_starkregen(hours, warnings, S),
    }
    for h in r["hints"].values():
        h["aktiv"] = bool(h["an"]) and h["stufe"] >= int(h["melden_ab"])
    r["pollen"] = pollen_now(inp.pollen_regions, S)
    r["regen_6h"] = round(sum(h.get("rr") or 0 for h in hours[:6]), 1)
    r["regen_24h"] = round(sum(h.get("rr") or 0 for h in hours[:24]), 1)
    d0 = hours[0]["t"].astimezone(inp.tz).date() if hours else None
    r["morgen"] = next((d for d in days if d0 and d["date"] == d0 + timedelta(days=1)), None)
    r["condition"] = condition(hours[0], is_daylight(hours[0])) if hours else ("unbekannt", "exceptional")
    r["bericht"] = bericht(r, S, inp.tz)
    return r
