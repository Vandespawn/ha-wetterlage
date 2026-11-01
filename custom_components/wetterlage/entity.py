"""Gemeinsame Basis aller Entitäten."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_GEMEINDE_NAME, DOMAIN
from .coordinator import WetterlageCoordinator


class WetterlageEntity(CoordinatorEntity[WetterlageCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: WetterlageCoordinator, key: str, platform: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        prefix = coordinator.settings["entitaeten"]["praefix"] or "wetterlage"
        self.entity_id = f"{platform}.{prefix}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Wetterlage",
            model=f"DWD Open Data · {entry.data.get(CONF_GEMEINDE_NAME) or ''}".strip(" ·"),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def result(self) -> dict[str, Any]:
        return self.coordinator.data

    @property
    def settings(self) -> dict[str, Any]:
        return self.coordinator.settings


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None
