"""Sensor platform for Salus iT600 Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .entity import SalusEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud sensors."""
    coordinator: SalusCloudCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for device_id, device in coordinator.data.items():
        if _has_temperature(device):
            entities.append(SalusCloudTemperatureSensor(coordinator, device_id, device))
        if _has_humidity(device):
            entities.append(SalusCloudHumiditySensor(coordinator, device_id, device))
        if _has_battery(device):
            entities.append(SalusCloudBatterySensor(coordinator, device_id, device))
    async_add_entities(entities)


def _has_temperature(device: dict[str, Any]) -> bool:
    """Check if device is a standalone temperature sensor."""
    device_type = device.get("type", "").lower()
    return device_type == "temperature_sensor" or (device_type == "sensor" and "temperature" in device)


def _has_humidity(device: dict[str, Any]) -> bool:
    """Check if device has humidity sensor."""
    return "humidity" in device or ("status" in device and "humidity" in device["status"])


def _has_battery(device: dict[str, Any]) -> bool:
    """Check if device has battery information."""
    return "battery" in device or "battery_level" in device or ("status" in device and "battery" in device["status"])


def _value(data: dict[str, Any], fields: tuple[str, ...], scale_above_100: bool) -> float | None:
    """Return first present field from device data or its status, scaled from x100 format when needed."""
    for source in (data, data.get("status") if isinstance(data.get("status"), dict) else {}):
        for field in fields:
            if field in source:
                value = source[field]
                if scale_above_100 and isinstance(value, int) and value > 100:
                    return value / 100.0
                return float(value)
    return None


class SalusCloudSensor(SalusEntity, SensorEntity):
    """Base class for Salus Cloud sensors."""

    def __init__(
        self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice, sensor_type: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, device)
        self._attr_name = f"{self._attr_name} {sensor_type.title()}"
        self._attr_unique_id = f"{self._attr_unique_id}_{sensor_type}"


class SalusCloudTemperatureSensor(SalusCloudSensor):
    """Temperature sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, device_id, device, "temperature")

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        return _value(self.device_data, ("temperature", "current_temperature", "LocalTemperature"), True)


class SalusCloudHumiditySensor(SalusCloudSensor):
    """Humidity sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the humidity sensor."""
        super().__init__(coordinator, device_id, device, "humidity")

    @property
    def native_value(self) -> float | None:
        """Return the humidity value."""
        return _value(self.device_data, ("humidity", "current_humidity"), True)


class SalusCloudBatterySensor(SalusCloudSensor):
    """Battery sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, device_id, device, "battery")

    @property
    def native_value(self) -> float | None:
        """Return the battery level."""
        return _value(self.device_data, ("battery", "battery_level", "battery_percentage"), False)
