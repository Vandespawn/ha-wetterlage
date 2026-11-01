"""Wetter-Entität mit DWD-MOSMIX-Vorhersage und Stationswerten für „jetzt“."""

from __future__ import annotations

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WetterlageConfigEntry
from .engine import condition, is_daylight
from .entity import WetterlageEntity


class WetterlageWeather(WetterlageEntity, SingleCoordinatorWeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "wetter", "weather")
        self._attr_translation_key = "wetter"
        self._attr_name = None  # Name des Geräts

    @property
    def _cur(self):
        return self.result["cur"]

    @property
    def condition(self) -> str | None:
        return self.result["condition"][1]

    @property
    def native_temperature(self) -> float | None:
        return self._cur["temperatur"]

    @property
    def native_apparent_temperature(self) -> float | None:
        return self.result["feel"]["value"]

    @property
    def humidity(self) -> float | None:
        v = self._cur["feuchte"]
        return None if v is None else round(v)

    @property
    def native_pressure(self) -> float | None:
        v = self._cur["luftdruck"]
        return None if v is None else round(v, 1)

    @property
    def native_wind_speed(self) -> float | None:
        return self._cur["wind"]

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._cur["boeen"]

    @property
    def wind_bearing(self) -> float | None:
        return self._cur["windrichtung"]

    @property
    def native_dew_point(self) -> float | None:
        return self._cur["taupunkt"]

    @property
    def cloud_coverage(self) -> float | None:
        return self._cur["bewoelkung"]

    @property
    def uv_index(self) -> float | None:
        return self._cur["uv"]

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for h in self.result["hours"][:96]:
            out.append(Forecast(
                datetime=h["t"].isoformat(),
                condition=condition(h, is_daylight(h))[1],
                native_temperature=h["T"],
                native_dew_point=h["Td"],
                native_precipitation=h["rr"],
                precipitation_probability=h["pRain"],
                native_wind_speed=h["ff"],
                native_wind_gust_speed=h["fx"],
                wind_bearing=h["dd"],
                cloud_coverage=h["neff"],
                native_pressure=h["p"],
            ))
        return out

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        # Heute immer zeigen, den angebrochenen letzten Tag der Vorhersage weglassen.
        days = [d for i, d in enumerate(self.result["days"]) if i == 0 or d["hours"] >= 12]
        return [Forecast(
            datetime=d["start"].isoformat(),
            condition=d["condition"],
            native_temperature=d["tx"],
            native_templow=d["tn"],
            native_precipitation=round(d["rr"], 1),
            precipitation_probability=d["pRain"],
            native_wind_speed=d["ff"],
            native_wind_gust_speed=d["fx"],
        ) for d in days]


async def async_setup_entry(hass: HomeAssistant, entry: WetterlageConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    if coordinator.settings["entitaeten"].get("wetter", True):
        async_add_entities([WetterlageWeather(coordinator)])
