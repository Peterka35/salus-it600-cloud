"""Test helpers: fake Salus Cloud API, fake MQTT connection and coordinator factory."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.salus_it600_cloud.api import (
    GatewayInfo,
    SalusCloudConnectionError,
    SalusMetadata,
)
from custom_components.salus_it600_cloud.const import CONF_SYNC_MODES
from custom_components.salus_it600_cloud.coordinator import SalusCloudCoordinator

from . import fixtures

CALL_LATER = "custom_components.salus_it600_cloud.coordinator.async_call_later"


def metadata() -> SalusMetadata:
    """Return metadata of the fixture gateway."""

    items = fixtures.slider_details()["data"]["items"]
    return SalusMetadata(
        gateways=[GatewayInfo(id=fixtures.GATEWAY_ID, name=fixtures.GATEWAY_NAME, device_code=fixtures.GATEWAY_CODE)],
        devices=[{**item, "_gateway_id": fixtures.GATEWAY_ID} for item in items if "rule_trigger_key" not in item],
        rules=[{**item, "_gateway_id": fixtures.GATEWAY_ID} for item in items if "rule_trigger_key" in item],
    )


class FakeApi:
    """Salus Cloud API returning fixture data."""

    def __init__(self) -> None:
        self.metadata_calls = 0
        self.metadata_error: Exception | None = None
        self.shadows: dict[str, dict[str, Any]] | Exception = {
            fixtures.THERMOSTAT_CODE: fixtures.thermostat_shadow(hold_type=0),
            fixtures.THERMOSTAT_2_CODE: fixtures.thermostat_shadow(hold_type=0, temperature_x100=2300),
            fixtures.RELAY_CODE: fixtures.relay_shadow(0),
        }

    async def fetch_metadata(self) -> SalusMetadata:
        self.metadata_calls += 1
        if self.metadata_error:
            raise self.metadata_error
        return metadata()

    async def get_device_shadows(self, device_codes: list[str]) -> dict[str, dict[str, Any]]:
        if isinstance(self.shadows, Exception):
            raise self.shadows
        return {code: shadow for code, shadow in self.shadows.items() if code in device_codes}

    async def get_iot_credentials(self) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeConnection:
    """MQTT connection recording published shadow updates."""

    def __init__(self, fail_codes: set[str] | None = None) -> None:
        self.fail_codes = fail_codes or set()
        self.published: list[tuple[str, str, dict[str, Any]]] = []
        self.kwargs: dict[str, Any] = {}
        self.started_with: list[str] | None = None
        self.stopped = False

    def factory(self, **kwargs: Any) -> "FakeConnection":
        self.kwargs = kwargs
        return self

    async def async_start(self, device_codes: list[str]) -> None:
        self.started_with = list(device_codes)

    async def async_stop(self) -> None:
        self.stopped = True

    def set_device_codes(self, device_codes: list[str]) -> None:
        return None

    async def async_publish_shadow(self, device_code: str, device_index: str, properties: dict[str, Any]) -> None:
        if device_code in self.fail_codes:
            raise SalusCloudConnectionError("not confirmed")
        self.published.append((device_code, device_index, properties))


async def create_coordinator(
    api: FakeApi | None = None, *, sync: bool = False, connection: FakeConnection | None = None
) -> tuple[SalusCloudCoordinator, FakeConnection, list[float]]:
    """Return coordinator after its first refresh with started (fake) MQTT connection and its clock."""

    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    entry = MagicMock()
    entry.entry_id = "salus-entry"
    entry.options = {CONF_SYNC_MODES: sync}
    clock = [0.0]
    connection = connection or FakeConnection()
    coordinator = SalusCloudCoordinator(
        hass, entry, api or FakeApi(), connection_factory=connection.factory, clock=lambda: clock[0]
    )
    coordinator.data = await coordinator._async_update_data()
    await coordinator.async_start_connection()
    return coordinator, connection, clock
