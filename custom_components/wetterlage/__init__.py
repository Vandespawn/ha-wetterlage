"""Wetterlage: DWD-Vorhersage, amtliche Warnungen, Pollenflug und Regenradar für Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import WetterlageCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.WEATHER]

type WetterlageConfigEntry = ConfigEntry[WetterlageCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WetterlageConfigEntry) -> bool:
    coordinator = WetterlageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_station_listener()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WetterlageConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
