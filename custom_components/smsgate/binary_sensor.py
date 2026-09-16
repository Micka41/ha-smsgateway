"""Capteur binaire de disponibilité de la passerelle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmsGateConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import SmsGateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmsGateConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Créer les capteurs binaires."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            SmsGateAvailability(coordinator, entry),
            SmsGateCheckBinarySensor(
                coordinator,
                entry,
                key="internet",
                check="connection:status",
                device_class=BinarySensorDeviceClass.CONNECTIVITY,
            ),
            SmsGateCheckBinarySensor(
                coordinator,
                entry,
                key="charging",
                check="battery:charging",
                device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
            ),
        ]
    )


class SmsGateAvailability(CoordinatorEntity[SmsGateCoordinator], BinarySensorEntity):
    """Disponibilité, alimentée par le polling /health et le heartbeat."""

    _attr_has_entity_name = True
    _attr_translation_key = "available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: SmsGateCoordinator, entry: SmsGateConfigEntry
    ) -> None:
        """Initialiser."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_available"
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            configuration_url=coordinator.api.base_url,
            sw_version=coordinator.app_version,
        )

    @property
    def is_on(self) -> bool:
        """Indiquer si la passerelle répond."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Exposer le heartbeat et les indicateurs réseau bruts.

        ``connection:transport`` et ``connection:cellular`` sont des codes
        Android dont la correspondance n'est pas documentée : ils sont exposés
        tels quels plutôt que traduits en libellés potentiellement faux.
        """
        last_ping = self.coordinator.last_ping
        return {
            "last_ping": last_ping.isoformat() if last_ping else None,
            "transport_raw": self.coordinator.check_value("connection:transport"),
            "cellular_raw": self.coordinator.check_value("connection:cellular"),
        }

    @property
    def available(self) -> bool:
        """Rester disponible pour pouvoir signaler l'indisponibilité."""
        return True


class SmsGateCheckBinarySensor(CoordinatorEntity[SmsGateCoordinator], BinarySensorEntity):
    """Capteur binaire alimenté par un contrôle de /health.

    ``connection:status`` est un booléen (0/1). ``battery:charging`` est un jeu
    de drapeaux du type d'alimentation — 0 hors charge, non nul en charge,
    la valeur indiquant secteur, USB, sans fil ou dock — donc le test porte
    sur la non-nullité et non sur l'égalité à 1.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmsGateCoordinator,
        entry: SmsGateConfigEntry,
        key: str,
        check: str,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        """Initialiser."""
        super().__init__(coordinator)
        self._check = check
        self._attr_translation_key = key
        self._attr_device_class = device_class
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )

    @property
    def available(self) -> bool:
        """L'entité disparaît si le contrôle est absent ou en échec."""
        return super().available and self.coordinator.check_ok(self._check)

    @property
    def is_on(self) -> bool | None:
        """Retourner l'état du contrôle."""
        valeur = self.coordinator.check_value(self._check)
        if valeur is None:
            return None
        try:
            return int(valeur) != 0
        except (TypeError, ValueError):
            return None
