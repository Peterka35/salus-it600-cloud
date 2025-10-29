"""Binary sensor platform for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SalusCloudCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud binary sensor devices."""
    coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Parse devices and create binary sensor entities
    for device_id, device_data in coordinator.data.items():
        if _is_binary_sensor_device(device_data):
            # Determine device class
            device_class = _get_device_class(device_data)

            entities.append(
                SalusCloudBinarySensor(
                    coordinator,
                    device_id,
                    device_data,
                    device_class,
                )
            )

    async_add_entities(entities)


def _is_binary_sensor_device(device_data: dict[str, Any]) -> bool:
    """Determine if device is a binary sensor."""
    device_type = device_data.get("type", "").lower()
    model = device_data.get("model", "").upper()

    # Known binary sensor types
    binary_types = ["door_sensor", "window_sensor", "motion_sensor", "binary_sensor"]

    return device_type in binary_types or model.startswith("WLS")


def _get_device_class(device_data: dict[str, Any]) -> BinarySensorDeviceClass | None:
    """Determine binary sensor device class."""
    device_type = device_data.get("type", "").lower()
    model = device_data.get("model", "").upper()

    if "door" in device_type or "window" in device_type or model.startswith("WLS"):
        return BinarySensorDeviceClass.DOOR

    if "motion" in device_type:
        return BinarySensorDeviceClass.MOTION

    if "occupancy" in device_type:
        return BinarySensorDeviceClass.OCCUPANCY

    return None


class SalusCloudBinarySensor(CoordinatorEntity[SalusCloudCoordinator], BinarySensorEntity):
    """Representation of a Salus iT600 Cloud binary sensor."""

    _attr_has_entity_name = False  # We set full name including device name

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._attr_device_class = device_class

        # Use gateway name as prefix for entity name (like salusfy)
        gateway_name = coordinator.gateway_name or "Salus iT600"
        gateway_id = coordinator.gateway_id
        device_name = device_data.get("name", f"Binary Sensor {device_id}")
        self._attr_name = f"{gateway_name} {device_name}"

        # Set unique_id with gateway to create new entities
        self._attr_unique_id = f"{DOMAIN}_{gateway_id}_{device_id}"

        # Set explicit object_id to ensure unique entity IDs
        import re
        gateway_slug = re.sub(r'[^a-z0-9_]+', '_', gateway_name.lower()).strip('_')
        device_slug = re.sub(r'[^a-z0-9_]+', '_', device_name.lower()).strip('_')
        self._attr_object_id = f"{gateway_slug}_{device_slug}"

        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Salus",
            "model": device_data.get("model", "iT600"),
            "via_device": (DOMAIN, device_data.get("_gateway_id")),
        }

    @property
    def device_data(self) -> dict[str, Any]:
        """Return current device data from coordinator."""
        return self.coordinator.get_device(self._device_id) or {}

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        data = self.device_data

        # Try different field names
        for field in ["is_on", "state", "active", "triggered", "open"]:
            if field in data:
                value = data[field]
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ["on", "true", "1", "open", "active"]
                if isinstance(value, int):
                    return value == 1

        # Try nested status
        if "status" in data and isinstance(data["status"], dict):
            for field in ["state", "active", "triggered"]:
                if field in data["status"]:
                    value = data["status"][field]
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ["on", "true", "1", "open", "active"]
                    if isinstance(value, int):
                        return value == 1

        return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
