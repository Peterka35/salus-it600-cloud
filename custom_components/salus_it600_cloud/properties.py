"""Shadow property names reported and accepted by the supported Salus device families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PropertyNames:
    """Property names of one device family's shadow document."""

    family: str
    hold_type: str
    system_mode: str
    running_state: str
    local_temperature: str
    heating_setpoint: str
    battery_voltage: str
    on_off: str
    set_hold_type: str
    set_heating_setpoint: str
    set_system_mode: str
    set_on_off: str
    # Some thermostats change HVAC mode through SystemMode instead of HoldType
    hvac_mode_uses_system_mode: bool = False


# Devices reporting under ep9, e.g. SQ610RF, HTRP-RF, TS600 and the relays
IT600 = PropertyNames(
    family="iT600",
    hold_type="ep9:sIT600TH:HoldType",
    system_mode="ep9:sIT600TH:SystemMode",
    running_state="ep9:sIT600TH:RunningState",
    local_temperature="ep9:sIT600TH:LocalTemperature_x100",
    heating_setpoint="ep9:sIT600TH:HeatingSetpoint_x100",
    battery_voltage="ep9:sBasicS:BatteryVoltage",
    on_off="ep9:sOnOffS:OnOff",
    set_hold_type="ep9:sIT600TH:SetHoldType",
    set_heating_setpoint="ep9:sIT600TH:SetHeatingSetpoint_x100",
    set_system_mode="ep9:sIT600TH:SetSystemMode",
    set_on_off="ep9:sOnOffS:SetOnOff",
)

# Devices reporting under ep1/ep2, e.g. IT800TX. They never report the ep9 property names.
IT800 = PropertyNames(
    family="iT800",
    hold_type="ep1:sComm:HoldType",
    system_mode="ep1:sTherS:SystemMode",
    running_state="ep1:sTherS:RunningState",
    local_temperature="ep1:sTherS:LocalTemperature_x100",
    heating_setpoint="ep1:sTherS:HeatingSetpoint_x100",
    battery_voltage="ep1:sPowerS:BatteryVoltage_x10",
    on_off="ep2:sOnOffS:OnOff",
    set_hold_type="ep1:sComm:SetHoldType",
    set_heating_setpoint="ep1:sTherS:SetHeatingSetpoint_x100",
    set_system_mode="ep1:sTherS:SetSystemMode",
    set_on_off="ep2:sOnOffS:SetOnOff",
    hvac_mode_uses_system_mode=True,
)

DEFAULT_PROPERTY_NAMES = IT600

# A single ep1 or ep2 property is enough to identify the family; the ep9 defaults stay in place
# for the already supported devices, whose shadows do not contain them.
_IT800_PREFIXES = ("ep1:sTherS:", "ep1:sComm:", "ep1:sPowerS:", "ep2:sOnOffS:")


def detect_property_names(properties: dict[str, Any]) -> PropertyNames:
    """Return the property names of the family that reported these shadow properties."""
    if any(name.startswith(_IT800_PREFIXES) for name in properties):
        return IT800
    return DEFAULT_PROPERTY_NAMES


def property_names_of(device: dict[str, Any]) -> PropertyNames:
    """Return the property names resolved for a device."""
    names = device.get("_property_names")
    return names if isinstance(names, PropertyNames) else DEFAULT_PROPERTY_NAMES
