"""Wetterlage: DWD-Vorhersage, amtliche Warnungen, Pollenflug und Regenradar für Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, DOMAIN, VERSION
from .coordinator import WetterlageCoordinator
from .websocket import async_register as async_register_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.WEATHER]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
CARD_FILE = Path(__file__).parent / "frontend" / "wetterlage-card.js"

type WetterlageConfigEntry = ConfigEntry[WetterlageCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Karte bereitstellen und WebSocket-Befehle anmelden (einmal je Home Assistant)."""
    async_register_websocket(hass)
    # Die Karte kommt mit der Integration: kein eigenes HACS-Paket, keine Ressource von Hand.
    if hass.http is not None:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)])
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    else:
        _LOGGER.debug("Frontend nicht geladen, Karte wird nicht angemeldet")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WetterlageConfigEntry) -> bool:
    coordinator = WetterlageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_station_listener()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WetterlageConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
