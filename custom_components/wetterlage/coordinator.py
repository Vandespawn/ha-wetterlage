"""Koordinator: Abrufe planen, rechnen, Ereignisse auslösen."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_GEMEINDE_ID,
    CONF_KREIS_ID,
    CONF_LAT,
    CONF_LON,
    CONF_STATION_ID,
    DOMAIN,
    EVENT_HINWEIS,
    EVENT_WARNUNG,
    OPT_SETTINGS,
)
from .defaults import merge_settings
from .dwd import DwdClient, DwdError, round_coord
from .engine import EngineInput, compute

_LOGGER = logging.getLogger(__name__)

STATION_KEYS = ["temperatur", "feuchte", "wind", "boeen", "strahlung", "uv", "regenrate", "regen_woche",
                "bodentemperatur", "luftdruck", "gefuehlt_station"]


class WetterlageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hält Rohdaten und Ergebnis für einen Ort."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.settings = merge_settings(entry.options.get(OPT_SETTINGS))
        Q = self.settings["quellen"]
        tick = max(1, min(int(Q["intervall_warnungen_min"]), int(Q["intervall_radar_min"]), 5))
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(minutes=tick))
        self.client = DwdClient(async_get_clientsession(hass))
        self.raw: dict[str, Any] = {"mosmix": None, "warnings": [], "pollen": None, "radar": []}
        self._last: dict[str, datetime] = {}
        self._first_done = False
        self._station_debouncer = Debouncer(hass, _LOGGER, cooldown=60, immediate=True, function=self._async_recompute)

    # --- Einstellungen, die von entry.data abhängen ---

    @property
    def station_id(self) -> str:
        v = str(self.settings["quellen"]["mosmix_station"]).strip()
        return self.config_entry.data[CONF_STATION_ID] if v in ("", "auto") else v

    @property
    def gemeinde_id(self) -> int | None:
        v = str(self.settings["quellen"]["warngebiet"]).strip()
        return self.config_entry.data.get(CONF_GEMEINDE_ID) if v in ("", "auto") else int(v)

    @property
    def query_point(self) -> tuple[float, float]:
        digits = int(self.settings["ort"]["koordinaten_runden"])
        return (round_coord(self.config_entry.data[CONF_LAT], digits), round_coord(self.config_entry.data[CONF_LON], digits))

    def _due(self, key: str, minutes: int) -> bool:
        last = self._last.get(key)
        return last is None or dt_util.utcnow() - last >= timedelta(minutes=minutes) - timedelta(seconds=30)

    # --- Abruf ---

    async def _async_update_data(self) -> dict[str, Any]:
        Q = self.settings["quellen"]
        now = dt_util.utcnow()
        if self._due("mosmix", int(Q["intervall_vorhersage_min"])):
            try:
                self.raw["mosmix"] = await self.client.mosmix(self.station_id)
                self._last["mosmix"] = now
            except DwdError as err:
                if self.raw["mosmix"] is None:
                    raise UpdateFailed(f"DWD-Vorhersage nicht erreichbar: {err}") from err
                _LOGGER.warning("Vorhersage nicht aktualisiert, nutze letzte Daten: %s", err)
        if self._due("warnings", int(Q["intervall_warnungen_min"])):
            try:
                self.raw["warnings"] = await self.client.warnings(self.gemeinde_id, self.config_entry.data.get(CONF_KREIS_ID))
                self._last["warnings"] = now
            except DwdError as err:
                _LOGGER.warning("Warnungen nicht aktualisiert: %s", err)
        if self._due("pollen", int(Q["intervall_pollen_min"])):
            try:
                self.raw["pollen"] = await self.client.pollen()
                self._last["pollen"] = now
            except DwdError as err:
                _LOGGER.warning("Pollenflug nicht aktualisiert: %s", err)
        if Q["radar"] and self._due("radar", int(Q["intervall_radar_min"])):
            lat, lon = self.query_point
            self.raw["radar"] = await self.client.radar(lat, lon, int(self.settings["regen"]["zeitraum_min"]) // 5)
            self._last["radar"] = now
        return self._compute()

    # --- Rechnen ---

    def _station_values(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for key in STATION_KEYS:
            entity_id = self.settings["station"].get(key)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
                out[key] = None
                continue
            try:
                out[key] = float(state.state)
            except ValueError:
                out[key] = None
        return out

    def _compute(self) -> dict[str, Any]:
        mos = self.raw["mosmix"]
        inp = EngineInput(
            now=dt_util.utcnow(),
            tz=dt_util.get_default_time_zone(),
            hours=mos["hours"],
            warnings=self.raw["warnings"],
            pollen_regions=(self.raw["pollen"] or {}).get("regions", []),
            radar=self.raw["radar"],
            station=self._station_values(),
            station_name=mos.get("name") or self.station_id,
        )
        result = compute(inp, self.settings)
        result["meta"] = {
            "mosmix_station": self.station_id,
            "mosmix_name": mos.get("name"),
            "mosmix_lauf": mos.get("issue"),
            "pollen_stand": (self.raw["pollen"] or {}).get("update"),
            "abgerufen": dict(self._last),
        }
        self._fire_events(result)
        return result

    async def _async_recompute(self) -> None:
        if self.raw["mosmix"] is not None:
            self.async_set_updated_data(self._compute())

    # --- Wetterstation beobachten ---

    @callback
    def async_start_station_listener(self) -> None:
        ids = [v for k, v in self.settings["station"].items() if k in STATION_KEYS and v]
        if not ids:
            return

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self._station_debouncer.async_call())

        self.config_entry.async_on_unload(async_track_state_change_event(self.hass, ids, _changed))
        self.config_entry.async_on_unload(self._station_debouncer.async_shutdown)

    # --- Ereignisse ---

    def _fire_events(self, result: dict[str, Any]) -> None:
        E = self.settings["ereignisse"]
        prev = self.data if self._first_done else None
        self._first_done = True
        if prev is None:
            return
        if E["warnungs_ereignis"]:
            old = {w["id"]: w for w in prev.get("warnings", [])}
            new = {w["id"]: w for w in result["warnings"]}
            for wid, w in new.items():
                if wid not in old:
                    self._fire(EVENT_WARNUNG, "beginn", w)
                elif (old[wid]["level"], old[wid]["headline"]) != (w["level"], w["headline"]):
                    self._fire(EVENT_WARNUNG, "aenderung", w)
            for wid, w in old.items():
                if wid not in new:
                    self._fire(EVENT_WARNUNG, "ende", w)
        if E["hinweis_ereignis"]:
            for key, h in result["hints"].items():
                before = prev.get("hints", {}).get(key, {})
                if h["aktiv"] != before.get("aktiv") or (h["aktiv"] and h["stufe"] != before.get("stufe")):
                    self.hass.bus.async_fire(EVENT_HINWEIS, {
                        "eintrag": self.config_entry.entry_id, "hinweis": key, "aktiv": h["aktiv"],
                        "stufe": h["stufe"], "vorher": before.get("stufe"), "text": h["text"], "amtlich": h["amtlich"],
                    })

    def _fire(self, event: str, typ: str, w: dict[str, Any]) -> None:
        self.hass.bus.async_fire(event, {
            "eintrag": self.config_entry.entry_id, "typ": typ, "ereignis": w["event"], "stufe": w["level"],
            "ueberschrift": w["headline"], "beginn": w["onset"], "ende": w["expires"], "gebiet": w["gebiet"],
        })
