"""Support for Inim Cloud alarm control panels."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCENARIO_STATE_MAP = {
    "0": AlarmControlPanelState.ARMED_AWAY,
    "1": AlarmControlPanelState.DISARMED,
    "2": AlarmControlPanelState.ARMED_HOME,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Inim Cloud alarm control panel based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[COORDINATOR]
    api = data["api"]

    entities = []

    devices = coordinator.data if coordinator.data else []

    for device in devices:
        _LOGGER.info("Adding alarm control panel for device: %s", device.get("name"))
        entities.append(InimAlarmControlPanel(coordinator, api, entry, device))

    if entities:
        _LOGGER.info("Adding %d alarm control panel entities", len(entities))
        async_add_entities(entities)


class InimAlarmControlPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of an Inim Cloud alarm control panel."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
    )
    _attr_code_arm_required = False
    _attr_code_format = None

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api,
        entry: ConfigEntry,
        device: Dict[str, Any],
    ) -> None:
        """Initialize the alarm control panel entity."""
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._device = device
        self._device_id = device["id"]
        self._attr_name = device["name"]
        self._attr_unique_id = f"{entry.entry_id}_alarm_{self._device_id}"
        self._scenarios = device.get("scenarios", [])
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{self._device_id}")},
            "name": device["name"],
            "manufacturer": "Inim",
            "model": "Cloud Alarm",
        }
        self._disarm_scenario_id = None
        self._arm_away_scenario_id = None
        self._arm_home_scenario_id = None

        for scenario in self._scenarios:
            scenario_id = scenario.get("id")
            scenario_name = scenario.get("name", "").lower()

            if scenario_name in ["arm", "away"]:
                self._arm_away_scenario_id = scenario_id
                _LOGGER.debug(
                    "Mapped '%s' to ARM_AWAY with ID %s", scenario_name, scenario_id
                )
            elif scenario_name in ["stay", "home", "partial"]:
                self._arm_home_scenario_id = scenario_id
                _LOGGER.debug(
                    "Mapped '%s' to ARM_HOME with ID %s", scenario_name, scenario_id
                )
            elif scenario_name in ["disarm", "off"]:
                self._disarm_scenario_id = scenario_id
                _LOGGER.debug(
                    "Mapped '%s' to DISARM with ID %s", scenario_name, scenario_id
                )

    def _find_device_in_coordinator(self) -> Dict[str, Any] | None:
        """Find this device in coordinator data."""
        if not self.coordinator.data:
            return None

        for device in self.coordinator.data:
            if device.get("id") == self._device_id:
                return device
        return None

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        _LOGGER.debug("Entity %s added to hass", self.entity_id)

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current alarm state using the AlarmControlPanelState enum."""

        device = self._find_device_in_coordinator()
        if not device:
            _LOGGER.warning("Device %s not found in coordinator data", self._device_id)
            return None

        active_scenario = device.get("active_scenario")
        _LOGGER.debug(
            "Device %s active scenario ID: %s", self._attr_name, active_scenario
        )

        scenario_str = str(active_scenario) if active_scenario is not None else None
        state = SCENARIO_STATE_MAP.get(scenario_str)

        if state is None:
            _LOGGER.warning(
                "No state mapping found for scenario ID: %s, defaulting to DISARMED",
                active_scenario,
            )
            state = AlarmControlPanelState.DISARMED
        else:
            _LOGGER.debug(
                "Device %s scenario ID %s mapped to state: '%s'",
                self._attr_name,
                active_scenario,
                state,
            )

        return state

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""

        _LOGGER.debug("Disarming system for device %s", self._device_id)

        if self._disarm_scenario_id is not None:
            try:
                _LOGGER.debug("Sending disarm command to API")
                await self._api.activate_scenario(
                    self._device_id, self._disarm_scenario_id
                )

                await self.coordinator.async_refresh()

            except Exception as err:
                _LOGGER.error("Error disarming system: %s", err)
                await self.coordinator.async_refresh()
        else:
            _LOGGER.error(
                "Cannot disarm - no disarm scenario ID found for device %s",
                self._device_id,
            )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""

        _LOGGER.debug("Arming system (home) for device %s", self._device_id)

        if self._arm_home_scenario_id is not None:
            try:
                _LOGGER.debug("Sending arm home command to API")
                await self._api.activate_scenario(
                    self._device_id, self._arm_home_scenario_id
                )

                await self.coordinator.async_refresh()

            except Exception as err:
                _LOGGER.error("Error arming system (home): %s", err)
                await self.coordinator.async_refresh()
        else:
            _LOGGER.error(
                "Cannot arm home - no arm home scenario ID found for device %s",
                self._device_id,
            )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""

        _LOGGER.debug("Arming system (away) for device %s", self._device_id)

        if self._arm_away_scenario_id is not None:
            try:
                _LOGGER.debug("Sending arm away command to API")
                await self._api.activate_scenario(
                    self._device_id, self._arm_away_scenario_id
                )

                await self.coordinator.async_refresh()

            except Exception as err:
                _LOGGER.error("Error arming system (away): %s", err)
                await self.coordinator.async_refresh()
        else:
            _LOGGER.error(
                "Cannot arm away - no arm away scenario ID found for device %s",
                self._device_id,
            )
