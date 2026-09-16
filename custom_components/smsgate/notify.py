"""Entité notify : SMS vers le destinataire par défaut.

Volontairement limitée à message + titre — c'est le contrat de NotifyEntity.
Les pièces jointes, la SIM et la priorité passent par les services
``smsgate.send_sms`` et ``smsgate.send_mms``.
"""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmsGateConfigEntry
from .api import SmsGateError
from .const import CONF_DEFAULT_RECIPIENT, DOMAIN, MANUFACTURER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmsGateConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Créer l'entité notify si un destinataire par défaut est configuré."""
    if entry.options.get(CONF_DEFAULT_RECIPIENT):
        async_add_entities([SmsGateNotify(entry)])


class SmsGateNotify(NotifyEntity):
    """Envoi d'un SMS au destinataire par défaut."""

    _attr_has_entity_name = True
    _attr_translation_key = "sms"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: SmsGateConfigEntry) -> None:
        """Initialiser."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Envoyer le message."""
        destinataire = self._entry.options.get(CONF_DEFAULT_RECIPIENT)
        if not destinataire:
            raise HomeAssistantError("Aucun destinataire par défaut configuré")

        contenu = f"{title}\n{message}" if title else message
        try:
            resultat = await self._entry.runtime_data.api.async_send_sms(
                recipients=[destinataire], message=contenu
            )
        except SmsGateError as err:
            raise HomeAssistantError(f"Envoi SMS impossible: {err}") from err

        self._entry.runtime_data.coordinator.track_message(
            resultat.get("id", ""), [destinataire], "pending"
        )
