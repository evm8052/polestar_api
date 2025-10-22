"""Base class for Polestar entities."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import PolestarCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription

_LOGGER = logging.getLogger(__name__)


class PolestarEntityDataSource(StrEnum):
    INFORMATION = "car_information_data"
    ODOMETER = "car_odometer_data"
    BATTERY = "car_battery_data"
    HEALTH = "car_health_data"


class PolestarEntityDataSourceException(Exception):
    """Exception raised when requested data source/attribute is missing"""


@dataclass(frozen=True)
class PolestarEntityDescription(EntityDescription):
    """Describes a Polestar entity."""

    data_source: PolestarEntityDataSource | None = None
    data_state_attribute: str | None = None
    data_state_fn: (
        Callable[
            [str | int | float | bool | date | datetime],
            str | int | float | bool | date | datetime,
        ]
        | None
    ) = None
    data_extra_state_attributes: dict[str, str] | None = None

    def __post_init__(self):
        """Validate the data source and attribute configuration."""
        if bool(self.data_source) != bool(self.data_state_attribute):
            raise ValueError(
                "Both data_source and data_attribute must be provided together"
            )


class PolestarEntity(CoordinatorEntity[PolestarCoordinator]):
    """Base class for Polestar entities."""

    _attr_attribution = ATTRIBUTION
    entity_description: PolestarEntityDescription

    def __init__(
        self,
        coordinator: PolestarCoordinator,
        entity_description: PolestarEntityDescription,
    ) -> None:
        """Initialize the Polestar entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.entity_id = (
            f"{DOMAIN}.polestar_{coordinator.get_short_id()}_{entity_description.key}"
        )
        self._attr_unique_id = f"polestar_{coordinator.vin}_{entity_description.key}"
        self._attr_translation_key = f"polestar_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.vin)},
            manufacturer="Polestar",
            model=self.coordinator.model,
            name=self.coordinator.name,
            serial_number=self.coordinator.vin,
        )
        if self.entity_description.data_extra_state_attributes:
            self._attr_extra_state_attributes = self.get_extra_state_attributes() or {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if hasattr(self, "_attr_extra_state_attributes"):
            self._attr_extra_state_attributes = self.get_extra_state_attributes() or {}
        super()._handle_coordinator_update()

    def get_extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""

        if not (
            self.entity_description.data_source
            and self.entity_description.data_extra_state_attributes
        ):
            return

        # ensure the coordinator has the data source
        data = getattr(self.coordinator, self.entity_description.data_source, None)
        if data is None:
            _LOGGER.debug(
                "%s not available for entity %s",
                self.entity_description.data_source,
                self.entity_id,
            )
            return

        # get all extra state attributes
        res = {}
        for (
            key,
            data_attribute,
        ) in self.entity_description.data_extra_state_attributes.items():
            # ensure the data source has the requested attribute
            if not hasattr(data, data_attribute):
                _LOGGER.error(
                    "Invalid extra state attribute %s.%s for entity %s",
                    self.entity_description.data_source,
                    data_attribute,
                    self.entity_id,
                )
                res[key] = None
                continue

            # ensure the requested value is available
            value = getattr(data, data_attribute, None)
            if value is None:
                _LOGGER.debug(
                    "%s.%s not available for entity %s",
                    self.entity_description.data_source,
                    data_attribute,
                    self.entity_id,
                )
            res[key] = value

        return res

    def get_native_value(self) -> str | None:
        """Return native value."""
        if not (
            self.entity_description.data_source
            and self.entity_description.data_state_attribute
        ):
            raise PolestarEntityDataSourceException

        # ensure the coordinator has the data source
        data = getattr(self.coordinator, self.entity_description.data_source, None)
        if not data:
            _LOGGER.debug(
                "%s not available for entity %s",
                self.entity_description.data_source,
                self.entity_id,
            )
            return

        # ensure the data source has the requested attribute
        if not hasattr(data, self.entity_description.data_state_attribute):
            _LOGGER.error(
                "Invalid state attribute %s.%s for entity %s",
                self.entity_description.data_source,
                self.entity_description.data_state_attribute,
                self.entity_id,
            )
            return

        # ensure the requested value is available
        value = getattr(data, self.entity_description.data_state_attribute, None)
        if value is None:
            _LOGGER.debug(
                "%s.%s not available for entity %s",
                self.entity_description.data_source,
                self.entity_description.data_state_attribute,
                self.entity_id,
            )
            return

        return (
            self.entity_description.data_state_fn(value)
            if self.entity_description.data_state_fn
            else value
        )
