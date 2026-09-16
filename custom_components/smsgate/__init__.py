"""Intégration SMSGateway — SMS Gateway for Android dans Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_WEBHOOK_ID,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError

from .api import SmsGateApi, SmsGateAuthError, SmsGateConnectionError, SmsGateError
from .recipients import RecipientError, async_resolve, invalidate_cache
from .const import (
    ATTR_ATTACHMENTS,
    ATTR_CONFIG_ENTRY,
    ATTR_MESSAGE,
    ATTR_PRIORITY,
    ATTR_RECIPIENTS,
    ATTR_SIM,
    ATTR_SUBJECT,
    ATTR_TTL,
    CONF_CHECK_UPDATES,
    CONF_MESSAGE_PATH,
    CONF_WEBHOOK_URL,
    DEFAULT_CHECK_UPDATES,
    DEFAULT_MESSAGE_PATH,
    DOMAIN,
    SERVICE_SEND_MMS,
    SERVICE_SEND_SMS,
    WEBHOOK_EVENTS,
)
from .coordinator import SmsGateCoordinator, SmsGateReleaseCoordinator
from .webhook_handler import async_handle_webhook

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.NOTIFY,
    Platform.SENSOR,
    Platform.UPDATE,
]

# Préfixe des webhooks créés côté application, pour pouvoir les nettoyer.
APP_WEBHOOK_PREFIX = "ha-smsgate"


@dataclass
class SmsGateData:
    """Objets partagés entre plateformes."""

    api: SmsGateApi
    coordinator: SmsGateCoordinator
    release: SmsGateReleaseCoordinator | None = None
    app_webhook_ids: list[str] = field(default_factory=list)


type SmsGateConfigEntry = ConfigEntry[SmsGateData]

BASE_SEND_SCHEMA = {
    vol.Required(ATTR_RECIPIENTS): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_PRIORITY): vol.All(vol.Coerce(int), vol.Range(min=-128, max=127)),
    vol.Optional(ATTR_SIM): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
    vol.Optional(ATTR_TTL): cv.positive_int,
    vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
}

SEND_SMS_SCHEMA = vol.Schema({**BASE_SEND_SCHEMA, vol.Required(ATTR_MESSAGE): cv.string})

SEND_MMS_SCHEMA = vol.Schema(
    {
        **BASE_SEND_SCHEMA,
        vol.Required(ATTR_ATTACHMENTS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_SUBJECT): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: SmsGateConfigEntry) -> bool:
    """Configurer une entrée."""
    api = SmsGateApi(
        session=async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        message_path=entry.data.get(CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH),
    )

    coordinator = SmsGateCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except SmsGateAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err

    # Recherche de nouvelle version : seul appel sortant de l'intégration,
    # désactivable dans les options.
    release: SmsGateReleaseCoordinator | None = None
    if entry.options.get(CONF_CHECK_UPDATES, DEFAULT_CHECK_UPDATES):
        release = SmsGateReleaseCoordinator(hass, entry)
        # Un échec GitHub ne doit pas empêcher l'intégration de démarrer.
        await release.async_refresh()

    entry.runtime_data = SmsGateData(api=api, coordinator=coordinator, release=release)

    # --- Webhook HA ----------------------------------------------------------
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass,
        DOMAIN,
        "SMSGateway",
        webhook_id,
        async_handle_webhook,
        allowed_methods=["POST"],
        local_only=True,
    )

    # --- Enregistrement côté application -------------------------------------
    # L'application en build "secure" refuse toute URL non HTTPS : il faut donc
    # l'URL externe (reverse proxy + certificat valide), pas l'adresse interne.
    url = _resolve_webhook_url(hass, entry, webhook_id)

    if url is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"webhook_url_{entry.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="webhook_url_unavailable",
        )
        raise ConfigEntryNotReady(
            "Aucune URL HTTPS disponible pour le webhook. Configurer l'URL externe "
            "de Home Assistant ou renseigner l'option dédiée."
        )

    ir.async_delete_issue(hass, DOMAIN, f"webhook_url_{entry.entry_id}")
    await _async_sync_app_webhooks(hass, entry, url)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _resolve_webhook_url(
    hass: HomeAssistant, entry: SmsGateConfigEntry, webhook_id: str
) -> str | None:
    """Déterminer l'URL que l'application appellera.

    Le build "secure" de l'application n'accepte que du HTTPS avec un
    certificat valide : une adresse interne en http ou une IP nue est refusée
    à l'enregistrement. On renvoie ``None`` si rien d'exploitable n'est
    disponible, plutôt que d'enregistrer une URL vouée à l'échec.
    """
    if override := entry.options.get(CONF_WEBHOOK_URL):
        url = override.rstrip("/")
        if not url.startswith("https://"):
            _LOGGER.error("URL de webhook forcée non HTTPS: %s", url)
            return None
        # L'option peut contenir soit la racine, soit l'URL complète.
        return url if webhook_id in url else f"{url}/api/webhook/{webhook_id}"

    try:
        # allow_internal=False : sans ça, HA retombe sur l'URL interne en http,
        # que l'application refusera. allow_ip=False : un certificat ne peut
        # pas valider une IP nue.
        url = webhook.async_generate_url(
            hass,
            webhook_id,
            allow_internal=False,
            allow_external=True,
            allow_ip=False,
        )
    except NoURLAvailableError:
        _LOGGER.error(
            "Aucune URL externe configurée dans Home Assistant "
            "(Paramètres > Système > Réseau), et aucune URL forcée dans les options"
        )
        return None

    if not url.startswith("https://"):
        _LOGGER.error(
            "L'URL externe de Home Assistant n'est pas en HTTPS (%s) : "
            "l'application refusera l'enregistrement du webhook",
            url,
        )
        return None

    return url


async def _async_sync_app_webhooks(
    hass: HomeAssistant, entry: SmsGateConfigEntry, url: str
) -> None:
    """(Ré)enregistrer un webhook applicatif par événement."""
    api = entry.runtime_data.api
    ids: list[str] = []

    for event in WEBHOOK_EVENTS:
        app_id = f"{APP_WEBHOOK_PREFIX}-{event.replace(':', '-')}"
        ids.append(app_id)
        # Suppression préalable : l'API rejette un identifiant déjà pris.
        await api.async_delete_webhook(app_id)
        try:
            await api.async_register_webhook(app_id, url, event)
        except SmsGateError as err:
            _LOGGER.error("Enregistrement du webhook %s impossible: %s", event, err)

    entry.runtime_data.app_webhook_ids = ids
    _LOGGER.debug("%d webhooks applicatifs pointés vers %s", len(ids), url)


async def _async_update_listener(hass: HomeAssistant, entry: SmsGateConfigEntry) -> None:
    """Recharger l'entrée quand les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SmsGateConfigEntry) -> bool:
    """Décharger une entrée."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])

    # runtime_data est absent si l'entrée n'a jamais démarré — par exemple
    # après un échec au premier rafraîchissement. Sans cette garde, retirer
    # une entrée en erreur lève AttributeError.
    data = getattr(entry, "runtime_data", None)
    if data is not None:
        # On retire les enregistrements côté téléphone pour ne pas laisser
        # l'app marteler une URL morte.
        for app_id in data.app_webhook_ids:
            await data.api.async_delete_webhook(app_id)

    if len(hass.config_entries.async_entries(DOMAIN)) == 1:
        hass.services.async_remove(DOMAIN, SERVICE_SEND_SMS)
        hass.services.async_remove(DOMAIN, SERVICE_SEND_MMS)
        invalidate_cache(hass)

    return True


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> SmsGateConfigEntry:
    """Retrouver l'entrée ciblée par un appel de service."""
    entry_id = call.data.get(ATTR_CONFIG_ENTRY)
    toutes = hass.config_entries.async_entries(DOMAIN)
    chargees = [entry for entry in toutes if hasattr(entry, "runtime_data")]

    if entry_id:
        for entry in chargees:
            if entry.entry_id == entry_id:
                return entry
        # Distinguer les deux causes : sans ça, une passerelle simplement en
        # erreur de démarrage est signalée comme inexistante.
        if any(entry.entry_id == entry_id for entry in toutes):
            raise HomeAssistantError(
                f"La passerelle {entry_id} existe mais n'est pas démarrée. "
                "Vérifier son état dans Appareils et services."
            )
        raise HomeAssistantError(
            f"Aucune passerelle SMSGateway avec l'identifiant {entry_id}. "
            "L'automation cible probablement une entrée supprimée : "
            "resélectionner la passerelle dans l'action."
        )

    if not chargees:
        raise HomeAssistantError("Aucune passerelle SMSGateway démarrée")
    return chargees[0]


async def _destinataires(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Résoudre les alias {NOM} depuis secrets.yaml."""
    try:
        return await async_resolve(hass, call.data[ATTR_RECIPIENTS])
    except RecipientError as err:
        raise HomeAssistantError(str(err)) from err


def _async_register_services(hass: HomeAssistant) -> None:
    """Déclarer les services d'envoi, une seule fois."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_SMS):
        return

    async def _async_send_sms(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call)
        data = entry.runtime_data
        destinataires = await _destinataires(hass, call)
        try:
            result = await data.api.async_send_sms(
                recipients=destinataires,
                message=call.data[ATTR_MESSAGE],
                sim=call.data.get(ATTR_SIM),
                priority=call.data.get(ATTR_PRIORITY),
                ttl=call.data.get(ATTR_TTL),
            )
        except (SmsGateConnectionError, SmsGateError) as err:
            raise HomeAssistantError(f"Envoi SMS impossible: {err}") from err
        data.coordinator.track_message(result.get("id", ""), destinataires, "pending")

    async def _async_send_mms(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call)
        data = entry.runtime_data
        destinataires = await _destinataires(hass, call)
        chemins = call.data[ATTR_ATTACHMENTS]

        for chemin in chemins:
            if not hass.config.is_allowed_path(chemin):
                raise HomeAssistantError(
                    f"Chemin non autorisé: {chemin}. Ajouter son dossier à allowlist_external_dirs"
                )

        try:
            pieces = [
                await hass.async_add_executor_job(SmsGateApi.encode_attachment, chemin)
                for chemin in chemins
            ]
        except OSError as err:
            raise HomeAssistantError(f"Pièce jointe illisible: {err}") from err

        try:
            result = await data.api.async_send_mms(
                recipients=destinataires,
                attachments=pieces,
                message=call.data.get(ATTR_MESSAGE),
                subject=call.data.get(ATTR_SUBJECT),
                sim=call.data.get(ATTR_SIM),
                priority=call.data.get(ATTR_PRIORITY),
                ttl=call.data.get(ATTR_TTL),
            )
        except (SmsGateConnectionError, SmsGateError) as err:
            raise HomeAssistantError(f"Envoi MMS impossible: {err}") from err
        data.coordinator.track_message(result.get("id", ""), destinataires, "pending")

    hass.services.async_register(DOMAIN, SERVICE_SEND_SMS, _async_send_sms, SEND_SMS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_MMS, _async_send_mms, SEND_MMS_SCHEMA)
