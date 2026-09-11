"""Base entity for Salus iT600 Cloud devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SalusCloudCoordinator, SalusDevice


class SalusEntity(CoordinatorEntity[SalusCloudCoordinator]):
    """Entity of a Salus device backed by coordinator data."""

    _attr_has_entity_name = False  # Name includes gateway name to keep entity ids of multiple apartments apart

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        gateway_id = device.get("_gateway_id", "")
        gateway = coordinator.get_gateway(gateway_id)
        self._attr_name = f"{gateway.name if gateway else 'Salus iT600'} {device.get('name') or device_id}"
        self._attr_unique_id = f"{DOMAIN}_{gateway_id}_{device_id}"
        self._attr_device_info = coordinator.device_info(device)

    @property
    def device_data(self) -> SalusDevice:
        """Return current data of the device."""
        return self.coordinator.get_device(self._device_id) or {}

    @property
    def shadow_properties(self) -> dict[str, Any]:
        """Return current shadow properties of the device."""
        return self.device_data.get("_shadow_properties", {})

    @property
    def available(self) -> bool:
        """Return whether recent state data of the device is known."""
        return super().available and bool(self.device_data.get("_fresh"))
