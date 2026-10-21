"""Tests for resolving the shadow property names of Salus device families."""

from custom_components.salus_it600_cloud.properties import (
    IT600,
    IT800,
    detect_property_names,
)

from . import fixtures


def test_ep9_properties_are_the_default() -> None:
    """Devices without ep1/ep2 properties keep the already supported ep9 names."""

    assert detect_property_names({"ep9:sIT600TH:HoldType": 0}) is IT600
    assert detect_property_names({}) is IT600


def test_ep1_thermostat_properties_are_detected() -> None:
    """A thermostat reporting ep1 properties is identified as an iT800 device."""

    properties = fixtures.it800_thermostat_shadow(hold_type=0)["state"]["reported"]["11"]["properties"]

    assert detect_property_names(properties) is IT800


def test_ep2_switch_properties_are_detected() -> None:
    """A relay reporting ep2 properties is identified as an iT800 device."""

    properties = fixtures.it800_relay_shadow(on_off=1)["state"]["reported"]["11"]["properties"]

    assert detect_property_names(properties) is IT800


def test_ep1_and_ep9_properties_prefer_the_reported_ep1_names() -> None:
    """When a shadow contains both families, the names the device actually reports win."""

    properties = {
        "ep9:sIT600TH:HoldType": 0,
        "ep9:sIT600TH:LocalTemperature_x100": 2000,
        "ep1:sComm:HoldType": 2,
    }

    assert detect_property_names(properties) is IT800
