"""Konstanten der Integration Wetterlage."""

from __future__ import annotations

DOMAIN = "wetterlage"
ATTRIBUTION = "Datenbasis: Deutscher Wetterdienst (CC BY 4.0), Werte teils von der Integration berechnet"

# Schlüssel in entry.data (bei der Einrichtung ermittelt)
CONF_LAT = "lat"
CONF_LON = "lon"
CONF_NAME = "name"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_GEMEINDE_ID = "gemeinde_id"
CONF_GEMEINDE_NAME = "gemeinde_name"
CONF_KREIS_ID = "kreis_id"
CONF_KREIS_NAME = "kreis_name"

# Schlüssel in entry.options
OPT_SETTINGS = "settings"

EVENT_WARNUNG = "wetterlage_warnung"
EVENT_HINWEIS = "wetterlage_hinweis"
