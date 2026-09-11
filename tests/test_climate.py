"""Tests for Salus thermostat entities."""

from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode

from custom_components.salus_it600_cloud import climate
from custom_components.salus_it600_cloud.climate import SalusCloudClimate

from . import fixtures
from .helpers import CALL_LATER, FakeApi, create_coordinator


def _entity(coordinator: object, device_id: str = fixtures.THERMOSTAT_ID) -> SalusCloudClimate:
    entity = SalusCloudClimate(coordinator, device_id, coordinator.data[device_id])
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


async def test_setup_creates_thermostats_only() -> None:
    """Climate entities are created for thermostats, not for relays or the gateway."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await climate.async_setup_entry(MagicMock(), entry, add_entities)

    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.THERMOSTAT_ID}",
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.THERMOSTAT_2_ID}",
    ]


async def test_entity_name_is_unchanged() -> None:
    """Existing names (and therefore entity ids) of thermostats stay the same."""

    coordinator, _, _ = await create_coordinator()

    assert _entity(coordinator).name == "Apartmán A Termostat pokoj"


async def test_schedule_mode_state() -> None:
    """Thermostat following its schedule is heating with schedule preset."""

    api = FakeApi()
    api.shadows[fixtures.THERMOSTAT_CODE] = fixtures.thermostat_shadow(
        hold_type=0, temperature_x100=2250, setpoint_x100=2100
    )
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.HEAT, "schedule", HVACAction.IDLE)
    assert (entity.current_temperature, entity.target_temperature) == (22.5, 21.0)


async def test_manual_mode_actively_heating() -> None:
    """Running state reports active heating."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = 1
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.HEAT, "manual", HVACAction.HEATING)


async def test_standby_mode_state() -> None:
    """Thermostat in stand-by (frost protection) is off."""

    api = FakeApi()
    api.shadows[fixtures.THERMOSTAT_CODE] = fixtures.thermostat_shadow(hold_type=7)
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.OFF, "away", HVACAction.OFF)


async def test_thermostat_without_reported_state_is_unavailable() -> None:
    """A thermostat without state data is unavailable instead of showing made-up heat/manual values."""

    api = FakeApi()
    del api.shadows[fixtures.THERMOSTAT_CODE]
    coordinator, _, _ = await create_coordinator(api)

    assert _entity(coordinator).available is False
    assert _entity(coordinator, fixtures.THERMOSTAT_2_ID).available is True


@pytest.mark.parametrize(
    ("action", "hold_type"),
    [
        (lambda entity: entity.async_set_hvac_mode(HVACMode.OFF), 7),
        (lambda entity: entity.async_set_hvac_mode(HVACMode.HEAT), 0),
        (lambda entity: entity.async_set_preset_mode("schedule"), 0),
        (lambda entity: entity.async_set_preset_mode("manual"), 2),
        (lambda entity: entity.async_set_preset_mode("away"), 7),
        (lambda entity: entity.async_turn_off(), 7),
        (lambda entity: entity.async_turn_on(), 0),
    ],
    ids=["hvac-off", "hvac-heat", "preset-schedule", "preset-manual", "preset-away", "turn-off", "turn-on"],
)
async def test_mode_commands_set_hold_type(
    action: Callable[[SalusCloudClimate], Awaitable[None]], hold_type: int
) -> None:
    """Mode changes are sent as hold type of the thermostat."""

    coordinator, connection, _ = await create_coordinator()
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await action(entity)

    assert connection.published == [(fixtures.THERMOSTAT_CODE, "11", {"ep9:sIT600TH:SetHoldType": hold_type})]


async def test_turning_off_one_thermostat_turns_off_all_with_sync() -> None:
    """With synchronization, turning off one thermostat turns off every thermostat of the apartment at once."""

    coordinator, connection, _ = await create_coordinator(sync=True)
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await entity.async_turn_off()

    assert sorted(code for code, _, _ in connection.published) == sorted(
        [fixtures.THERMOSTAT_CODE, fixtures.THERMOSTAT_2_CODE]
    )
    assert _entity(coordinator, fixtures.THERMOSTAT_2_ID).hvac_mode == HVACMode.OFF
    assert entity.supported_features & ClimateEntityFeature.TURN_OFF


async def test_set_temperature_shows_new_target_immediately() -> None:
    """New target temperature is shown right after the command, before the device reports it."""

    coordinator, connection, _ = await create_coordinator()
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await entity.async_set_temperature(temperature=21.5)

    assert connection.published == [
        (
            fixtures.THERMOSTAT_CODE,
            "11",
            {
                "ep9:sIT600TH:SetHeatingSetpoint_x100": 2150,
                "ep9:sIT600TH:SetHoldType": 2,
                "ep9:sIT600TH:SetSystemMode": 4,
            },
        )
    ]
    assert entity.target_temperature == 21.5
    assert entity.preset_mode == "manual"
