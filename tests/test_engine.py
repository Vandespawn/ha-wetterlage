"""Rechenkern: jede Einstellung muss das Ergebnis wie erwartet verändern."""

from __future__ import annotations

from datetime import timedelta

from conftest import NOW, TZ, defaults, engine, make_hours


def test_ruhige_lage(inp, settings):
    r = engine.compute(inp, settings)
    assert r["warnings"] == []
    assert r["hints"]["gewitter"]["stufe"] == 0
    assert r["hints"]["hitze"]["stufe"] == 0
    assert r["rain"]["text"].startswith("Radar") or r["rain"]["sum"] in (None, 0)
    assert r["bericht"]  # Tagesbericht ist nicht leer
    assert "°C" in r["bericht"]


def test_bodenfrost_und_schwellen(inp, settings):
    # Tiefstwert 1 °C, 5 cm über Boden -0,1 °C -> Bodenfrost möglich (Stufe 1)
    r = engine.compute(inp, settings)
    assert r["hints"]["frost"]["stufe"] == 1
    assert r["hints"]["frost"]["aktiv"] is True
    # Bodenfrost aus, Frostgefahr erst unter 0,5 °C -> kein Hinweis
    settings["hinweise"]["frost"]["bodenfrost"] = False
    settings["hinweise"]["frost"]["frostgefahr_ab_c"] = 0.5
    r = engine.compute(inp, settings)
    assert r["hints"]["frost"]["stufe"] == 0
    # Frost ab 2 °C -> Stufe 2
    settings["hinweise"]["frost"]["frost_ab_c"] = 2
    assert engine.compute(inp, settings)["hints"]["frost"]["stufe"] == 2


def test_melden_ab_und_abschalten(inp, settings):
    settings["hinweise"]["frost"]["melden_ab"] = 2
    assert engine.compute(inp, settings)["hints"]["frost"]["aktiv"] is False
    settings["hinweise"]["frost"]["melden_ab"] = 1
    settings["hinweise"]["frost"]["an"] = False
    assert engine.compute(inp, settings)["hints"]["frost"]["aktiv"] is False


def test_amtliche_warnung_hat_vorrang(inp, settings):
    inp.warnings = [{"id": "x", "event": "FROST", "headline": "Amtliche WARNUNG vor FROST", "description": "",
                     "instruction": "", "level": 1, "group": "FROST", "onset": "2026-11-01T23:00:00Z",
                     "expires": "2026-11-02T07:00:00Z", "gebiet": "Kreis"}]
    settings["hinweise"]["frost"]["bodenfrost"] = False
    settings["hinweise"]["frost"]["frostgefahr_ab_c"] = 0
    r = engine.compute(inp, settings)
    frost = r["hints"]["frost"]
    assert frost["amtlich"] is True
    assert frost["text"] == "Amtliche WARNUNG vor FROST"  # Wortlaut unverändert
    assert frost["stufe"] == 1
    assert r["bericht"].startswith("Amtliche Warnung: Amtliche WARNUNG vor FROST.")
    assert "amtliche Warnung vor FROST" in r["bericht"]  # Nacht-Baustein folgt der Warnung
    # Mindeststufe 2 blendet die Warnung aus
    settings["warnungen"]["mindeststufe"] = 2
    r = engine.compute(inp, settings)
    assert r["warnings"] == [] and r["hints"]["frost"]["amtlich"] is False


def test_gefuehlte_temperatur_modelle(inp, settings):
    inp.station = {"temperatur": 8.7, "feuchte": 70.0, "wind": 6.8, "strahlung": 241.0, "gefuehlt_station": 7.8}
    r = engine.compute(inp, settings)
    assert r["feel"]["modell"] == "automatisch → Windchill"
    assert round(r["feel"]["value"], 1) == 9.2  # Wind -0,9, Sonne +1,4
    settings["gefuehlt"]["sonne"] = False
    assert round(engine.compute(inp, settings)["feel"]["value"], 1) == 7.8
    settings["gefuehlt"]["modell"] = "station"
    assert engine.compute(inp, settings)["feel"]["value"] == 7.8
    settings["gefuehlt"]["modell"] = "keine"
    assert engine.compute(inp, settings)["feel"]["value"] == 8.7
    settings["gefuehlt"]["woerter"] = "5:eisig; 99:mild"
    assert engine.compute(inp, settings)["feel"]["word"] == "mild"


def test_vorrang_station_oder_dwd(inp, settings):
    inp.station = {"temperatur": 12.0}
    assert engine.compute(inp, settings)["cur"]["temperatur"] == 12.0
    settings["station"]["vorrang"] = "dwd"
    r = engine.compute(inp, settings)
    assert r["cur"]["temperatur"] != 12.0
    assert r["cur"]["src"]["temperatur"] == "DWD MOSMIX"


def test_luftdruck_auf_meereshoehe(inp, settings):
    inp.station = {"temperatur": 8.7, "luftdruck": 977.3}
    settings["ort"]["hoehe_m"] = 420
    p = engine.compute(inp, settings)["cur"]["luftdruck"]
    assert 1025 < p < 1030


def test_gewitter_schwellen(settings):
    hours = make_hours(thunder=lambda i, h: 30.0 if i == 3 else 0.0)
    inp = engine.EngineInput(now=NOW, tz=TZ, hours=hours)
    assert engine.compute(inp, settings)["hints"]["gewitter"]["stufe"] == 2
    settings["hinweise"]["gewitter"]["mittel_ab"] = 40
    assert engine.compute(inp, settings)["hints"]["gewitter"]["stufe"] == 1
    settings["hinweise"]["gewitter"]["vorlauf_h"] = 2
    assert engine.compute(inp, settings)["hints"]["gewitter"]["stufe"] == 0


def test_hitze_und_tropennacht(settings):
    hours = make_hours(T=lambda i, h: h["T"] + 25)  # 26 bis 33 °C
    inp = engine.EngineInput(now=NOW, tz=TZ, hours=hours)
    h = engine.compute(inp, settings)["hints"]["hitze"]
    assert h["stufe"] == 2 and h["tropennacht"] is True
    settings["hinweise"]["hitze"]["heiss_ab"] = 34
    assert engine.compute(inp, settings)["hints"]["hitze"]["stufe"] == 1


def test_regen_naechste_stunde(inp, settings):
    inp.radar = [{"t": NOW + timedelta(minutes=5 * k), "mmh": 0.0 if k < 4 else 1.2, "ref": "x"} for k in range(25)]
    r = engine.compute(inp, settings)
    assert r["rain"]["text"].startswith("Regen ab")
    assert len(r["rain"]["steps"]) == 12
    settings["regen"]["zeitraum_min"] = 30
    assert len(engine.compute(inp, settings)["rain"]["steps"]) == 6
    settings["regen"]["schwelle_mmh"] = 2
    assert engine.compute(inp, settings)["rain"]["text"] == "Kein Regen in den nächsten 30 Minuten"
    settings["regen"]["zeitraum_min"] = 60
    assert engine.compute(inp, settings)["rain"]["text"] == "Kein Regen in der nächsten Stunde"
    settings["quellen"]["radar"] = False
    assert engine.compute(inp, settings)["rain"]["aus"] is True


def test_pollen(inp, settings):
    inp.pollen_regions = [{"id": 121, "region_id": 120, "bundesland": "Bayern", "name": "Bay. Wald",
                           "pollen": {"Birke": {"today": "2", "tomorrow": "1"}, "Hasel": {"today": "0-1"}}}]
    settings["quellen"]["pollen_region"] = 121
    p = engine.compute(inp, settings)["pollen"]
    assert [a["name"] for a in p["belastet"]] == ["Birke"]
    settings["pollen"]["arten"] = ["Hasel"]
    assert engine.compute(inp, settings)["pollen"]["belastet"] == []
    settings["pollen"]["belastung_ab"] = "0-1"
    assert [a["name"] for a in engine.compute(inp, settings)["pollen"]["belastet"]] == ["Hasel"]


def test_bericht_bausteine_und_reihenfolge(inp, settings):
    B = settings["bericht"]
    B["bausteine"] = [{"id": "morgen", "an": True}, {"id": "heute", "an": True}]
    text = engine.compute(inp, settings)["bericht"]
    assert text.startswith("Morgen")
    B["bausteine"] = [{"id": "heute", "an": False}, {"id": "morgen", "an": False}]
    assert engine.compute(inp, settings)["bericht"] == ""
    B["bausteine"] = [{"id": "heute", "an": True}]
    B["stil"] = "ausfuehrlich"
    assert "Sonnenstunden" in engine.compute(inp, settings)["bericht"]


def test_fmt_ohne_minus_null():
    assert engine.fmt(-0.04) == "0,0"
    assert engine.fmt(-0.4, 0) == "0"
    assert engine.fmt(None) == "–"


def test_merge_settings_ergaenzt_und_wandelt():
    s = defaults.merge_settings({"regen": {"zeitraum_min": "30"}, "unbekannt": 1, "hinweise": {"frost": {"an": 0}}})
    assert s["regen"]["zeitraum_min"] == 30
    assert s["regen"]["schwelle_mmh"] == 0.1
    assert s["hinweise"]["frost"]["an"] is False
    assert "unbekannt" not in s
