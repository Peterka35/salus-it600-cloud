"""API payload fixtures mirroring the structure of Salus Cloud responses (identifiers and personal data are made up)."""

import json
from typing import Any

GATEWAY_ID = "10000000-0000-4000-8000-000000000001"
GATEWAY_CODE = "SAU2AG1_GW-001E5E000001"
GATEWAY_NAME = "Apartmán A"
THERMOSTAT_ID = "20000000-0000-4000-8000-000000000001"
THERMOSTAT_CODE = "SAU2AG1_GW-001E5E000001-SQ610RF-001E5E0000000B02"
THERMOSTAT_2_ID = "20000000-0000-4000-8000-000000000002"
THERMOSTAT_2_CODE = "SAU2AG1_GW-001E5E000001-SQ610RF-001E5E0000000A01"
RELAY_ID = "30000000-0000-4000-8000-000000000001"
RELAY_CODE = "SAU2AG1_GW-001E5E000001-SR600-001E5E0000000C03"
RULE_ID = "40000000-0000-4000-8000-000000000001"
RULE_TRIGGER_KEY = "ruleTriggerKey-00000000000000000000000000000001"
AUTO_RULE_ID = "40000000-0000-4000-8000-000000000002"
GUEST_EMAIL = "guest@example.com"

OCCUPANT = {
    "id": "50000000-0000-4000-8000-000000000001",
    "email": GUEST_EMAIL,
    "first_name": "Jan",
    "last_name": "Novák",
    "phone_number": "+420600000000",
}

GATEWAY = {
    "id": GATEWAY_ID,
    "device_code": GATEWAY_CODE,
    "category": {"name": None, "category_id": "1"},
    "model": "SAU2AG1_GW",
    "name": GATEWAY_NAME,
    "plan_code": None,
    "occupants_permissions": {
        "gateway_id": GATEWAY_ID,
        "invitation_email": GUEST_EMAIL,
        "access_level": "O",
        "receiver_occupant": OCCUPANT,
        "sharer_occupant": OCCUPANT,
    },
}


def slider_list() -> dict[str, Any]:
    """Return /occupants/slider_list response."""

    return {
        "data": [
            {
                "id": GATEWAY_ID,
                "type": "gateway",
                "gateway": GATEWAY,
                "coordinator_device": {
                    "id": "60000000-0000-4000-8000-000000000001",
                    "device_code": f"{GATEWAY_CODE}-SAU2AG1_ZC-001E5E0000000D04",
                    "name": GATEWAY_NAME,
                    "model": "SAU2AG1_ZC",
                },
                "rule_group": None,
            }
        ]
    }


def _device(device_id: str, code: str, name: str, model: str, category: str) -> dict[str, Any]:
    return {
        "id": device_id,
        "device_code": code,
        "name": name,
        "model": model,
        "dashboard_attributes": {"id": f"dash-{device_id}", "type": "device", "grid_order": "6"},
        "devices_metadata": [],
        "category": {"name": category, "category_id": "13"},
        "alert_communication_configs": [],
    }


def slider_details() -> dict[str, Any]:
    """Return /occupants/slider_details response for the gateway."""

    return {
        "data": {
            "id": GATEWAY_ID,
            "type": "gateway",
            "gateway": GATEWAY,
            "items": [
                _device(THERMOSTAT_ID, THERMOSTAT_CODE, "Termostat pokoj", "SQ610RF", "Quantum Thermostats"),
                _device(THERMOSTAT_2_ID, THERMOSTAT_2_CODE, "Termostat koupelna", "SQ610RF", "Quantum Thermostats"),
                _device(RELAY_ID, RELAY_CODE, "Topení pokoj", "SR600", "Smart Relays"),
                {
                    "id": GATEWAY_ID,
                    "device_code": GATEWAY_CODE,
                    "model": "SAU2AG1_GW",
                    "name": GATEWAY_NAME,
                    "plan_code": None,
                    "dashboard_attributes": {"id": "dash-gw", "type": "gateway", "grid_order": "t"},
                    "devices_metadata": [],
                    "category": {"name": None, "category_id": "1"},
                    "alert_communication_configs": [],
                    "rule_group": None,
                    "occupants_permissions": GATEWAY["occupants_permissions"],
                },
                {
                    "id": RULE_ID,
                    "rule_trigger_key": RULE_TRIGGER_KEY,
                    "rule": {
                        "key": "00000000000000000000000000000001",
                        "name": "Vypnout topení (Stand-by)",
                        "action": [
                            {
                                "op": "SetValue",
                                "parameters": [
                                    {"string": "001e5e0000000a01"},
                                    {"string": "ep_9:sIT600TH:SetHoldType"},
                                    {"number": 7},
                                ],
                            }
                        ],
                        "active": True,
                        "condition": {"op": "OR", "parameters": []},
                    },
                    "dashboard_attributes": {"id": "dash-rule", "type": "one_touch_rule", "grid_order": "w"},
                },
                {
                    "id": AUTO_RULE_ID,
                    "rule_trigger_key": "ruleTriggerKey-00000000000000000000000000000002",
                    "rule": {
                        "key": "auto-rule-key",
                        "name": "_P65FD8T6S-001e5e0000000b02-VR00ZN000000001-Heat-ON",
                        "action": [],
                        "active": True,
                        "condition": {"op": "OR", "parameters": []},
                        "properties": [],
                    },
                    "dashboard_attributes": {"type": "one_touch_rule"},
                },
            ],
        }
    }


def thermostat_shadow(hold_type: int, temperature_x100: int = 2200, setpoint_x100: int = 2100) -> dict[str, Any]:
    """Return shadow document of a thermostat."""

    return {
        "state": {
            "desired": {"11": {"properties": {"ep9:sIT600TH:SetHoldType": hold_type}}},
            "reported": {
                "11": {
                    "properties": {
                        "ep9:sIT600TH:HoldType": hold_type,
                        "ep9:sIT600TH:SystemMode": 4,
                        "ep9:sIT600TH:RunningState": 0,
                        "ep9:sIT600TH:LocalTemperature_x100": temperature_x100,
                        "ep9:sIT600TH:HeatingSetpoint_x100": setpoint_x100,
                        "ep9:sBasicS:BatteryVoltage": 30,
                    },
                    "model": "SQ610RF",
                }
            },
        },
        "version": 8800,
        "timestamp": 1789140103,
    }


def relay_shadow(on_off: int) -> dict[str, Any]:
    """Return shadow document of a relay."""

    return {
        "state": {"reported": {"11": {"properties": {"ep9:sOnOffS:OnOff": on_off}, "model": "SR600"}}},
        "version": 120,
        "timestamp": 1789140103,
    }


def device_shadows(shadows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return /devices/device_shadows response with stringified shadow payloads."""

    return {
        "data": {
            "success_list": [{"device_code": code, "payload": json.dumps(shadow)} for code, shadow in shadows.items()]
        }
    }
