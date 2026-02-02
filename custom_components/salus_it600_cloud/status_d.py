"""Helpers for parsing Status_d payloads."""
from __future__ import annotations

import logging
from typing import Any

from .const import STATUS_D_HUMIDITY_MODELS, STATUS_D_HUMIDITY_OFFSET, STATUS_D_KEY

_LOGGER = logging.getLogger(__name__)


def get_status_d(shadow_props: dict[str, Any] | None) -> str | None:
    """Return Status_d from shadow properties if present."""
    if not isinstance(shadow_props, dict):
        return None
    status_d = shadow_props.get(STATUS_D_KEY)
    return status_d if isinstance(status_d, str) else None


def model_supports_status_d_humidity(model: str | None) -> bool:
    """Return True if the device model is known to expose humidity via Status_d."""
    if not model:
        return False
    model_upper = model.upper()
    return any(model_upper.startswith(prefix) for prefix in STATUS_D_HUMIDITY_MODELS)


def decode_status_d_humidity(status_d: str | None) -> float | None:
    """Extract humidity from Status_d if present (BCD at offset)."""
    if not status_d:
        return None
    try:
        raw = bytes.fromhex(status_d)
    except ValueError:
        _LOGGER.debug("Status_d is not valid hex")
        return None
    if len(raw) <= STATUS_D_HUMIDITY_OFFSET:
        _LOGGER.debug("Status_d too short for humidity offset")
        return None
    value = raw[STATUS_D_HUMIDITY_OFFSET]
    hi, lo = (value >> 4) & 0xF, value & 0xF
    if hi <= 9 and lo <= 9:
        return float(hi * 10 + lo)
    if 0 <= value <= 100:
        return float(value)
    _LOGGER.debug("Status_d humidity byte not in expected range")
    return None


def has_status_d_humidity(device_data: dict[str, Any]) -> bool:
    """Return True if device data is likely to have Status_d humidity."""
    model = device_data.get("model")
    if not model_supports_status_d_humidity(model):
        return False
    shadow_props = device_data.get("_shadow_properties")
    return get_status_d(shadow_props) is not None
