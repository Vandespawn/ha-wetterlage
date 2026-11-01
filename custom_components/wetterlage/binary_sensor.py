"""Binärsensoren für die eigenen Hinweise (Frost, Gewitter, Hitze, Sturm, Starkregen)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WetterlageConfigEntry
from .engine import HINT_KEYS
from .entity import WetterlageEntity, iso

DEVICE_CLASS = {"frost": BinarySensorDeviceClass.COLD, "hitze": BinarySensorDeviceClass.HEAT}
ICONS = {"gewitter": "mdi:weather-lightning", "sturm": "mdi:weather-windy", "starkregen": "mdi:weather-pouring"}


class HintBinarySensor(WetterlageEntity, BinarySensorEntity):
    """An, sobald der Hinweis die eingestellte Stufe erreicht."""

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key, "binary_sensor")
        self._attr_device_class = DEVICE_CLASS.get(key)
        if key in ICONS:
            self._attr_icon = ICONS[key]

    @property
    def hint(self) -> dict[str, Any]:
        return self.result["hints"][self.key]

    @property
    def is_on(self) -> bool:
        return self.hint["aktiv"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        h = self.hint
        attrs = {
            "stufe": h["stufe"], "melden_ab": h["melden_ab"], "text": h["text"], "grund": h["grund"],
            "amtlich": h["amtlich"], "quelle": h["quelle"] if h["amtlich"] else f"{h['quelle']} (eigener Hinweis, berechnet)",
        }
        if self.key == "frost":
            attrs["um"] = iso(h.get("um"))
        return attrs


async def async_setup_entry(hass: HomeAssistant, entry: WetterlageConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    S = coordinator.settings
    async_add_entities(
        HintBinarySensor(coordinator, key) for key in HINT_KEYS
        if S["entitaeten"].get(key, True) and S["hinweise"][key]["an"]
    )
