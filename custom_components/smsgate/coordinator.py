"""Coordinator SMSGateway : disponibilité de la passerelle et suivi des envois."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from aiohttp import ClientError, ClientTimeout

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SmsGateApi, SmsGateAuthError, SmsGateError
from .const import (
    DOMAIN,
    RELEASE_SCAN_INTERVAL_HOURS,
    RELEASE_URL,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Nombre d'envois dont on garde la trace pour recoller les webhooks de statut.
MAX_TRACKED_MESSAGES = 100


class SmsGateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Interroge périodiquement l'endpoint de santé du Local Server."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SmsGateApi) -> None:
        """Initialiser le coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.api = api
        self.last_ping = None
        # messageId -> {"state": ..., "recipients": [...], "updated": datetime}
        self.messages: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupérer l'état de santé de la passerelle."""
        try:
            health = await self.api.async_health()
        except SmsGateAuthError as err:
            raise UpdateFailed(f"Authentification refusée: {err}") from err
        except SmsGateError as err:
            raise UpdateFailed(str(err)) from err

        return {"health": health, "last_ping": self.last_ping}

    # --- Lecture des contrôles /health ---------------------------------------

    def _check(self, cle: str) -> dict[str, Any]:
        """Retourner un contrôle de /health, ou un dict vide s'il est absent."""
        health = (self.data or {}).get("health") or {}
        checks = health.get("checks") or {}
        valeur = checks.get(cle)
        return valeur if isinstance(valeur, dict) else {}

    def check_value(self, cle: str) -> Any:
        """Retourner la valeur observée d'un contrôle, ou None."""
        return self._check(cle).get("observedValue")

    def check_ok(self, cle: str) -> bool:
        """Indiquer si un contrôle est présent et non en échec.

        Un statut ``warn`` reste exploitable : seul ``fail`` ou l'absence du
        contrôle rend l'entité indisponible.
        """
        check = self._check(cle)
        return bool(check) and check.get("status") != "fail"

    @property
    def app_version(self) -> str | None:
        """Retourner la version applicative remontée par /health."""
        version = ((self.data or {}).get("health") or {}).get("version")
        return version if isinstance(version, str) else None

    def note_ping(self) -> None:
        """Enregistrer un heartbeat reçu par webhook."""
        self.last_ping = dt_util.now()
        self.async_set_updated_data({**(self.data or {}), "last_ping": self.last_ping})

    def track_message(self, message_id: str, recipients: list[str], state: str) -> None:
        """Mémoriser un envoi pour le corréler aux webhooks de statut."""
        if not message_id:
            return
        self.messages[message_id] = {
            "state": state,
            "recipients": recipients,
            "updated": dt_util.now(),
        }
        while len(self.messages) > MAX_TRACKED_MESSAGES:
            self.messages.pop(next(iter(self.messages)))

    def update_message_state(self, message_id: str, state: str) -> dict[str, Any] | None:
        """Mettre à jour l'état d'un envoi suivi."""
        if not message_id:
            return None
        entry = self.messages.setdefault(
            message_id, {"state": state, "recipients": [], "updated": dt_util.now()}
        )
        entry["state"] = state
        entry["updated"] = dt_util.now()
        return entry


class SmsGateReleaseCoordinator(DataUpdateCoordinator[str | None]):
    """Recherche la dernière version publiée de l'application sur GitHub.

    Volontairement tolérant : l'API GitHub limite les requêtes anonymes et
    peut être injoignable. Un échec ne doit jamais rendre l'intégration
    indisponible — il laisse simplement la version cible inconnue.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialiser le coordinator de version."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_release",
            update_interval=timedelta(hours=RELEASE_SCAN_INTERVAL_HOURS),
            config_entry=entry,
        )
        self._session = async_get_clientsession(hass)
        self.release_url: str | None = None

    async def _async_update_data(self) -> str | None:
        """Retourner le tag de la dernière version stable, ou None."""
        try:
            async with self._session.get(
                RELEASE_URL, timeout=ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    # 403 = quota anonyme épuisé. Sans intérêt à remonter.
                    _LOGGER.debug("GitHub a répondu %s", response.status)
                    return self.data
                charge = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Recherche de version impossible: %s", err)
            return self.data

        self.release_url = charge.get("html_url")
        tag = charge.get("tag_name")
        # /releases/latest exclut déjà les pre-releases côté GitHub.
        return tag.lstrip("vV") if isinstance(tag, str) and tag else None
