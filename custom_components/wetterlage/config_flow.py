"""Einrichtung und Optionen."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    ObjectSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify
import voluptuous as vol

from .const import (
    CONF_GEMEINDE_ID,
    CONF_GEMEINDE_NAME,
    CONF_KREIS_ID,
    CONF_KREIS_NAME,
    CONF_LAT,
    CONF_LON,
    CONF_NAME,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
    OPT_SETTINGS,
)
from .coordinator import STATION_KEYS
from .defaults import DEFAULT_SETTINGS, merge_settings
from .dwd import DwdClient, DwdError, round_coord
from .parse import pollen_region_for_warncell

_LOGGER = logging.getLogger(__name__)


class WetterlageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung: Ort wählen, DWD-Station und Warngebiet ermitteln, Pollenregion wählen."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._regions: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WetterlageOptionsFlow:
        return WetterlageOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            lat = float(user_input["ort"]["latitude"])
            lon = float(user_input["ort"]["longitude"])
            await self.async_set_unique_id(f"{lat:.2f}_{lon:.2f}")
            self._abort_if_unique_id_configured()
            client = DwdClient(async_get_clientsession(self.hass))
            digits = int(DEFAULT_SETTINGS["ort"]["koordinaten_runden"])
            try:
                stations = await client.nearest_stations(lat, lon)
                station = None
                for s in stations[:4]:  # nicht jede Station hat eine MOSMIX-Datei
                    try:
                        await client.mosmix(s["id"])
                    except DwdError:
                        continue
                    station = s
                    break
                if station is None:
                    raise DwdError("Keine MOSMIX-Station in der Nähe erreichbar")
                cells = await client.warncells(round_coord(lat, digits), round_coord(lon, digits))
                pollen = await client.pollen()
            except DwdError as err:
                _LOGGER.warning("Einrichtung: DWD nicht erreichbar: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._data = {
                    CONF_NAME: user_input[CONF_NAME], CONF_LAT: lat, CONF_LON: lon,
                    CONF_STATION_ID: station["id"], CONF_STATION_NAME: f"{station['name']} ({station['km']} km)",
                    CONF_GEMEINDE_ID: cells["gemeinde_id"], CONF_GEMEINDE_NAME: cells["gemeinde_name"],
                    CONF_KREIS_ID: cells["kreis_id"], CONF_KREIS_NAME: cells["kreis_name"],
                }
                self._regions = pollen["regions"]
                return await self.async_step_pollen()

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=self.hass.config.location_name or "Zuhause"): str,
            vol.Required("ort", default={"latitude": self.hass.config.latitude, "longitude": self.hass.config.longitude}):
                LocationSelector(LocationSelectorConfig(radius=False)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_pollen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            settings = merge_settings({})
            settings["quellen"]["pollen_region"] = int(user_input["pollen_region"])
            settings["ort"]["hoehe_m"] = int(self.hass.config.elevation or 0)
            # Mehrere Orte brauchen unterschiedliche Entitäts-IDs.
            if self._async_current_entries():
                settings["entitaeten"]["praefix"] = f"wetterlage_{slugify(self._data[CONF_NAME])}"
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data, options={OPT_SETTINGS: settings})

        state_region = pollen_region_for_warncell(self._data.get(CONF_GEMEINDE_ID))
        regions = sorted(self._regions, key=lambda r: (r["region_id"] != state_region, r["id"]))
        options = [
            SelectOptionDict(value=str(r["id"]), label=r["name"] if r["name"] == r["bundesland"] else f"{r['name']} ({r['bundesland']})")
            for r in regions
        ]
        schema = vol.Schema({
            vol.Required("pollen_region", default=options[0]["value"] if options else "0"):
                SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
        })
        return self.async_show_form(
            step_id="pollen", data_schema=schema,
            description_placeholders={
                "station": self._data[CONF_STATION_NAME],
                "gemeinde": self._data.get(CONF_GEMEINDE_NAME) or "–",
                "kreis": self._data.get(CONF_KREIS_NAME) or "–",
            },
        )


class WetterlageOptionsFlow(OptionsFlowWithReload):
    """Optionen. Ein eigenes Einstellungsfeld in der Seitenleiste folgt; bis dahin sind alle
    Einstellungen über „Alle Einstellungen“ als YAML änderbar."""

    @property
    def _settings(self) -> dict[str, Any]:
        return merge_settings(self.config_entry.options.get(OPT_SETTINGS))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["station", "alle"])

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        settings = self._settings
        if user_input is not None:
            settings["station"]["vorrang"] = user_input["vorrang"]
            for key in STATION_KEYS:
                settings["station"][key] = user_input.get(key) or ""
            return self.async_create_entry(data={OPT_SETTINGS: settings})

        fields: dict[Any, Any] = {
            vol.Required("vorrang", default=settings["station"]["vorrang"]): SelectSelector(SelectSelectorConfig(
                options=[SelectOptionDict(value="station", label="Station, DWD nur als Ersatz"),
                         SelectOptionDict(value="dwd", label="DWD, Station nur als Ersatz")],
                translation_key="vorrang")),
        }
        for key in STATION_KEYS:
            current = settings["station"].get(key) or None
            fields[vol.Optional(key, description={"suggested_value": current})] = EntitySelector(
                EntitySelectorConfig(domain="sensor"))
        return self.async_show_form(step_id="station", data_schema=vol.Schema(fields))

    async def async_step_alle(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw = user_input.get("einstellungen")
            if not isinstance(raw, dict):
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(data={OPT_SETTINGS: merge_settings(raw)})
        schema = vol.Schema({vol.Required("einstellungen", default=self._settings): ObjectSelector()})
        return self.async_show_form(step_id="alle", data_schema=schema, errors=errors)
