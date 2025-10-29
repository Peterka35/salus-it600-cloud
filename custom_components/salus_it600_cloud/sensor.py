"""Sensor platform for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
    """Set up Salus iT600 Cloud sensor devices."""
    coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Parse devices and create sensor entities
    for device_id, device_data in coordinator.data.items():
        # Temperature sensors
        if _has_temperature(device_data):
            entities.append(
                SalusCloudTemperatureSensor(
                    coordinator,
                    device_id,
                    device_data,
                )
            )

        # Humidity sensors
        if _has_humidity(device_data):
            entities.append(
                SalusCloudHumiditySensor(
                    coordinator,
                    device_id,
                    device_data,
                )
            )

        # Battery sensors
        if _has_battery(device_data):
            entities.append(
                SalusCloudBatterySensor(
                    coordinator,
                    device_id,
                    device_data,
                )
            )

    async_add_entities(entities)


def _has_temperature(device_data: dict[str, Any]) -> bool:
    """Check if device has temperature sensor."""
    # For standalone temperature sensors (not thermostats)
    device_type = device_data.get("type", "").lower()
    return (
        device_type == "temperature_sensor"
        or device_type == "sensor"
        and "temperature" in device_data
    )


def _has_humidity(device_data: dict[str, Any]) -> bool:
    """Check if device has humidity sensor."""
    return (
        "humidity" in device_data
        or ("status" in device_data and "humidity" in device_data["status"])
    )


def _has_battery(device_data: dict[str, Any]) -> bool:
    """Check if device has battery information."""
    return (
        "battery" in device_data
        or "battery_level" in device_data
        or ("status" in device_data and "battery" in device_data["status"])
    )


class SalusCloudSensor(CoordinatorEntity[SalusCloudCoordinator], SensorEntity):
    """Base class for Salus Cloud sensors."""

    _attr_has_entity_name = False  # We set full name including device name

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._sensor_type = sensor_type

        # Use gateway name as prefix for entity name (like salusfy)
        gateway_name = coordinator.gateway_name or "Salus iT600"
        gateway_id = coordinator.gateway_id
        device_name = device_data.get("name", device_id)
        self._attr_name = f"{gateway_name} {device_name} {sensor_type.title()}"

        # Set unique_id with gateway to create new entities
        self._attr_unique_id = f"{DOMAIN}_{gateway_id}_{device_id}_{sensor_type}"

        # Set explicit object_id to ensure unique entity IDs
        import re
        gateway_slug = re.sub(r'[^a-z0-9_]+', '_', gateway_name.lower()).strip('_')
        device_slug = re.sub(r'[^a-z0-9_]+', '_', device_name.lower()).strip('_')
        sensor_slug = re.sub(r'[^a-z0-9_]+', '_', sensor_type.lower()).strip('_')
        self._attr_object_id = f"{gateway_slug}_{device_slug}_{sensor_slug}"

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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class SalusCloudTemperatureSensor(SalusCloudSensor):
    """Temperature sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, device_id, device_data, "temperature")

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        data = self.device_data

        # Try different field names
        for field in ["temperature", "current_temperature", "LocalTemperature"]:
            if field in data:
                temp = data[field]
                if isinstance(temp, int) and temp > 100:
                    return temp / 100.0
                return float(temp)

        # Try nested status
        if "status" in data and isinstance(data["status"], dict):
            if "temperature" in data["status"]:
                temp = data["status"]["temperature"]
                if isinstance(temp, int) and temp > 100:
                    return temp / 100.0
                return float(temp)

        return None


class SalusCloudHumiditySensor(SalusCloudSensor):
    """Humidity sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the humidity sensor."""
        super().__init__(coordinator, device_id, device_data, "humidity")

    @property
    def native_value(self) -> float | None:
        """Return the humidity value."""
        data = self.device_data

        # Try different field names
        for field in ["humidity", "current_humidity"]:
            if field in data:
                humidity = data[field]
                if isinstance(humidity, int) and humidity > 100:
                    return humidity / 100.0
                return float(humidity)

        # Try nested status
        if "status" in data and isinstance(data["status"], dict):
            if "humidity" in data["status"]:
                humidity = data["status"]["humidity"]
                if isinstance(humidity, int) and humidity > 100:
                    return humidity / 100.0
                return float(humidity)

        return None


class SalusCloudBatterySensor(SalusCloudSensor):
    """Battery sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, device_id, device_data, "battery")

    @property
    def native_value(self) -> float | None:
        """Return the battery level."""
        data = self.device_data

        # Try different field names
        for field in ["battery", "battery_level", "battery_percentage"]:
            if field in data:
                return float(data[field])

        # Try nested status
        if "status" in data and isinstance(data["status"], dict):
            for field in ["battery", "battery_level"]:
                if field in data["status"]:
                    return float(data["status"][field])

        return None
