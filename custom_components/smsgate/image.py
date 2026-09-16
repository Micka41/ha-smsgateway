"""Entité image : dernière pièce jointe image reçue par MMS."""

from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import SmsGateConfigEntry
from .const import DOMAIN, MANUFACTURER, SIGNAL_MMS_RECEIVED

_LOGGER = logging.getLogger(__name__)

ATTR_PATH = "path"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmsGateConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Créer l'entité image."""
    async_add_entities([SmsGateLastImage(hass, entry)])


class SmsGateLastImage(ImageEntity, RestoreEntity):
    """Expose la dernière image reçue, lue à la demande depuis le disque."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_mms_image"

    def __init__(self, hass: HomeAssistant, entry: SmsGateConfigEntry) -> None:
        """Initialiser."""
        super().__init__(hass)
        self._entry = entry
        self._path: str | None = None
        self._attr_unique_id = f"{entry.entry_id}_last_mms_image"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Exposer le chemin du fichier courant."""
        return {ATTR_PATH: self._path}

    async def async_added_to_hass(self) -> None:
        """Restaurer le dernier chemin connu et s'abonner aux MMS."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            chemin = last_state.attributes.get(ATTR_PATH)
            if chemin and await self.hass.async_add_executor_job(os.path.isfile, chemin):
                self._path = chemin
                self._attr_image_last_updated = dt_util.utcnow()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_MMS_RECEIVED.format(self._entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, data: dict[str, Any]) -> None:
        """Retenir la première pièce jointe de type image."""
        for piece in data.get("attachments") or []:
            if piece.get("content_type", "").startswith("image/"):
                self._path = piece["path"]
                self._cached_image = None
                self._attr_image_last_updated = dt_util.utcnow()
                self.async_write_ha_state()
                return

    async def async_image(self) -> bytes | None:
        """Retourner le contenu binaire de l'image."""
        if not self._path:
            return None
        try:
            return await self.hass.async_add_executor_job(self._read)
        except OSError as err:
            _LOGGER.warning("Lecture de %s impossible: %s", self._path, err)
            return None

    def _read(self) -> bytes:
        """Lire le fichier — appel bloquant."""
        with open(self._path, "rb") as handle:
            return handle.read()
