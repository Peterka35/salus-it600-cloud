"""Switch platform for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Salus iT600 Cloud switch devices."""
    coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Parse devices and create switch entities
    for device_id, device_data in coordinator.data.items():
        if _is_switch_device(device_data):
            entities.append(
                SalusCloudSwitch(
                    coordinator,
                    device_id,
                    device_data,
                )
            )

    async_add_entities(entities)


def _is_switch_device(device_data: dict[str, Any]) -> bool:
    """Determine if device is a switch."""
    device_type = device_data.get("type", "").lower()
    model = device_data.get("model", "").upper()

    # Known switch models from local API
    switch_models = ["RS600", "SPE600", "SR600"]

    return (
        device_type == "switch"
        or device_type == "relay"
        or any(model.startswith(sm) for sm in switch_models)
    )


class SalusCloudSwitch(CoordinatorEntity[SalusCloudCoordinator], SwitchEntity):
    """Representation of a Salus iT600 Cloud switch."""

    _attr_has_entity_name = False  # We set full name including device name

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._device_code = device_data.get("device_code", "")

        # Use gateway name as prefix for entity name (like salusfy)
        gateway_name = coordinator.gateway_name or "Salus iT600"
        gateway_id = coordinator.gateway_id
        device_name = device_data.get("name", f"Switch {device_id}")
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
        """Return true if switch is on."""
        data = self.device_data

        # First, try shadow properties (from device_shadows API)
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            # Check OnOff state from shadow
            on_off = shadow_props.get("ep9:sOnOffS:OnOff")
            if on_off is not None:
                return on_off == 1

        # Fallback: Try different field names
        for field in ["is_on", "state", "OnOff", "power_state"]:
            if field in data:
                value = data[field]
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ["on", "true", "1"]
                if isinstance(value, int):
                    return value == 1

        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on %s", self._attr_name)

        try:
            await self.coordinator.gateway.set_switch_state(self._device_code, True)

            # Request immediate coordinator refresh to get updated state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to turn on switch: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to turn on switch: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off %s", self._attr_name)

        try:
            await self.coordinator.gateway.set_switch_state(self._device_code, False)

            # Request immediate coordinator refresh to get updated state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to turn off switch: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to turn off switch: {err}") from err

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
