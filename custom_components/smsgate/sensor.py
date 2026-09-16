"""Capteurs SMSGateway."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmsGateConfigEntry
from .coordinator import SmsGateCoordinator
from .const import (
    DOMAIN,
    MANUFACTURER,
    SIGNAL_MMS_RECEIVED,
    SIGNAL_SMS_RECEIVED,
    SIGNAL_STATUS,
)

MAX_STATE_LENGTH = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmsGateConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Créer les capteurs."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            SmsGateLastSmsSensor(entry),
            SmsGateLastMmsSensor(entry),
            SmsGateLastStatusSensor(entry),
            SmsGateCheckSensor(
                coordinator,
                entry,
                key="battery",
                check="battery:level",
                unit=PERCENTAGE,
                device_class=SensorDeviceClass.BATTERY,
            ),
            SmsGateCheckSensor(
                coordinator,
                entry,
                key="failed_messages",
                check="messages:failed",
                unit="messages",
            ),
        ]
    )


class SmsGateBaseSensor(SensorEntity, RestoreEntity):
    """Base commune : appareil, nommage, restauration."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: SmsGateConfigEntry, key: str) -> None:
        """Initialiser le capteur."""
        self._entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )
        self._attrs: dict[str, Any] = {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourner les attributs additionnels."""
        return self._attrs

    async def async_added_to_hass(self) -> None:
        """Restaurer l'état après redémarrage."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last_state.state
            self._attrs = dict(last_state.attributes)
            self._attrs.pop("friendly_name", None)

    def _apply(self, value: str | None, attrs: dict[str, Any]) -> None:
        """Appliquer une nouvelle valeur en respectant la limite d'état."""
        self._attr_native_value = (value or "")[:MAX_STATE_LENGTH] or None
        self._attrs = attrs
        self.async_write_ha_state()


class SmsGateLastSmsSensor(SmsGateBaseSensor):
    """Dernier SMS reçu : l'état porte l'expéditeur, le texte est en attribut."""

    _attr_icon = "mdi:message-text"

    def __init__(self, entry: SmsGateConfigEntry) -> None:
        """Initialiser."""
        super().__init__(entry, "last_sms")

    async def async_added_to_hass(self) -> None:
        """S'abonner au signal interne."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SMS_RECEIVED.format(self._entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, data: dict[str, Any]) -> None:
        """Traiter un SMS entrant."""
        self._apply(
            data.get("sender"),
            {
                "message": data.get("message"),
                "sim": data.get("sim"),
                "received_at": data.get("received_at"),
                "message_id": data.get("message_id"),
            },
        )


class SmsGateLastMmsSensor(SmsGateBaseSensor):
    """Dernier MMS reçu, avec les chemins des pièces jointes écrites."""

    _attr_icon = "mdi:image-multiple"

    def __init__(self, entry: SmsGateConfigEntry) -> None:
        """Initialiser."""
        super().__init__(entry, "last_mms")

    async def async_added_to_hass(self) -> None:
        """S'abonner au signal interne."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_MMS_RECEIVED.format(self._entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, data: dict[str, Any]) -> None:
        """Traiter un MMS téléchargé."""
        pieces = data.get("attachments") or []
        self._apply(
            data.get("sender"),
            {
                "subject": data.get("subject"),
                "message": data.get("message"),
                "received_at": data.get("received_at"),
                "message_id": data.get("message_id"),
                "attachment_count": len(pieces),
                "attachment_paths": [p["path"] for p in pieces],
                "attachment_names": [p["name"] for p in pieces],
            },
        )


class SmsGateLastStatusSensor(SmsGateBaseSensor):
    """Dernier statut d'envoi remonté par webhook."""

    _attr_icon = "mdi:check-network"

    def __init__(self, entry: SmsGateConfigEntry) -> None:
        """Initialiser."""
        super().__init__(entry, "last_status")

    async def async_added_to_hass(self) -> None:
        """S'abonner au signal interne."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATUS.format(self._entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, data: dict[str, Any]) -> None:
        """Traiter un changement de statut."""
        self._apply(
            data.get("state"),
            {
                "message_id": data.get("message_id"),
                "recipient": data.get("recipient"),
            },
        )


class SmsGateCheckSensor(CoordinatorEntity[SmsGateCoordinator], SensorEntity):
    """Capteur numérique alimenté par un contrôle de /health."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SmsGateCoordinator,
        entry: SmsGateConfigEntry,
        key: str,
        check: str,
        unit: str,
        device_class: SensorDeviceClass | None = None,
    ) -> None:
        """Initialiser."""
        super().__init__(coordinator)
        self._check = check
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
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
    def native_value(self) -> int | None:
        """Retourner la valeur observée."""
        valeur = self.coordinator.check_value(self._check)
        try:
            return int(valeur)
        except (TypeError, ValueError):
            return None
