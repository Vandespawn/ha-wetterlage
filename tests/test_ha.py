"""Tests gegen ein echtes Home Assistant (laufen in GitHub Actions unter Linux).

Lokal ohne pytest-homeassistant-custom-component werden sie übersprungen.
In GitHub Actions ist WETTERLAGE_HA_TESTS gesetzt: Dort schlägt ein fehlendes Paket fehl,
statt die Tests still zu überspringen.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

if not os.environ.get("WETTERLAGE_HA_TESTS"):
    pytest.importorskip("pytest_homeassistant_custom_component")

from conftest import NOW, make_hours  # noqa: E402
from homeassistant import config_entries  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.wetterlage.const import DOMAIN, EVENT_WARNUNG  # noqa: E402
from custom_components.wetterlage.defaults import merge_settings  # noqa: E402

CLIENT = "custom_components.wetterlage.dwd.DwdClient"
STATIONS = [{"id": "10865", "name": "MUENCHEN/FLUGHAFEN", "lat": 48.35, "lon": 11.78, "elev": 446, "km": 28.0}]
CELLS = {"gemeinde_id": 809162000, "gemeinde_name": "Stadt München", "kreis_id": 909162999, "kreis_name": "Stadt München"}
POLLEN = {"update": "2026-11-01 11:00 Uhr", "regions": [
    {"id": 20, "region_id": 20, "bundesland": "Mecklenburg-Vorpommern", "name": "Mecklenburg-Vorpommern", "pollen": {}},
    {"id": 121, "region_id": 120, "bundesland": "Bayern", "name": "Allgäu/Oberbayern/Bay. Wald",
     "pollen": {"Birke": {"today": "2", "tomorrow": "1", "dayafter_to": "0"}}},
]}
FROST = {"id": "w1", "event": "FROST", "headline": "Amtliche WARNUNG vor FROST", "description": "Es tritt Frost auf.",
         "instruction": "", "level": 1, "group": "FROST", "onset": "2026-11-01T23:00:00Z", "expires": "2026-11-02T07:00:00Z",
         "gebiet": "Kreis"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def dwd():
    mosmix = {"issue": NOW, "name": "MUENCHEN/FLUGHAFEN", "hours": make_hours()}
    with (
        patch(f"{CLIENT}.nearest_stations", AsyncMock(return_value=STATIONS)),
        patch(f"{CLIENT}.warncells", AsyncMock(return_value=CELLS)),
        patch(f"{CLIENT}.mosmix", AsyncMock(return_value=mosmix)),
        patch(f"{CLIENT}.pollen", AsyncMock(return_value=POLLEN)),
        patch(f"{CLIENT}.warnings", AsyncMock(return_value=[])) as warnings,
        patch(f"{CLIENT}.radar", AsyncMock(return_value=[])),
    ):
        yield {"warnings": warnings}


def _entry(settings: dict | None = None) -> MockConfigEntry:
    s = merge_settings(settings or {})
    s["quellen"]["pollen_region"] = 121
    return MockConfigEntry(
        domain=DOMAIN, title="Zuhause", unique_id="48.14_11.58",
        data={"name": "Zuhause", "lat": 48.1372, "lon": 11.5755, "station_id": "10865", "station_name": "MUENCHEN/FLUGHAFEN (28.0 km)",
              **CELLS},
        options={"settings": s},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_einrichtung(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    hass.config.latitude, hass.config.longitude = 48.1372, 11.5755
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Zuhause", "ort": {"latitude": 48.1372, "longitude": 11.5755}})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "pollen"
    assert result["data_schema"].schema["pollen_region"].config["options"][0]["value"] == "121"  # Bayern zuerst
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pollen_region": "121"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["station_id"] == "10865" and result["data"]["kreis_id"] == 909162999
    assert result["options"]["settings"]["quellen"]["pollen_region"] == 121


async def test_entitaeten(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, _entry())
    feel = hass.states.get("sensor.wetterlage_gefuehlte_temperatur")
    assert feel is not None and float(feel.state) < 10
    assert "Deutscher Wetterdienst" in feel.attributes["attribution"]
    frost = hass.states.get("binary_sensor.wetterlage_frost")
    assert frost.state == "on" and frost.attributes["amtlich"] is False
    assert hass.states.get("weather.wetterlage_wetter") is not None
    assert hass.states.get("sensor.wetterlage_pollen_birke").state == "2.0"
    assert hass.states.get("sensor.wetterlage_amtliche_warnung").state == "0"
    assert hass.states.get("sensor.wetterlage_tagesbericht").attributes["text"]


async def test_entitaeten_abschaltbar(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, _entry({"entitaeten": {"tagesbericht": False, "pollen_einzeln": False, "praefix": "meinwetter"}}))
    assert hass.states.get("sensor.meinwetter_tagesbericht") is None
    assert hass.states.get("sensor.meinwetter_pollen_birke") is None
    assert hass.states.get("sensor.meinwetter_gefuehlte_temperatur") is not None


async def test_wetterstation(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    hass.states.async_set("sensor.aussen", "12.5")
    await _setup(hass, _entry({"station": {"temperatur": "sensor.aussen"}, "gefuehlt": {"modell": "keine"}}))
    assert float(hass.states.get("sensor.wetterlage_gefuehlte_temperatur").state) == 12.5


async def test_optionen_alle_einstellungen(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    entry = _entry()
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "alle"})
    new = merge_settings(entry.options["settings"])
    new["hinweise"]["frost"]["melden_ab"] = 3
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"einstellungen": new})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.wetterlage_frost").state == "off"


async def test_warnungs_ereignis(hass: HomeAssistant, dwd, freezer) -> None:
    freezer.move_to(NOW)
    entry = _entry()
    await _setup(hass, entry)
    events = []
    hass.bus.async_listen(EVENT_WARNUNG, events.append)
    dwd["warnings"].return_value = [FROST]
    freezer.tick(600)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [e.data["typ"] for e in events] == ["beginn"]
    assert hass.states.get("sensor.wetterlage_amtliche_warnung").state == "1"
    assert hass.states.get("binary_sensor.wetterlage_frost").attributes["amtlich"] is True


async def test_karte_websocket(hass: HomeAssistant, dwd, freezer, hass_ws_client) -> None:
    freezer.move_to(NOW)
    await _setup(hass, _entry({"karte": {"tage": 4}}))
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "wetterlage/eintraege"})
    msg = await client.receive_json()
    assert msg["success"] and msg["result"][0]["title"] == "Zuhause"
    await client.send_json({"id": 2, "type": "wetterlage/karte/abonnieren"})
    assert (await client.receive_json())["success"]
    event = (await client.receive_json())["event"]
    assert event["bereit"] is True
    assert event["titel"] == "München"
    assert event["karte"]["tage"] == 4
    assert event["tage"][0]["name"] == "Heute"
    assert {h["id"] for h in event["hinweise"]} == {"frost", "gewitter", "hitze", "sturm", "starkregen"}
    assert "Deutscher Wetterdienst" in event["quelle"]
    # Nach einer Aktualisierung kommen neue Daten ohne neue Anfrage.
    dwd["warnings"].return_value = [FROST]
    freezer.tick(600)
    await hass.config_entries.async_entries("wetterlage")[0].runtime_data.async_refresh()
    event = (await client.receive_json())["event"]
    assert event["warnungen"][0]["ueberschrift"] == "Amtliche WARNUNG vor FROST"


async def test_karte_ohne_eintrag(hass: HomeAssistant, hass_ws_client) -> None:
    from homeassistant.setup import async_setup_component  # noqa: PLC0415

    assert await async_setup_component(hass, "wetterlage", {})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "wetterlage/karte/abonnieren"})
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "not_found"
