"""Entité de mise à jour de l'application SMS Gateway for Android.

L'API de l'application n'expose aucun endpoint de mise à jour : la version
installée vient de ``/health``, la version disponible de la page des releases
GitHub. L'installation reste manuelle — une intégration Home Assistant ne peut
pas pousser un APK sur un téléphone.
"""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmsGateConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import SmsGateReleaseCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmsGateConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Créer l'entité de mise à jour si la recherche est activée."""
    release = entry.runtime_data.release
    if release is not None:
        async_add_entities([SmsGateUpdate(release, entry)])


class SmsGateUpdate(CoordinatorEntity[SmsGateReleaseCoordinator], UpdateEntity):
    """Compare la version installée à la dernière version publiée."""

    _attr_has_entity_name = True
    _attr_translation_key = "app"
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(
        self, coordinator: SmsGateReleaseCoordinator, entry: SmsGateConfigEntry
    ) -> None:
        """Initialiser."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_app_update"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
        )

    @property
    def installed_version(self) -> str | None:
        """Version rapportée par l'application elle-même."""
        return self._entry.runtime_data.coordinator.app_version

    @property
    def latest_version(self) -> str | None:
        """Dernière version publiée, ou la version installée si inconnue.

        Retourner la version installée quand GitHub est injoignable évite
        d'afficher une mise à jour fantôme ou un état inconnu permanent.
        """
        return self.coordinator.data or self.installed_version

    @property
    def release_url(self) -> str | None:
        """Lien vers la page de la release."""
        return self.coordinator.release_url

    @property
    def available(self) -> bool:
        """Disponible dès que la version installée est connue."""
        return self.installed_version is not None

    async def async_release_notes(self) -> str | None:
        """Renvoyer vers les notes de version plutôt que de les recopier."""
        if not self.coordinator.release_url:
            return None
        return (
            "L'installation se fait manuellement depuis le téléphone.\n\n"
            f"[Notes de version]({self.coordinator.release_url})"
        )
