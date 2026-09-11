"""Data coordinator for Salus iT600 Cloud: device states, commands and thermostat mode synchronization."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GatewayInfo,
    SalusCloudApi,
    SalusCloudAuthenticationError,
    SalusCloudConnectionError,
    SalusMetadata,
)
from .const import (
    CONF_SYNC_MODES,
    CONFIRM_REFRESH_DELAY_SECONDS,
    DEFAULT_SHADOW_INDEX,
    DOMAIN,
    GATEWAY_SHADOW_INDEX,
    HOLD_TYPE_MANUAL,
    METADATA_REFRESH_SECONDS,
    PENDING_TIMEOUT_SECONDS,
    PUSH_SCAN_INTERVAL_SECONDS,
    SCAN_INTERVAL_SECONDS,
    STALE_AFTER_SECONDS,
)
from .devices import is_climate_device
from .mqtt import SalusMqttConnection
from .state import DeviceStateStore, extract_reported

_LOGGER = logging.getLogger(__name__)

# Device from the Salus device list extended with "_gateway_id", "_shadow_properties",
# "_shadow_device_index" and "_fresh"
type SalusDevice = dict[str, Any]


class SalusCloudCoordinator(DataUpdateCoordinator[dict[str, SalusDevice]]):
    """Keeps Salus device data up to date and sends commands to devices."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: SalusCloudApi,
        *,
        connection_factory: Callable[..., SalusMqttConnection] = SalusMqttConnection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self._connection_factory = connection_factory
        self._clock = clock
        self._store = DeviceStateStore(pending_timeout=PENDING_TIMEOUT_SECONDS, max_age=STALE_AFTER_SECONDS)
        self._metadata: SalusMetadata | None = None
        self._metadata_fetched_at = 0.0
        self._connection: SalusMqttConnection | None = None
        self._cancel_confirmation: CALLBACK_TYPE | None = None
        self.push_available = False
        # Gateway id -> device registry id of the gateway device
        self.gateway_device_ids: dict[str, str] = {}

    @property
    def sync_modes(self) -> bool:
        """Return whether a mode change is applied to all thermostats of the gateway."""
        return bool(self.config_entry.options.get(CONF_SYNC_MODES, False))

    @property
    def gateways(self) -> list[GatewayInfo]:
        """Return gateways of the account."""
        return self._metadata.gateways if self._metadata else []

    @property
    def rules(self) -> list[dict[str, Any]]:
        """Return OneTouch rules of all gateways."""
        return self._metadata.rules if self._metadata else []

    def get_gateway(self, gateway_id: str) -> GatewayInfo | None:
        """Return gateway by id."""
        return next((gateway for gateway in self.gateways if gateway.id == gateway_id), None)

    def get_device(self, device_id: str) -> SalusDevice | None:
        """Return current data of a device."""
        return (self.data or {}).get(device_id)

    def device_info(self, device: SalusDevice) -> DeviceInfo:
        """Return device registry info of a device linked to its gateway."""
        info = DeviceInfo(
            identifiers={(DOMAIN, device["id"])},
            name=device.get("name") or device["id"],
            manufacturer="Salus",
            model=device.get("model") or "iT600",
        )
        if via_device_id := self.gateway_device_ids.get(device.get("_gateway_id", "")):
            info["via_device_id"] = via_device_id
        return info

    def _device_codes(self) -> list[str]:
        devices = self._metadata.devices if self._metadata else []
        return [device["device_code"] for device in devices if device.get("device_code")]

    async def _async_update_data(self) -> dict[str, SalusDevice]:
        now = self._clock()
        try:
            if self._metadata is None or now - self._metadata_fetched_at >= METADATA_REFRESH_SECONDS:
                await self._async_refresh_metadata(now)
            try:
                shadows = await self.api.get_device_shadows(self._device_codes())
            except SalusCloudConnectionError as err:
                if not any(self._store.is_fresh(code, now) for code in self._device_codes()):
                    raise UpdateFailed(f"Error communicating with Salus Cloud: {err}") from err
                _LOGGER.warning("Failed to refresh device states, keeping last known states: %s", err)
                shadows = {}
        except SalusCloudAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        for device_code, shadow in shadows.items():
            if (reported := extract_reported(shadow)) is not None:
                self._store.update_reported(device_code, reported[0], reported[1], now)
        return self._build_data(now)

    async def _async_refresh_metadata(self, now: float) -> None:
        try:
            metadata = await self.api.fetch_metadata()
        except SalusCloudConnectionError as err:
            if self._metadata is None:
                raise UpdateFailed(f"Error communicating with Salus Cloud: {err}") from err
            _LOGGER.warning("Failed to refresh device list, using the previous one: %s", err)
            return
        self._metadata = metadata
        self._metadata_fetched_at = now
        if self._connection is not None:
            self._connection.set_device_codes(self._device_codes())

    def _build_data(self, now: float) -> dict[str, SalusDevice]:
        data: dict[str, SalusDevice] = {}
        for device in self._metadata.devices if self._metadata else []:
            device_id = device.get("id")
            device_code = device.get("device_code")
            if not device_id or not device_code:
                continue
            data[device_id] = {
                **device,
                "_shadow_properties": self._store.properties(device_code, now),
                "_shadow_device_index": self._store.index(device_code),
                "_fresh": self._store.is_fresh(device_code, now),
            }
        return data

    async def async_start_connection(self) -> None:
        """Connect to AWS IoT for commands and pushed device state changes."""
        if not self.gateways:
            return
        self._connection = self._connection_factory(
            credentials_provider=self.api.get_iot_credentials,
            client_id_prefix=self.gateways[0].device_code,
            on_shadow_document=self._handle_shadow_document,
            on_push_available=self._handle_push_available,
        )
        await self._connection.async_start(self._device_codes())

    async def async_shutdown(self) -> None:
        """Stop polling and the AWS IoT connection."""
        await super().async_shutdown()
        if self._cancel_confirmation is not None:
            self._cancel_confirmation()
            self._cancel_confirmation = None
        if self._connection is not None:
            await self._connection.async_stop()

    @callback
    def _handle_shadow_document(self, device_code: str, document: dict[str, Any]) -> None:
        if self._metadata is None or (reported := extract_reported(document)) is None:
            return
        now = self._clock()
        self._store.update_reported(device_code, reported[0], reported[1], now)
        self.async_set_updated_data(self._build_data(now))

    @callback
    def _handle_push_available(self, available: bool) -> None:
        self.push_available = available
        self.update_interval = timedelta(seconds=PUSH_SCAN_INTERVAL_SECONDS if available else SCAN_INTERVAL_SECONDS)

    async def async_set_hold_type(self, device_id: str, hold_type: int) -> None:
        """Set hold type of a thermostat, or of all thermostats of its gateway when modes are synchronized."""
        device = self._require_device(device_id)
        targets = [device]
        if self.sync_modes:
            targets = [
                other
                for other in self.data.values()
                if other.get("_gateway_id") == device.get("_gateway_id") and is_climate_device(other)
            ]
        await self._async_send(targets, {"ep9:sIT600TH:SetHoldType": hold_type})

    async def async_set_temperature(self, device_id: str, temperature: float) -> None:
        """Set target temperature of a thermostat (switches it to manual hold)."""
        await self._async_send(
            [self._require_device(device_id)],
            {
                "ep9:sIT600TH:SetHeatingSetpoint_x100": round(temperature * 100),
                "ep9:sIT600TH:SetHoldType": HOLD_TYPE_MANUAL,
                "ep9:sIT600TH:SetSystemMode": 4,
            },
        )

    async def async_set_switch(self, device_id: str, turn_on: bool) -> None:
        """Turn relay or smart plug on or off."""
        await self._async_send([self._require_device(device_id)], {"ep9:sOnOffS:SetOnOff": 1 if turn_on else 0})

    async def async_trigger_rule(self, gateway_id: str, rule_trigger_key: str) -> None:
        """Trigger a OneTouch rule of a gateway."""
        gateway = self.get_gateway(gateway_id)
        if gateway is None:
            raise HomeAssistantError(f"Salus gateway {gateway_id} not found")
        try:
            await self._async_publish(
                gateway.device_code, GATEWAY_SHADOW_INDEX, {"ep0:sRule:SetTriggerRule": rule_trigger_key}
            )
        except SalusCloudConnectionError as err:
            raise HomeAssistantError(f"Failed to trigger OneTouch rule: {err}") from err

    def _require_device(self, device_id: str) -> SalusDevice:
        device = self.get_device(device_id)
        if device is None:
            raise HomeAssistantError(f"Salus device {device_id} not found")
        return device

    async def _async_publish(self, device_code: str, device_index: str, properties: dict[str, Any]) -> None:
        if self._connection is None:
            raise SalusCloudConnectionError("Not connected to AWS IoT")
        await self._connection.async_publish_shadow(device_code, device_index, properties)

    async def _async_send(self, devices: list[SalusDevice], properties: dict[str, Any]) -> None:
        results = await asyncio.gather(
            *(
                self._async_publish(
                    device["device_code"], device.get("_shadow_device_index") or DEFAULT_SHADOW_INDEX, properties
                )
                for device in devices
            ),
            return_exceptions=True,
        )
        now = self._clock()
        failed: list[str] = []
        for device, result in zip(devices, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Device %s did not accept %s: %s", device.get("name"), properties, result)
                failed.append((device.get("name") or device["device_code"]).strip())
            else:
                self._store.set_pending(device["device_code"], properties, now)
        if len(failed) < len(devices):
            self.async_set_updated_data(self._build_data(now))
            if not self.push_available:
                self._schedule_confirmation_refresh()
        if failed:
            raise HomeAssistantError(f"Salus device did not accept the command: {', '.join(failed)}")

    @callback
    def _schedule_confirmation_refresh(self) -> None:
        if self._cancel_confirmation is not None:
            self._cancel_confirmation()
        self._cancel_confirmation = async_call_later(
            self.hass, CONFIRM_REFRESH_DELAY_SECONDS, self._async_confirmation_refresh
        )

    async def _async_confirmation_refresh(self, _now: datetime) -> None:
        self._cancel_confirmation = None
        await self.async_request_refresh()
