"""Sensoren."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WetterlageConfigEntry
from .const import CONF_GEMEINDE_NAME, CONF_KREIS_NAME
from .defaults import POLLEN_ARTEN
from .engine import P_LABEL, P_NAME, signed
from .entity import WetterlageEntity, iso

Result = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class WetterlageSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Result, Any], Any]
    attrs_fn: Callable[[Result, Any], dict[str, Any]] | None = None
    available_fn: Callable[[Result, Any], bool] | None = None


def _feel_attrs(r: Result, e: Any) -> dict[str, Any]:
    f, c = r["feel"], r["cur"]
    return {
        "wort": f["word"], "modell": f["modell"],
        "grund": ", ".join(f"{p['grund']} {signed(p['delta'])} °C" for p in f["parts"]) or "keine Korrektur",
        "anteile": {p["grund"]: round(p["delta"], 2) for p in f["parts"]},
        "temperatur": c["temperatur"],
        "quelle": f"Temperatur: {c['src']['temperatur']}, Wind: {c['src']['wind']}, Sonne: {c['src']['strahlung']}",
    }


def _rain_attrs(r: Result, e: Any) -> dict[str, Any]:
    rain = r["rain"]
    return {
        "text": rain["text"], "beginn": iso(rain.get("beginn")), "ende": iso(rain.get("ende")),
        "verlauf": [{"zeit": iso(s["t"]), "mm_h": s["mmh"]} for s in rain["steps"]],
        "radar_lauf": rain.get("ref"), "quelle": "DWD Radar-Nowcast (RV)",
    }


def _warn_attrs(r: Result, e: Any) -> dict[str, Any]:
    W = e.settings["warnungen"]
    data = e.coordinator.config_entry.data
    return {
        "anzahl": len(r["warnings"]),
        "ueberschrift": r["warnings"][0]["headline"] if r["warnings"] else None,
        "warnungen": [{
            "ereignis": w["event"], "stufe": w["level"], "ueberschrift": w["headline"],
            **({"beschreibung": w["description"]} if W["beschreibung"] else {}),
            **({"verhaltenshinweise": w["instruction"]} if W["verhaltenshinweise"] else {}),
            "beginn": w["onset"], "ende": w["expires"], "gebiet": w["gebiet"],
        } for w in r["warnings"]],
        "warngebiet": data.get(CONF_GEMEINDE_NAME), "warngebiet_id": e.coordinator.gemeinde_id,
        "kreis": data.get(CONF_KREIS_NAME), "quelle": "DWD Warnungen (amtlich, unverändert)",
    }


def _pollen_max(r: Result, e: Any) -> str:
    b = r["pollen"]["belastet"]
    return f"{b[0]['name']}: {b[0]['label']}" if b else "keine"


def _bericht_attrs(r: Result, e: Any) -> dict[str, Any]:
    return {"text": r["bericht"], "quelle": "berechnet aus DWD MOSMIX, Warnungen und Pollenflug"}


def _day_attrs(day_key: str):
    def fn(r: Result, e: Any) -> dict[str, Any]:
        d = r.get(day_key)
        return {"zustand": d["text"], "tiefstwert": d["tn"], "regen_mm": round(d["rr"], 1), "quelle": "DWD MOSMIX"} if d else {}
    return fn


SENSORS: tuple[WetterlageSensorDescription, ...] = (
    WetterlageSensorDescription(
        key="gefuehlte_temperatur", device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, suggested_display_precision=1,
        value_fn=lambda r, e: None if r["feel"]["value"] is None else round(r["feel"]["value"], 2), attrs_fn=_feel_attrs),
    WetterlageSensorDescription(
        key="regen_naechste_stunde", device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, suggested_display_precision=1,
        value_fn=lambda r, e: r["rain"]["sum"], attrs_fn=_rain_attrs, available_fn=lambda r, e: not r["rain"]["aus"]),
    WetterlageSensorDescription(
        key="regen_6_stunden", device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, suggested_display_precision=1,
        value_fn=lambda r, e: r["regen_6h"], attrs_fn=lambda r, e: {"quelle": "DWD MOSMIX"}),
    WetterlageSensorDescription(
        key="regen_24_stunden", device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, suggested_display_precision=1,
        value_fn=lambda r, e: r["regen_24h"], attrs_fn=lambda r, e: {"quelle": "DWD MOSMIX"}),
    WetterlageSensorDescription(
        key="amtliche_warnung", icon="mdi:alert",
        value_fn=lambda r, e: r["warnings"][0]["level"] if r["warnings"] else 0, attrs_fn=_warn_attrs),
    WetterlageSensorDescription(
        key="pollen_hoechste", icon="mdi:flower-pollen",
        value_fn=_pollen_max,
        attrs_fn=lambda r, e: {"region": r["pollen"]["region"], "tag": r["pollen"]["tag"],
                               "belastet": [a["name"] for a in r["pollen"]["belastet"]], "quelle": "DWD Pollenflug-Gefahrenindex"}),
    WetterlageSensorDescription(
        key="tiefstwert_nacht", device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, suggested_display_precision=1,
        value_fn=lambda r, e: r["hints"]["frost"]["min_t"],
        attrs_fn=lambda r, e: {"um": iso(r["hints"]["frost"]["um"]), "bodennah": r["hints"]["frost"]["min_t5"],
                               "zeitraum_h": e.settings["hinweise"]["frost"]["vorlauf_h"], "quelle": "DWD MOSMIX"}),
    WetterlageSensorDescription(
        key="hoechstwert_morgen", device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, suggested_display_precision=1,
        value_fn=lambda r, e: r["morgen"]["tx"] if r["morgen"] else None, attrs_fn=_day_attrs("morgen")),
    WetterlageSensorDescription(
        key="sonnenstunden_morgen", device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS, suggested_display_precision=1,
        value_fn=lambda r, e: round(r["morgen"]["sunH"], 2) if r["morgen"] else None,
        attrs_fn=lambda r, e: {"quelle": "DWD MOSMIX"}),
    WetterlageSensorDescription(
        key="regen_7_tage", device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS, suggested_display_precision=1,
        value_fn=lambda r, e: e.coordinator._station_values().get("regen_woche"),
        attrs_fn=lambda r, e: {"quelle": "Station"},
        available_fn=lambda r, e: bool(e.settings["station"]["regen_woche"])),
    WetterlageSensorDescription(
        key="luftdruck", device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA, suggested_display_precision=1,
        value_fn=lambda r, e: None if r["cur"]["luftdruck"] is None else round(r["cur"]["luftdruck"], 1),
        attrs_fn=lambda r, e: {"bezug": "Meereshöhe", "quelle": r["cur"]["src"]["luftdruck"]}),
    WetterlageSensorDescription(
        key="tagesbericht", icon="mdi:text-box-outline",
        value_fn=lambda r, e: (r["bericht"][:252] + "…") if len(r["bericht"]) > 255 else r["bericht"],
        attrs_fn=_bericht_attrs),
)


class WetterlageSensor(WetterlageEntity, SensorEntity):
    entity_description: WetterlageSensorDescription

    def __init__(self, coordinator, description: WetterlageSensorDescription) -> None:
        super().__init__(coordinator, description.key, "sensor")
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        fn = self.entity_description.available_fn
        return fn(self.result, self) if fn else True

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.result, self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.result, self) if fn else None


class PollenSensor(WetterlageEntity, SensorEntity):
    """Eine Pollenart als Zahl 0 bis 3 (in halben Stufen), gut für Automationen."""

    _attr_icon = "mdi:flower-pollen-outline"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, art: str) -> None:
        super().__init__(coordinator, f"pollen_{art.lower()}", "sensor")
        self.art = art
        self._attr_translation_key = "pollen_art"
        self._attr_translation_placeholders = {"art": P_NAME.get(art, art)}

    def _entry(self) -> dict[str, Any] | None:
        return next((a for a in self.result["pollen"]["arten"] if a["id"] == self.art), None)

    @property
    def native_value(self) -> float | None:
        a = self._entry()
        return a["index"] if a else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self._entry() or {}
        region_id = self.result["pollen"].get("region_id")
        regions = (self.coordinator.raw["pollen"] or {}).get("regions", [])
        reg = next((x for x in regions if x["id"] == region_id), None)
        days = (reg or {}).get("pollen", {}).get(self.art, {})
        return {
            "stufe": a.get("label"), "tag": self.result["pollen"]["tag"], "region": self.result["pollen"]["region"],
            "heute": P_LABEL.get(days.get("today", ""), None), "morgen": P_LABEL.get(days.get("tomorrow", ""), None),
            "uebermorgen": P_LABEL.get(days.get("dayafter_to", ""), None), "quelle": "DWD Pollenflug-Gefahrenindex",
        }


async def async_setup_entry(hass: HomeAssistant, entry: WetterlageConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    E = coordinator.settings["entitaeten"]
    entities: list[SensorEntity] = [WetterlageSensor(coordinator, d) for d in SENSORS if E.get(d.key, True)]
    if E.get("pollen_einzeln", True):
        entities += [PollenSensor(coordinator, a) for a in POLLEN_ARTEN if a in coordinator.settings["pollen"]["arten"]]
    async_add_entities(entities)
