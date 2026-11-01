"""WebSocket-Befehle für die Dashboard-Karte."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import DOMAIN
from .karte import karte_payload


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_eintraege)
    websocket_api.async_register_command(hass, ws_karte_abonnieren)


def _find_entry(hass: HomeAssistant, entry_id: str | None):
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id:
        return next((e for e in entries if e.entry_id == entry_id), None)
    return entries[0] if entries else None


@websocket_api.websocket_command({vol.Required("type"): "wetterlage/eintraege"})
@callback
def ws_eintraege(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Eingerichtete Orte, für die Auswahl im Karten-Editor."""
    connection.send_result(msg["id"], [
        {"entry_id": e.entry_id, "title": e.title} for e in hass.config_entries.async_loaded_entries(DOMAIN)
    ])


@websocket_api.websocket_command({vol.Required("type"): "wetterlage/karte/abonnieren", vol.Optional("eintrag"): str})
@callback
def ws_karte_abonnieren(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Kartendaten sofort senden und nach jeder Aktualisierung erneut."""
    entry = _find_entry(hass, msg.get("eintrag"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Kein eingerichteter Wetterlage-Ort gefunden")
        return
    coordinator = entry.runtime_data
    active = True

    @callback
    def _push() -> None:
        if active:
            connection.send_message(websocket_api.event_message(msg["id"], karte_payload(coordinator)))

    remove_listener = coordinator.async_add_listener(_push)

    @callback
    def _unsubscribe() -> None:
        nonlocal active
        active = False
        remove_listener()

    @callback
    def _on_unload() -> None:
        # Der Ort lädt neu (z. B. nach geänderten Einstellungen): Die Karte soll sich neu verbinden,
        # sonst hängt sie am alten Koordinator und bekommt keine Daten mehr.
        if active:
            connection.send_message(websocket_api.event_message(msg["id"], {"neu_verbinden": True}))
        _unsubscribe()

    entry.async_on_unload(_on_unload)
    connection.subscriptions[msg["id"]] = _unsubscribe
    connection.send_result(msg["id"])
    _push()
