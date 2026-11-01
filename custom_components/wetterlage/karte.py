"""Daten für die Dashboard-Karte: ein JSON-taugliches Abbild des Rechenergebnisses."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .const import ATTRIBUTION, CONF_GEMEINDE_NAME

HINT_LABEL = {"frost": "Frost", "gewitter": "Gewitter", "hitze": "Hitze", "sturm": "Sturm", "starkregen": "Starkregen"}
WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _r(v: float | None, d: int = 2) -> float | None:
    return None if v is None else round(v, d)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def karte_payload(coordinator: Any, today: date | None = None) -> dict[str, Any]:
    r = coordinator.data
    S = coordinator.settings
    entry = coordinator.config_entry
    if r is None:
        return {"bereit": False}
    gemeinde = entry.data.get(CONF_GEMEINDE_NAME) or ""
    cur = r["cur"]
    days = r["days"]
    first = days[0]["date"] if days else today
    return {
        "bereit": True,
        "titel": S["ort"]["name"] or gemeinde.replace("Gemeinde ", "").replace("Stadt ", "") or entry.title,
        "warngebiet": gemeinde,
        "karte": S["karte"],
        "warnungen_anzeigen": S["warnungen"]["anzeigen"],
        "mindeststufe": S["warnungen"]["mindeststufe"],
        "jetzt": {
            "zustand": r["condition"][0], "zustand_ha": r["condition"][1],
            "temperatur": _r(cur["temperatur"], 1), "feuchte": _r(cur["feuchte"], 0),
            "wind": _r(cur["wind"], 0), "boeen": _r(cur["boeen"], 0), "quelle": cur["src"]["temperatur"],
        },
        "gefuehlt": {
            "wert": _r(r["feel"]["value"], 1), "wort": r["feel"]["word"], "modell": r["feel"]["modell"],
            "anteile": [{"grund": p["grund"], "delta": round(p["delta"], 2)} for p in r["feel"]["parts"]],
        },
        "warnungen": [{
            "ueberschrift": w["headline"], "stufe": w["level"], "ereignis": w["event"],
            "beschreibung": w["description"] if S["warnungen"]["beschreibung"] else None,
            "verhaltenshinweise": w["instruction"] if S["warnungen"]["verhaltenshinweise"] else None,
            "beginn": w["onset"], "ende": w["expires"],
        } for w in r["warnings"]],
        "hinweise": [{
            "id": k, "label": HINT_LABEL[k], "stufe": h["stufe"], "text": h["text"],
            "amtlich": h["amtlich"], "an": h["an"], "aktiv": h["aktiv"],
        } for k, h in r["hints"].items()],
        "regen": {
            "aus": r["rain"]["aus"], "text": r["rain"]["text"], "span": r["rain"]["span"], "summe": r["rain"]["sum"],
            "schritte": [{"t": _iso(s["t"]), "mmh": s["mmh"]} for s in r["rain"]["steps"]],
        },
        "bericht": r["bericht"],
        "tage": [{
            "name": "Heute" if d["date"] == first else WOCHENTAG[d["date"].weekday()],
            "datum": d["date"].isoformat(), "tx": _r(d["tx"], 1), "tn": _r(d["tn"], 1), "regen": _r(d["rr"], 1),
            "sonne_h": _r(d["sunH"], 1), "zustand": d["text"], "zustand_ha": d["condition"],
        } for d in days],
        "pollen": {
            "region": r["pollen"]["region"], "tag": r["pollen"]["tag"],
            "arten": [{"name": a["name"], "wert": a["wert"], "label": a["label"], "index": a["index"]} for a in r["pollen"]["arten"]],
        },
        "quelle": ATTRIBUTION,
    }
