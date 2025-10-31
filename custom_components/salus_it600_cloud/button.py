"""Button platform for Salus iT600 Cloud."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud button entities."""
    from .coordinator import SalusCloudCoordinator

    coordinator: SalusCloudCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Get OneTouch rules
    try:
        rules = await coordinator.gateway.get_onetouch_rules()
        _LOGGER.info("Found %d OneTouch rules", len(rules))

        for rule_data in rules:
            rule = rule_data.get("rule", {})
            rule_name = rule.get("name", "Unknown Rule")
            rule_trigger_key = rule_data.get("rule_trigger_key", "")
            gateway_id = rule_data.get("_gateway_id", "")

            if not rule_trigger_key:
                _LOGGER.debug("Skipping rule %s - no trigger key", rule_name)
                continue

            # Skip auto-generated rules (they start with _)
            if rule_name.startswith("_"):
                _LOGGER.debug("Skipping auto-generated rule: %s", rule_name)
                continue

            entities.append(
                SalusOneTouchButton(
                    coordinator,
                    rule_data,
                    rule_name,
                    rule_trigger_key,
                    gateway_id,
                )
            )

    except Exception as err:
        _LOGGER.error("Failed to load OneTouch rules: %s", err)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d OneTouch button(s)", len(entities))
    else:
        _LOGGER.info("No OneTouch buttons to add")


class SalusOneTouchButton(ButtonEntity):
    """Representation of a Salus OneTouch rule button."""

    _attr_has_entity_name = False  # We set full name including device name

    def __init__(
        self,
        coordinator,
        rule_data: dict[str, Any],
        rule_name: str,
        rule_trigger_key: str,
        gateway_id: str,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._rule_data = rule_data
        self._rule_name = rule_name
        self._rule_trigger_key = rule_trigger_key
        self._gateway_id = gateway_id

        rule_id = rule_data.get("id", "")

        # Use gateway name as prefix for entity name (like salusfy)
        gateway_name = coordinator.gateway_name or "Salus iT600"
        gateway_id = coordinator.gateway_id
        self._attr_name = f"{gateway_name} {rule_name}"

        # Set unique_id with gateway to create new entities
        self._attr_unique_id = f"{DOMAIN}_{gateway_id}_onetouch_{rule_id}"

        # Set explicit object_id to ensure unique entity IDs
        import re
        gateway_slug = re.sub(r'[^a-z0-9_]+', '_', gateway_name.lower()).strip('_')
        rule_slug = re.sub(r'[^a-z0-9_]+', '_', rule_name.lower()).strip('_')
        self._attr_object_id = f"{gateway_slug}_{rule_slug}"

        # Device info - link to gateway
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{gateway_id}_onetouch_rules")},
            "name": "OneTouch Rules",
            "manufacturer": "Salus",
            "model": "OneTouch Rules",
            "via_device": (DOMAIN, gateway_id),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Triggering OneTouch rule: %s", self._rule_name)

        try:
            # Get gateway device code
            gateways = await self._coordinator.gateway.get_gateways()
            gateway = next(
                (g for g in gateways if g.get("id") == self._gateway_id),
                None
            )

            if not gateway:
                _LOGGER.error("Gateway not found: %s", self._gateway_id)
                from homeassistant.exceptions import HomeAssistantError
                raise HomeAssistantError(f"Gateway not found: {self._gateway_id}")

            gateway_code = gateway.get("gateway", {}).get("device_code")
            if not gateway_code:
                _LOGGER.error("Gateway device code not found")
                from homeassistant.exceptions import HomeAssistantError
                raise HomeAssistantError("Gateway device code not found")

            # Trigger the rule
            await self._coordinator.gateway.trigger_onetouch_rule(
                gateway_code, self._rule_trigger_key
            )

            _LOGGER.info("Successfully triggered OneTouch rule: %s", self._rule_name)

        except Exception as err:
            _LOGGER.error("Failed to trigger OneTouch rule: %s", err)
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"Failed to trigger OneTouch rule: {err}") from err
