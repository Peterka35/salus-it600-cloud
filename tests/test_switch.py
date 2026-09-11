"""Tests for Salus relay entities."""

from unittest.mock import MagicMock, patch

from custom_components.salus_it600_cloud import switch
from custom_components.salus_it600_cloud.switch import SalusCloudSwitch

from . import fixtures
from .helpers import CALL_LATER, FakeApi, create_coordinator


async def test_setup_creates_relays_only() -> None:
    """Switch entities are created for relays and plugs, not for thermostats."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await switch.async_setup_entry(MagicMock(), entry, add_entities)

    entities = add_entities.call_args.args[0]
    assert [entity.unique_id for entity in entities] == [f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.RELAY_ID}"]
    assert entities[0].name == "Apartmán A Topení pokoj"


async def test_relay_state() -> None:
    """Relay state comes from reported on/off property."""

    api = FakeApi()
    api.shadows[fixtures.RELAY_CODE] = fixtures.relay_shadow(1)
    coordinator, _, _ = await create_coordinator(api)

    assert SalusCloudSwitch(coordinator, fixtures.RELAY_ID, coordinator.data[fixtures.RELAY_ID]).is_on is True


async def test_turn_on_relay_shows_state_immediately() -> None:
    """Relay command targets only the relay (never synchronized) and its state is shown right away."""

    coordinator, connection, _ = await create_coordinator(sync=True)
    entity = SalusCloudSwitch(coordinator, fixtures.RELAY_ID, coordinator.data[fixtures.RELAY_ID])
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    with patch(CALL_LATER):
        await entity.async_turn_on()

    assert connection.published == [(fixtures.RELAY_CODE, "11", {"ep9:sOnOffS:SetOnOff": 1})]
    assert entity.is_on is True
