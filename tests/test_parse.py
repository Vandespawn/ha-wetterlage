"""Einlesen der DWD-Formate."""

from __future__ import annotations

import io
import zipfile

from conftest import parse

KML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<kml:kml xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd" xmlns:kml="http://www.opengis.net/kml/2.2">
<kml:Document><kml:ExtendedData><dwd:ProductDefinition><dwd:IssueTime>2026-11-01T09:00:00.000Z</dwd:IssueTime>
<dwd:ForecastTimeSteps><dwd:TimeStep>2026-11-01T10:00:00.000Z</dwd:TimeStep><dwd:TimeStep>2026-11-01T11:00:00.000Z</dwd:TimeStep></dwd:ForecastTimeSteps>
</dwd:ProductDefinition></kml:ExtendedData>
<kml:Placemark><kml:name>10637</kml:name><kml:description>FRANKFURT/MAIN</kml:description><kml:ExtendedData>
<dwd:Forecast dwd:elementName="TTT"><dwd:value>     281.15     282.15</dwd:value></dwd:Forecast>
<dwd:Forecast dwd:elementName="FF"><dwd:value>       2.00          -</dwd:value></dwd:Forecast>
<dwd:Forecast dwd:elementName="PPPP"><dwd:value>  101800.00  101750.00</dwd:value></dwd:Forecast>
</kml:ExtendedData></kml:Placemark></kml:Document></kml:kml>"""


def _kmz() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MOSMIX_L_2026110109_10637.kml", KML.encode("latin-1"))
    return buf.getvalue()


def test_mosmix_kmz():
    m = parse.parse_mosmix_kmz(_kmz())
    assert m["name"] == "FRANKFURT/MAIN"
    assert m["issue"].isoformat() == "2026-11-01T09:00:00+00:00"
    assert len(m["hours"]) == 2
    h0, h1 = m["hours"]
    assert h0["T"] == 8.0 and h1["T"] == 9.0  # Kelvin -> °C
    assert h0["ff"] == 7.2 and h1["ff"] is None  # m/s -> km/h, "-" = fehlt
    assert h0["p"] == 1018.0  # Pa -> hPa
    assert h0["rr"] is None  # Element nicht in der Datei


def test_stationskatalog_grad_minuten():
    text = ("ID    ICAO NAME                 LAT    LON     ELEV\n"
            "----- ---- -------------------- -----  ------- -----\n"
            "10637 EDDF FRANKFURT/MAIN        50.03    8.35   112\n"
            "10865 EDDM MUENCHEN/FLUGHAFEN    48.21   11.47   446\n")
    st = parse.parse_station_catalog(text)
    assert st[0]["id"] == "10637"
    assert abs(st[0]["lat"] - (50 + 3 / 60)) < 1e-9
    near = parse.nearest_stations(st, 50.1109, 8.6821, 1)
    assert near[0]["id"] == "10637" and near[0]["km"] < 15


def _w(group, onset, level="Minor", ident=None):
    return {"IDENTIFIER": ident or f"{group}-{onset}", "EVENT": group, "HEADLINE": f"Amtliche WARNUNG vor {group}",
            "SEVERITY": level, "EC_GROUP": group, "ONSET": onset, "EXPIRES": None}


def test_warnungen_gemeinde_vor_kreis():
    gem = [_w("FROST", "2026-11-01T23:00:00Z", ident="g1")]
    kreis = [_w("FROST", "2026-11-01T23:00:00Z", ident="k1"), _w("HEAT", "2026-11-02T10:00:00Z", "Moderate", "k2")]
    out = parse.merge_warnings(gem, kreis)
    assert [w["id"] for w in out] == ["k2", "g1"]  # höchste Stufe zuerst, Frost nur einmal
    assert out[0]["level"] == 2 and out[0]["gebiet"] == "Kreis"


def test_pollenregion_aus_warncell():
    assert parse.pollen_region_for_warncell(809162000) == 120  # Bayern
    assert parse.pollen_region_for_warncell(811000000) == 50  # Berlin
    assert parse.pollen_region_for_warncell(None) is None


def test_pollen_regionen():
    data = {"last_update": "2026-11-01 11:00 Uhr", "content": [
        {"region_id": 20, "region_name": "Mecklenburg-Vorpommern", "partregion_id": -1, "partregion_name": "", "Pollen": {}},
        {"region_id": 120, "region_name": "Bayern", "partregion_id": 121, "partregion_name": "Allgäu/Oberbayern/Bay. Wald", "Pollen": {}},
    ]}
    p = parse.parse_pollen(data)
    assert [(r["id"], r["name"]) for r in p["regions"]] == [(20, "Mecklenburg-Vorpommern"), (121, "Allgäu/Oberbayern/Bay. Wald")]
