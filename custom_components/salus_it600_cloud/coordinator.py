"""DataUpdateCoordinator for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .gateway import SalusCloudConnectionError, SalusCloudGateway

_LOGGER = logging.getLogger(__name__)


class SalusCloudCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Salus iT600 Cloud data."""

    def __init__(
        self,
        hass: HomeAssistant,
        gateway: SalusCloudGateway,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.gateway = gateway
        self._devices: dict[str, dict[str, Any]] = {}
        self._gateway_name: str = ""
        self._gateway_id: str = ""
        self._gateway_code: str = ""

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            # Get gateway info first (only on first run if not set)
            if not self._gateway_name:
                gateways = await self.gateway.get_gateways()
                if gateways:
                    self._gateway_id = gateways[0].get("id", "")
                    gateway_data = gateways[0].get("gateway", {})
                    self._gateway_name = gateway_data.get("name", "Salus Gateway")
                    self._gateway_code = gateway_data.get("device_code", "")
                    _LOGGER.info("Gateway name: %s (ID: %s)", self._gateway_name, self._gateway_id)

            # Get all devices
            devices = await self.gateway.get_all_devices()

            # Convert list to dict with device_id as key
            devices_dict = {}
            for device in devices:
                # Use appropriate ID field
                device_id = device.get("id") or device.get("device_id")
                if device_id:
                    devices_dict[device_id] = device

            self._devices = devices_dict
            _LOGGER.debug("Stored %d devices", len(devices_dict))
            return devices_dict

        except SalusCloudConnectionError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get device data by ID."""
        return self._devices.get(device_id)

    def get_devices_by_type(self, device_type: str) -> list[dict[str, Any]]:
        """Get all devices of a specific type."""
        # This will need to be adapted based on actual device data structure
        return [
            device
            for device in self._devices.values()
            if device.get("type") == device_type
        ]

    @property
    def gateway_name(self) -> str:
        """Return the gateway name."""
        return self._gateway_name or "Salus Gateway"

    @property
    def gateway_id(self) -> str:
        """Return the gateway ID."""
        return self._gateway_id

    @property
    def gateway_code(self) -> str:
        """Return the gateway device code."""
        return self._gateway_code
