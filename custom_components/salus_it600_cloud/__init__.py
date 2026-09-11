"""The Salus iT600 Cloud integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SalusCloudApi, SalusCloudAuthenticationError, SalusCloudConnectionError
from .const import DOMAIN
from .coordinator import SalusCloudCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

type SalusConfigEntry = ConfigEntry[SalusCloudCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    """Set up Salus iT600 Cloud from a config entry."""
    api = SalusCloudApi(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], session=async_get_clientsession(hass))
    try:
        await api.authenticate()
    except SalusCloudAuthenticationError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SalusCloudConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SalusCloudCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    # Gateways are registered first so devices can refer to them
    device_registry = dr.async_get(hass)
    for gateway in coordinator.gateways:
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, gateway.id)},
            manufacturer="Salus",
            model="iT600 Gateway",
            name=gateway.name,
        )
        coordinator.gateway_device_ids[gateway.id] = device.id

    await coordinator.async_start_connection()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    """Unload a config entry (the coordinator stops its MQTT connection when the entry unloads)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
