"""Gemeinsame Testdaten.

Die Tests für Rechenkern und Einlesen brauchen kein Home Assistant: engine.py, parse.py
und defaults.py werden direkt als Module geladen.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "wetterlage"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"wl_{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


defaults = _load("defaults")
engine = _load("engine")
parse = _load("parse")

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 1, 10, 30, tzinfo=UTC)  # 11:30 Uhr in Berlin


def make_hours(n: int = 72, **over) -> list[dict]:
    """Ruhige Herbstlage: 8 °C am Tag, 1 °C in der Nacht, trocken, wolkig."""
    start = NOW.replace(minute=0) + timedelta(hours=1)
    hours = []
    for i in range(n):
        t = start + timedelta(hours=i)
        local = t.astimezone(TZ).hour
        temp = 1.0 + 7.0 * max(0.0, 1 - abs(local - 14) / 8)
        hours.append({"t": t, "T": temp, "Td": temp - 4, "T5": temp - 1.1, "ff": 10.0, "fx": 20.0, "dd": 120.0,
                      "rr": 0.0, "pRain": 5.0, "ww": 2.0, "neff": 70.0, "thunder": 0.0,
                      "sun": 1200.0 if 8 <= local <= 16 else 0.0, "rad": 200.0 if 8 <= local <= 16 else 0.0, "p": 1018.0})
    for key, fn in over.items():
        for i, h in enumerate(hours):
            h[key] = fn(i, h)
    return hours


@pytest.fixture
def settings():
    return defaults.merge_settings({})


@pytest.fixture
def inp():
    return engine.EngineInput(now=NOW, tz=TZ, hours=make_hours(), station={})
