"""The Salus iT600 Cloud integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import SalusCloudCoordinator
from .gateway import (
    SalusCloudAuthenticationError,
    SalusCloudConnectionError,
    SalusCloudGateway,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Salus iT600 Cloud from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    # Create gateway instance
    gateway = SalusCloudGateway(email, password)

    try:
        # Authenticate
        await gateway.authenticate()

        # Create coordinator
        coordinator = SalusCloudCoordinator(hass, gateway)

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        # Store coordinator
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Register gateway device first (before other devices reference it)
        from homeassistant.helpers import device_registry as dr
        device_registry = dr.async_get(hass)

        if coordinator.gateway_id:
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, coordinator.gateway_id)},
                manufacturer="Salus",
                model="iT600 Gateway",
                name=coordinator.gateway_name,
            )
            _LOGGER.info("Registered gateway device: %s", coordinator.gateway_name)

        # Forward entry setup to platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except SalusCloudAuthenticationError as err:
        _LOGGER.error("Authentication failed: %s", err)
        await gateway.close()
        return False

    except SalusCloudConnectionError as err:
        _LOGGER.error("Connection failed: %s", err)
        await gateway.close()
        raise ConfigEntryNotReady from err

    except Exception as err:
        _LOGGER.exception("Unexpected error during setup: %s", err)
        await gateway.close()
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Close gateway connection
        coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.gateway.close()

        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
