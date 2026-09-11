"""Classification of Salus devices."""

from __future__ import annotations

from typing import Any

CLIMATE_MODELS = ("HTRP-RF", "TS600", "VS10", "VS20", "SQ610", "FC600")
SWITCH_MODELS = ("RS600", "SPE600", "SR600")


def is_climate_device(device: dict[str, Any]) -> bool:
    """Return whether the device is a thermostat."""
    return (
        (device.get("type") or "").lower() in ("thermostat", "climate")
        or (device.get("model") or "").upper().startswith(CLIMATE_MODELS)
        or "thermostat" in (device.get("name") or "").lower()
    )


def is_switch_device(device: dict[str, Any]) -> bool:
    """Return whether the device is a relay or a smart plug."""
    return (device.get("type") or "").lower() in ("switch", "relay") or (device.get("model") or "").upper().startswith(
        SWITCH_MODELS
    )
