"""Climate platform for Salus iT600 Cloud thermostats."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import HOLD_TYPE_MANUAL, HOLD_TYPE_SCHEDULE, HOLD_TYPE_STANDBY
from .coordinator import SalusCloudCoordinator
from .devices import is_climate_device
from .entity import SalusEntity

PRESET_SCHEDULE = "schedule"
PRESET_MANUAL = "manual"
PRESET_AWAY = "away"  # Stand-by with frost protection

PRESET_TO_HOLD_TYPE = {
    PRESET_SCHEDULE: HOLD_TYPE_SCHEDULE,
    PRESET_MANUAL: HOLD_TYPE_MANUAL,
    PRESET_AWAY: HOLD_TYPE_STANDBY,
}
HOLD_TYPE_TO_PRESET = {hold_type: preset for preset, hold_type in PRESET_TO_HOLD_TYPE.items()}
HOLD_TYPE_NAMES = {
    HOLD_TYPE_SCHEDULE: "Schedule",
    HOLD_TYPE_MANUAL: "Manual Hold",
    HOLD_TYPE_STANDBY: "Frost Protection",
}
SYSTEM_MODE_NAMES = {0: "Off", 1: "Auto", 4: "Heat"}

HOLD_TYPE = "ep9:sIT600TH:HoldType"
SYSTEM_MODE = "ep9:sIT600TH:SystemMode"
RUNNING_STATE = "ep9:sIT600TH:RunningState"
LOCAL_TEMPERATURE = "ep9:sIT600TH:LocalTemperature_x100"
HEATING_SETPOINT = "ep9:sIT600TH:HeatingSetpoint_x100"
BATTERY_VOLTAGE = "ep9:sBasicS:BatteryVoltage"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud thermostats."""
    coordinator: SalusCloudCoordinator = entry.runtime_data
    async_add_entities(
        [
            SalusCloudClimate(coordinator, device_id, device)
            for device_id, device in coordinator.data.items()
            if is_climate_device(device)
        ]
    )


class SalusCloudClimate(SalusEntity, ClimateEntity):
    """Salus iT600 thermostat."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_SCHEDULE, PRESET_MANUAL, PRESET_AWAY]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0

    def _temperature(self, name: str) -> float | None:
        value = self.shadow_properties.get(name)
        return value / 100 if value is not None else None

    @property
    def current_temperature(self) -> float | None:
        """Return the measured temperature."""
        return self._temperature(LOCAL_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._temperature(HEATING_SETPOINT)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return off for stand-by or system mode off, heat otherwise."""
        properties = self.shadow_properties
        if not properties:
            return None
        if properties.get(HOLD_TYPE) == HOLD_TYPE_STANDBY or properties.get(SYSTEM_MODE) == 0:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return whether the thermostat is heating right now."""
        hvac_mode = self.hvac_mode
        if hvac_mode is None:
            return None
        if hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self.shadow_properties.get(RUNNING_STATE) == 1 else HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return preset matching the hold type."""
        hold_type = self.shadow_properties.get(HOLD_TYPE)
        if hold_type is None:
            return None
        return HOLD_TYPE_TO_PRESET.get(hold_type, PRESET_MANUAL)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_temperature(self._device_id, temperature)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset (synchronized across the gateway when enabled)."""
        await self.coordinator.async_set_hold_type(self._device_id, PRESET_TO_HOLD_TYPE[preset_mode])

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set off (stand-by) or heat (follow schedule), synchronized across the gateway when enabled."""
        hold_type = HOLD_TYPE_STANDBY if hvac_mode == HVACMode.OFF else HOLD_TYPE_SCHEDULE
        await self.coordinator.async_set_hold_type(self._device_id, hold_type)

    async def async_turn_on(self) -> None:
        """Turn heating on (follow schedule)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn heating off (stand-by)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return hold type, system mode, battery voltage and running state."""
        properties = self.shadow_properties
        attributes: dict[str, Any] = {}
        if (hold_type := properties.get(HOLD_TYPE)) is not None:
            attributes["hold_type"] = HOLD_TYPE_NAMES.get(hold_type, f"Unknown ({hold_type})")
        if (system_mode := properties.get(SYSTEM_MODE)) is not None:
            attributes["system_mode"] = SYSTEM_MODE_NAMES.get(system_mode, f"Unknown ({system_mode})")
        if (battery_voltage := properties.get(BATTERY_VOLTAGE)) is not None:
            attributes["battery_voltage"] = f"{battery_voltage / 10:.1f}V"
        if (running_state := properties.get(RUNNING_STATE)) is not None:
            attributes["running_state"] = "Heating" if running_state == 1 else "Idle"
        return attributes
