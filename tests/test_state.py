"""Tests for device state tracking."""

from custom_components.salus_it600_cloud.state import DeviceStateStore, extract_reported

THERMOSTAT = "SAL3AG1GW-001E5E000002-SQ610RFNH-001E5E0000000E05"
RELAY = "SAL3AG1GW-001E5E000002-SR600-001E5E0000000F06"
HOLD = "ep9:sIT600TH:HoldType"
SETPOINT = "ep9:sIT600TH:HeatingSetpoint_x100"
TEMPERATURE = "ep9:sIT600TH:LocalTemperature_x100"


def _store() -> DeviceStateStore:
    return DeviceStateStore(pending_timeout=60, max_age=600)


def test_extract_reported_returns_index_and_properties() -> None:
    """Reported properties are nested under the device index of the shadow document."""

    shadow = {
        "state": {
            "desired": {"11": {"properties": {"ep9:sIT600TH:SetHoldType": 7}}},
            "reported": {"11": {"properties": {HOLD: 7, TEMPERATURE: 2200}, "model": "SQ610RFNH"}},
        },
        "version": 8800,
        "timestamp": 1789140103,
    }

    assert extract_reported(shadow) == ("11", {HOLD: 7, TEMPERATURE: 2200})


def test_extract_reported_of_gateway_shadow() -> None:
    """Gateway shadow uses its own device index."""

    shadow = {"state": {"reported": {"000000000001": {"properties": {"ep0:sRule:TriggerRule": ""}}}}}

    assert extract_reported(shadow) == ("000000000001", {"ep0:sRule:TriggerRule": ""})


def test_extract_reported_without_reported_state() -> None:
    """Shadow without reported device properties yields nothing."""

    assert extract_reported({"state": {"desired": {"11": {"properties": {HOLD: 0}}}}}) is None
    assert extract_reported({}) is None


def test_reported_properties_are_merged() -> None:
    """Later reports update changed properties and keep the others."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 7, TEMPERATURE: 2200}, now=0)
    store.update_reported(THERMOSTAT, "11", {TEMPERATURE: 2150}, now=10)

    assert store.properties(THERMOSTAT, now=10) == {HOLD: 7, TEMPERATURE: 2150}
    assert store.index(THERMOSTAT) == "11"


def test_pending_change_hides_stale_report() -> None:
    """A report sent before the device applied a command does not revert the commanded state."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 0, SETPOINT: 2100}, now=0)
    store.set_pending(THERMOSTAT, {"ep9:sIT600TH:SetHoldType": 7}, now=1)

    store.update_reported(THERMOSTAT, "11", {HOLD: 0, SETPOINT: 2100}, now=2)

    assert store.properties(THERMOSTAT, now=2) == {HOLD: 7, SETPOINT: 2100}


def test_confirmed_pending_change_no_longer_overrides_reports() -> None:
    """Once the device reports the commanded value, later changes made elsewhere are shown."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 0}, now=0)
    store.set_pending(THERMOSTAT, {"ep9:sIT600TH:SetHoldType": 7}, now=1)
    store.update_reported(THERMOSTAT, "11", {HOLD: 7}, now=5)

    store.update_reported(THERMOSTAT, "11", {HOLD: 2}, now=20)

    assert store.properties(THERMOSTAT, now=20) == {HOLD: 2}


def test_pending_change_expires() -> None:
    """A command the device never applies stops overriding reports after the pending timeout."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 0}, now=0)
    store.set_pending(THERMOSTAT, {"ep9:sIT600TH:SetHoldType": 7}, now=1)

    assert store.properties(THERMOSTAT, now=60) == {HOLD: 7}
    assert store.properties(THERMOSTAT, now=62) == {HOLD: 0}


def test_pending_setpoint_and_switch_use_reported_property_names() -> None:
    """Commanded setpoint and relay state are shown under the properties the entities read."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {SETPOINT: 2100}, now=0)
    store.update_reported(RELAY, "11", {"ep9:sOnOffS:OnOff": 0}, now=0)

    store.set_pending(THERMOSTAT, {"ep9:sIT600TH:SetHeatingSetpoint_x100": 2250}, now=1)
    store.set_pending(RELAY, {"ep9:sOnOffS:SetOnOff": 1}, now=1)

    assert store.properties(THERMOSTAT, now=2) == {SETPOINT: 2250}
    assert store.properties(RELAY, now=2) == {"ep9:sOnOffS:OnOff": 1}


def test_freshness_of_device_data() -> None:
    """Device data counts as fresh until max age passes since the last report."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 7}, now=100)

    assert store.is_fresh(THERMOSTAT, now=700) is True
    assert store.is_fresh(THERMOSTAT, now=701) is False
    assert store.is_fresh(RELAY, now=100) is False


def test_pending_change_does_not_refresh_data() -> None:
    """Sending a command does not make stale device data look fresh."""

    store = _store()
    store.update_reported(THERMOSTAT, "11", {HOLD: 0}, now=0)
    store.set_pending(THERMOSTAT, {"ep9:sIT600TH:SetHoldType": 7}, now=650)

    assert store.is_fresh(THERMOSTAT, now=650) is False
