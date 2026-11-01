"""Abruf der DWD-Open-Data-Quellen."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import aiohttp

from .parse import merge_warnings, nearest_stations, parse_mosmix_kmz, parse_pollen, parse_station_catalog

_LOGGER = logging.getLogger(__name__)

OPENDATA = "https://opendata.dwd.de"
GEOSERVER = "https://maps.dwd.de/geoserver/dwd"
CATALOG_URL = "https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/mosmix_stationskatalog.cfg?view=nasPublication&nn=16102"
TIMEOUT = aiohttp.ClientTimeout(total=30)
WARN_FIELDS = "IDENTIFIER,EVENT,HEADLINE,DESCRIPTION,INSTRUCTION,SEVERITY,EC_GROUP,ONSET,EXPIRES"


class DwdError(Exception):
    """Abruf beim DWD fehlgeschlagen."""


def round_coord(value: float, digits: int) -> float:
    return round(value, digits) if digits < 4 else value


class DwdClient:
    def __init__(self, session: aiohttp.ClientSession, user_agent: str = "ha-wetterlage") -> None:
        self._session = session
        self._headers = {"User-Agent": user_agent}

    async def _get(self, url: str, kind: str = "json", tries: int = 3) -> Any:
        last: Exception | None = None
        for attempt in range(1, tries + 1):
            try:
                async with self._session.get(url, headers=self._headers, timeout=TIMEOUT) as resp:
                    resp.raise_for_status()
                    if kind == "json":
                        return await resp.json(content_type=None)
                    if kind == "bytes":
                        return await resp.read()
                    return await resp.text(encoding="latin-1")
            except (TimeoutError, aiohttp.ClientError, ValueError) as err:
                last = err
                if attempt < tries:
                    await asyncio.sleep(0.5 * attempt)
        raise DwdError(f"{url}: {last}") from last

    async def _wfs(self, layer: str, cql: str, fields: str) -> list[dict[str, Any]]:
        url = (f"{GEOSERVER}/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=dwd:{layer}"
               f"&outputFormat=application/json&propertyName={fields}&CQL_FILTER={cql}")
        data = await self._get(url)
        return [f["properties"] for f in data.get("features", [])]

    # --- Einrichtung ---

    async def nearest_stations(self, lat: float, lon: float, count: int = 6) -> list[dict[str, Any]]:
        text = await self._get(CATALOG_URL, "text")
        return nearest_stations(parse_station_catalog(text), lat, lon, count)

    async def warncells(self, lat: float, lon: float) -> dict[str, Any]:
        """Warngebiete (Gemeinde und Kreis) zu einem Punkt."""
        point = f"INTERSECTS(SHAPE,POINT({lat}%20{lon}))"
        gem = await self._wfs("Warngebiete_Gemeinden", point, "WARNCELLID,NAME,KREIS")
        kreis = await self._wfs("Warngebiete_Kreise", point, "WARNCELLID,NAME")
        if not gem and not kreis:
            raise DwdError("Kein DWD-Warngebiet für diesen Ort gefunden")
        return {
            "gemeinde_id": int(gem[0]["WARNCELLID"]) if gem else None,
            "gemeinde_name": gem[0].get("NAME") if gem else None,
            "kreis_id": int(kreis[0]["WARNCELLID"]) if kreis else None,
            "kreis_name": kreis[0].get("NAME") if kreis else None,
        }

    # --- Laufende Abrufe ---

    async def mosmix(self, station_id: str) -> dict[str, Any]:
        url = f"{OPENDATA}/weather/local_forecasts/mos/MOSMIX_L/single_stations/{station_id}/kml/MOSMIX_L_LATEST_{station_id}.kmz"
        data = await self._get(url, "bytes")
        # Das Entpacken und Durchsuchen von ~350 KB XML gehört nicht in die Event-Loop.
        return await asyncio.get_running_loop().run_in_executor(None, parse_mosmix_kmz, data)

    async def warnings(self, gemeinde_id: int | None, kreis_id: int | None) -> list[dict[str, Any]]:
        gem: list[dict[str, Any]] = []
        kreis: list[dict[str, Any]] = []
        if gemeinde_id:
            gem = await self._wfs("Warnungen_Gemeinden", f"WARNCELLID={gemeinde_id}", WARN_FIELDS)
        if kreis_id:
            kreis = await self._wfs("Warnungen_Landkreise", f"GC_WARNCELLID={kreis_id}", WARN_FIELDS)
        return merge_warnings(gem, kreis)

    async def pollen(self) -> dict[str, Any]:
        return parse_pollen(await self._get(f"{OPENDATA}/climate_environment/health/alerts/s31fg.json"))

    async def radar(self, lat: float, lon: float, steps: int) -> list[dict[str, Any]]:
        """Radar-Nowcast als Punktwerte in 5-Minuten-Schritten ab jetzt.

        Nutzt die abfragbare Kartenebene des DWD. Einzelne Schritte können fehlen (mmh=None).
        """
        now = datetime.now(UTC)
        t0 = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
        sem = asyncio.Semaphore(4)
        d = 0.005

        async def one(k: int) -> dict[str, Any]:
            t = t0 + timedelta(minutes=5 * k)
            url = (f"{GEOSERVER}/wms?service=WMS&version=1.3.0&request=GetFeatureInfo&layers=dwd:Niederschlagsradar"
                   f"&query_layers=dwd:Niederschlagsradar&crs=EPSG:4326&bbox={lat - d},{lon - d},{lat + d},{lon + d}"
                   f"&width=3&height=3&i=1&j=1&info_format=application/json&time={t.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            async with sem:
                try:
                    data = await self._get(url, "json", tries=4)
                    props = data["features"][0]["properties"]
                    return {"t": t, "mmh": round(max(0.0, float(props["RV_ANALYSIS"])), 2), "ref": props.get("REFERENCE_TIME")}
                except (DwdError, KeyError, IndexError, TypeError, ValueError):
                    return {"t": t, "mmh": None, "ref": None}

        return list(await asyncio.gather(*(one(k) for k in range(steps + 1))))
