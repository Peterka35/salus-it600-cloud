"""Config flow for Salus iT600 Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .gateway import SalusCloudAuthenticationError, SalusCloudGateway

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class SalusIT600CloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Salus iT600 Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            # Check if already configured
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            # Try to authenticate
            gateway = SalusCloudGateway(email, password)

            try:
                await gateway.authenticate()

                # Try to get gateways to verify connection works
                gateways = await gateway.get_gateways()

                if not gateways:
                    _LOGGER.debug("Authentication successful but no gateways found")
                    errors["base"] = "no_devices"
                else:
                    _LOGGER.debug(
                        "Authentication successful, found %d gateway(s)", len(gateways)
                    )

                    # Create entry
                    return self.async_create_entry(
                        title=f"Salus iT600 Cloud ({email})",
                        data={
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                        },
                    )

            except SalusCloudAuthenticationError as err:
                _LOGGER.error("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"

            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

            finally:
                await gateway.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
