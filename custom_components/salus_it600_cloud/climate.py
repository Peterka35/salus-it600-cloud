"""Climate platform for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_AWAY,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_DEVICE_ID, ATTR_GATEWAY_ID, ATTR_MODEL, DOMAIN
from .coordinator import SalusCloudCoordinator

_LOGGER = logging.getLogger(__name__)

# Preset modes mapping to HoldType values
PRESET_SCHEDULE = "schedule"  # HoldType = 0 (Auto/Schedule)
PRESET_MANUAL = "manual"  # HoldType = 2 (Manual Hold)
PRESET_FROST = "away"  # HoldType = 7 (Standby/Frost) - using PRESET_AWAY

# Mapping between preset modes and HoldType values
PRESET_TO_HOLDTYPE = {
    PRESET_SCHEDULE: 0,
    PRESET_MANUAL: 2,
    PRESET_FROST: 7,
}

HOLDTYPE_TO_PRESET = {
    0: PRESET_SCHEDULE,
    2: PRESET_MANUAL,
    7: PRESET_FROST,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud climate devices."""
    coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Parse devices and create climate entities
    for device_id, device_data in coordinator.data.items():
        # Check if this is a thermostat/climate device
        # This logic will need to be adjusted based on actual API response structure
        if _is_climate_device(device_data):
            entities.append(
                SalusCloudClimate(
                    coordinator,
                    device_id,
                    device_data,
                )
            )

    async_add_entities(entities)


def _is_climate_device(device_data: dict[str, Any]) -> bool:
    """Determine if device is a climate device."""
    # Based on the local implementation, we look for specific device types
    # This may need adjustment based on cloud API response
    device_type = device_data.get("type", "").lower()
    model = device_data.get("model", "").upper()

    # Check for known thermostat models
    climate_models = ["HTRP-RF", "TS600", "VS10", "VS20", "SQ610", "FC600"]

    return (
        device_type in ["thermostat", "climate"]
        or any(model.startswith(cm) for cm in climate_models)
        or "thermostat" in device_data.get("name", "").lower()
    )


class SalusCloudClimate(CoordinatorEntity[SalusCloudCoordinator], ClimateEntity):
    """Representation of a Salus iT600 Cloud climate device."""

    _attr_has_entity_name = False  # We set full name including device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # Now supports temperature control and preset modes!
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_SCHEDULE, PRESET_MANUAL, PRESET_FROST]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)

        self._device_id = device_id
        self._device_code = device_data.get("device_code", "")

        # Use gateway name as prefix for entity name (like salusfy)
        gateway_name = coordinator.gateway_name or "Salus iT600"
        gateway_id = coordinator.gateway_id
        device_name = device_data.get("name", f"Thermostat {device_id}")
        self._attr_name = f"{gateway_name} {device_name}"

        # Set unique_id with gateway to create new entities
        # Old format: salus_it600_cloud_{device_id}
        # New format: salus_it600_cloud_{gateway_id}_{device_id}
        self._attr_unique_id = f"{DOMAIN}_{gateway_id}_{device_id}"

        # Set explicit object_id to ensure unique entity IDs
        # This prevents conflicts when multiple gateways exist
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
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        data = self.device_data

        # First, try shadow properties (from device_shadows API)
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            # Look for LocalTemperature_x100 in shadow properties
            temp_x100 = shadow_props.get("ep9:sIT600TH:LocalTemperature_x100")
            if temp_x100 is not None:
                return temp_x100 / 100.0

        # Fallback to other possible fields
        for field in ["current_temperature", "LocalTemperature", "temperature"]:
            if field in data:
                temp = data[field]
                if isinstance(temp, int) and temp > 100:
                    return temp / 100.0
                return float(temp)

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        data = self.device_data

        # First, try shadow properties (from device_shadows API)
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            # Look for HeatingSetpoint_x100 in shadow properties
            temp_x100 = shadow_props.get("ep9:sIT600TH:HeatingSetpoint_x100")
            if temp_x100 is not None:
                return temp_x100 / 100.0

        # Fallback to other possible fields
        for field in ["target_temperature", "HeatingSetpoint", "setpoint"]:
            if field in data:
                temp = data[field]
                if isinstance(temp, int) and temp > 100:
                    return temp / 100.0
                return float(temp)

        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        data = self.device_data

        # First, try shadow properties (from device_shadows API)
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            # Check HoldType first - Standby/Frost mode (7) should be OFF
            hold_type = shadow_props.get("ep9:sIT600TH:HoldType")
            if hold_type == 7:  # Standby/Frost mode
                return HVACMode.OFF

            # Check SystemMode (0 = off, 4 = heat)
            system_mode = shadow_props.get("ep9:sIT600TH:SystemMode")
            if system_mode == 0:
                return HVACMode.OFF
            # mode 4 = heat, default to HEAT
            return HVACMode.HEAT

        # Fallback to other possible fields
        is_on = data.get("is_on", True)
        mode = data.get("mode", "").lower()

        if not is_on or mode == "off":
            return HVACMode.OFF

        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action (heating/idle)."""
        # First check if HVAC mode is OFF
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        # Then check running state
        data = self.device_data
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            # Check RunningState (1 = heating, 0 = idle)
            running_state = shadow_props.get("ep9:sIT600TH:RunningState")
            if running_state == 1:
                return HVACAction.HEATING
            elif running_state == 0:
                return HVACAction.IDLE

        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        data = self.device_data

        # Get HoldType from shadow properties
        shadow_props = data.get("_shadow_properties", {})
        if shadow_props:
            hold_type = shadow_props.get("ep9:sIT600TH:HoldType")
            if hold_type is not None:
                return HOLDTYPE_TO_PRESET.get(hold_type, PRESET_MANUAL)

        # Default to manual if unknown
        return PRESET_MANUAL

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        _LOGGER.info("Setting temperature for %s to %.1f°C", self._attr_name, temperature)

        try:
            await self.coordinator.gateway.set_temperature(self._device_code, temperature)

            # Request immediate coordinator refresh to get updated state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to set temperature: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to set temperature: {err}") from err

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in PRESET_TO_HOLDTYPE:
            _LOGGER.error("Unknown preset mode: %s", preset_mode)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Unknown preset mode: {preset_mode}")

        hold_type = PRESET_TO_HOLDTYPE[preset_mode]
        _LOGGER.info("Setting preset mode for %s to %s (HoldType=%d)",
                     self._attr_name, preset_mode, hold_type)

        try:
            await self.coordinator.gateway.set_hold_mode(self._device_code, hold_type)

            # Request immediate coordinator refresh to get updated state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to set preset mode: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to set preset mode: {err}") from err

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode.

        Maps HVAC modes to preset modes:
        - OFF → Away/Frost mode (HoldType=7)
        - HEAT → Schedule mode (HoldType=0)
        """
        _LOGGER.info("Setting HVAC mode for %s to %s", self._attr_name, hvac_mode)

        # Map HVAC mode to HoldType
        if hvac_mode == HVACMode.OFF:
            hold_type = 7  # Frost/Away mode
            mode_name = "frost/away"
        elif hvac_mode == HVACMode.HEAT:
            hold_type = 0  # Schedule mode
            mode_name = "schedule"
        else:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        try:
            _LOGGER.debug("Setting HVAC mode %s → HoldType %d (%s)", hvac_mode, hold_type, mode_name)
            await self.coordinator.gateway.set_hold_mode(self._device_code, hold_type)

            # Request immediate coordinator refresh to get updated state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to set HVAC mode: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to set HVAC mode: {err}") from err

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self.device_data
        shadow_props = data.get("_shadow_properties", {})

        attrs = {}

        # Add hold type info
        hold_type = shadow_props.get("ep9:sIT600TH:HoldType")
        if hold_type is not None:
            hold_type_names = {
                0: "Schedule",
                2: "Manual Hold",
                7: "Frost Protection"
            }
            attrs["hold_type"] = hold_type_names.get(hold_type, f"Unknown ({hold_type})")

        # Add system mode
        system_mode = shadow_props.get("ep9:sIT600TH:SystemMode")
        if system_mode is not None:
            system_mode_names = {
                0: "Off",
                1: "Auto",
                4: "Heat"
            }
            attrs["system_mode"] = system_mode_names.get(system_mode, f"Unknown ({system_mode})")

        # Add battery level if available
        battery_level = shadow_props.get("ep9:sBasicS:BatteryVoltage")
        if battery_level is not None:
            attrs["battery_voltage"] = f"{battery_level / 10:.1f}V"

        # Add running state
        running_state = shadow_props.get("ep9:sIT600TH:RunningState")
        if running_state is not None:
            attrs["running_state"] = "Heating" if running_state == 1 else "Idle"

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
