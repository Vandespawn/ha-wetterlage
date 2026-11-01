"""Standardeinstellungen der Integration.

Alles hier ist über die Optionen änderbar. Ohne Home-Assistant-Importe, damit es testbar bleibt.
"""

from __future__ import annotations

import copy
from typing import Any

POLLEN_ARTEN = ["Hasel", "Erle", "Esche", "Birke", "Graeser", "Roggen", "Beifuss", "Ambrosia"]

DEFAULT_SETTINGS: dict[str, Any] = {
    "ort": {
        "name": "",
        "hoehe_m": 0,
        # Koordinaten für Abfragen beim DWD runden (Datenschutz). 4 = nicht runden.
        "koordinaten_runden": 2,
    },
    "quellen": {
        "mosmix_station": "auto",
        "warngebiet": "auto",
        "pollen_region": 0,
        "radar": True,
        "intervall_vorhersage_min": 60,
        "intervall_warnungen_min": 5,
        "intervall_radar_min": 5,
        "intervall_pollen_min": 360,
    },
    "station": {
        "vorrang": "station",
        "temperatur": "",
        "feuchte": "",
        "wind": "",
        "boeen": "",
        "strahlung": "",
        "uv": "",
        "regenrate": "",
        "regen_woche": "",
        "bodentemperatur": "",
        "luftdruck": "",
        "gefuehlt_station": "",
    },
    "gefuehlt": {
        "modell": "auto",
        "wind": True,
        "sonne": True,
        "sonnen_faktor": 0.1,
        "windchill_bis_c": 10,
        "schwuele_ab_c": 27,
        "schwuele_ab_feuchte": 40,
        "woerter": "-10:sehr kalt; 0:frostig; 8:kalt; 14:kühl; 20:angenehm; 26:warm; 32:heiß; 99:sehr heiß",
    },
    "regen": {"zeitraum_min": 60, "schwelle_mmh": 0.1},
    "hinweise": {
        "frost": {"an": True, "melden_ab": 1, "vorlauf_h": 24, "frost_ab_c": 0, "streng_ab_c": -10,
                  "frostgefahr_ab_c": 3, "bodenfrost": True, "glaette": True},
        "gewitter": {"an": True, "melden_ab": 1, "vorlauf_h": 12, "gering_ab": 10, "mittel_ab": 25, "hoch_ab": 50},
        "hitze": {"an": True, "melden_ab": 1, "tage": 3, "warm_ab": 27, "heiss_ab": 30, "extrem_ab": 35,
                  "tropennacht_ab": 20},
        "sturm": {"an": True, "melden_ab": 2, "vorlauf_h": 24, "boeen_ab_kmh": 60, "orkan_ab_kmh": 100},
        "starkregen": {"an": True, "melden_ab": 2, "vorlauf_h": 24, "ab_mm_pro_h": 10},
    },
    "warnungen": {"anzeigen": True, "mindeststufe": 1, "beschreibung": True, "verhaltenshinweise": False},
    "pollen": {"arten": list(POLLEN_ARTEN), "tag": "today", "belastung_ab": "1"},
    "bericht": {
        "bausteine": [
            {"id": "warnung", "an": True},
            {"id": "heute", "an": True},
            {"id": "nacht", "an": True},
            {"id": "wind", "an": True},
            {"id": "morgen", "an": True},
            {"id": "pollen", "an": False},
        ],
        "stil": "kurz",
        "tag_bis_uhr": 18,
        "nacht_von_uhr": 20,
        "nacht_bis_uhr": 7,
    },
    "karte": {
        "abschnitte": [
            {"id": "kopf", "an": True},
            {"id": "warnungen", "an": True},
            {"id": "hinweise", "an": True},
            {"id": "regen", "an": True},
            {"id": "bericht", "an": True},
            {"id": "tage", "an": True},
            {"id": "pollen", "an": True},
        ],
        "tage": 7,
        "dezimalstellen": 1,
        "design": "auto",
        "symbole": "emoji",
        "farbe_stufe_0": "#2e9e5b",
        "farbe_stufe_1": "#d6b400",
        "farbe_stufe_2": "#f08a00",
        "farbe_stufe_3": "#e0362c",
        "farbe_stufe_4": "#8e24aa",
        "farbe_regen": "#2f80ed",
        "eckenradius_px": 16,
    },
    "entitaeten": {
        "praefix": "wetterlage",
        "gefuehlte_temperatur": True,
        "regen_naechste_stunde": True,
        "regen_6_stunden": True,
        "regen_24_stunden": True,
        "frost": True,
        "gewitter": True,
        "hitze": True,
        "sturm": True,
        "starkregen": True,
        "amtliche_warnung": True,
        "pollen_hoechste": True,
        "pollen_einzeln": True,
        "tiefstwert_nacht": True,
        "hoechstwert_morgen": True,
        "sonnenstunden_morgen": True,
        "regen_7_tage": True,
        "luftdruck": True,
        "tagesbericht": True,
        "wetter": True,
    },
    "ereignisse": {"warnungs_ereignis": True, "hinweis_ereignis": True},
}


def merge_settings(user: dict[str, Any] | None, defaults: dict[str, Any] = DEFAULT_SETTINGS) -> dict[str, Any]:
    """Gespeicherte Einstellungen mit den Standardwerten ergänzen.

    Unbekannte Schlüssel fallen weg, fehlende kommen aus den Standardwerten.
    Listen werden als Ganzes übernommen.
    """
    out: dict[str, Any] = {}
    user = user if isinstance(user, dict) else {}
    for key, default in defaults.items():
        value = user.get(key)
        if isinstance(default, dict):
            out[key] = merge_settings(value, default)
        elif isinstance(default, list):
            out[key] = copy.deepcopy(value) if isinstance(value, list) else copy.deepcopy(default)
        elif value is None:
            out[key] = default
        elif isinstance(default, bool):
            out[key] = bool(value)
        elif isinstance(default, (int, float)) and not isinstance(value, bool):
            try:
                out[key] = type(default)(value) if isinstance(default, int) and float(value).is_integer() else float(value)
            except (TypeError, ValueError):
                out[key] = default
        else:
            out[key] = value
    return out
