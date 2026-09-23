"""Réception des webhooks SMSGateway.

Un seul webhook Home Assistant est exposé ; côté application, un enregistrement
par événement pointe vers cette même URL. Le champ ``event`` du payload permet
de router. Les livraisons groupées (plusieurs messages dans un POST) sont
normalisées en liste.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
import os
import re
from typing import Any

from aiohttp.web import Request, Response

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    CONF_KEEP_ATTACHMENTS,
    CONF_SIGNING_KEY,
    CONF_MEDIA_DIR,
    DEFAULT_KEEP_ATTACHMENTS,
    DEFAULT_MEDIA_DIR,
    DOMAIN,
    EVENT_MMS_DOWNLOADED,
    EVENT_MMS_RECEIVED,
    EVENT_SMS_DELIVERED,
    EVENT_SMS_FAILED,
    EVENT_SMS_RECEIVED,
    EVENT_SMS_SENT,
    EVENT_SYSTEM_PING,
    HA_EVENT_MMS_NOTIFIED,
    HA_EVENT_MMS_RECEIVED,
    HA_EVENT_SMS_RECEIVED,
    HA_EVENT_STATUS,
    SIGNAL_MMS_RECEIVED,
    SIGNAL_PING,
    SIGNAL_SMS_RECEIVED,
    SIGNAL_STATUS,
    SIGNATURE_TOLERANCE_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
IMAGE_TYPES = ("image/",)


def _safe_filename(name: str) -> str:
    """Neutraliser un nom de fichier fourni par l'extérieur.

    Les séparateurs Windows sont convertis avant ``basename`` (sous Linux, ``\\``
    n'en est pas un) et les points de tête sont retirés pour écarter toute
    tentative de remontée de dossier.
    """
    brut = (name or "").replace("\\", "/")
    cleaned = SAFE_NAME.sub("_", os.path.basename(brut)).lstrip(".")
    return cleaned[:100] or "piece_jointe"


async def _async_collect(
    api: Any, message_id: str, attachments: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], bytes]]:
    """Réunir le contenu binaire de chaque pièce jointe.

    Le champ ``data`` du webhook est documenté comme facultatif. Quand il
    manque, la pièce jointe est téléchargée depuis l'appareil via
    ``GET /inbox/{id}/attachments/{partId}`` plutôt que d'être abandonnée.
    """
    resolues: list[tuple[dict[str, Any], bytes]] = []

    for attachment in attachments:
        binaire: bytes | None = None
        data = attachment.get("data")

        if data:
            try:
                binaire = base64.b64decode(data)
            except (binascii.Error, ValueError):
                _LOGGER.warning(
                    "Pièce jointe %s : base64 invalide", attachment.get("name")
                )

        if binaire is None:
            part_id = attachment.get("partId")
            if part_id is None or not message_id:
                _LOGGER.debug(
                    "Pièce jointe %s sans contenu ni partId, ignorée",
                    attachment.get("name"),
                )
                continue
            try:
                binaire = await api.async_download_attachment(message_id, part_id)
            except Exception as err:  # noqa: BLE001 - une pièce ne bloque pas le lot
                _LOGGER.warning(
                    "Téléchargement de la pièce jointe %s/%s impossible: %s",
                    message_id,
                    part_id,
                    err,
                )
                continue

        resolues.append((attachment, binaire))

    return resolues


def _write_attachments(
    directory: str, resolues: list[tuple[dict[str, Any], bytes]], keep: int
) -> list[dict[str, Any]]:
    """Écrire les pièces jointes sur disque et purger les plus anciennes.

    Appel bloquant : exécuté dans l'executor.
    """
    os.makedirs(directory, exist_ok=True)
    horodatage = dt_util.now().strftime("%Y%m%d-%H%M%S")
    ecrites: list[dict[str, Any]] = []

    for index, (attachment, binaire) in enumerate(resolues):
        nom = f"{horodatage}_{index}_{_safe_filename(attachment.get('name', ''))}"
        chemin = os.path.join(directory, nom)
        with open(chemin, "wb") as handle:
            handle.write(binaire)

        ecrites.append(
            {
                "path": chemin,
                "name": nom,
                "content_type": attachment.get("contentType", ""),
                "size": len(binaire),
            }
        )

    # Rétention : on ne garde que les N fichiers les plus récents.
    keep = max(1, int(keep))
    try:
        fichiers = sorted(
            (os.path.join(directory, f) for f in os.listdir(directory)),
            key=os.path.getmtime,
            reverse=True,
        )
        for obsolete in fichiers[keep:]:
            os.remove(obsolete)
    except OSError as err:
        _LOGGER.debug("Purge des pièces jointes impossible: %s", err)

    return ecrites


# Noms rencontrés en amont pour l'horodatage de réception, par ordre de priorité.
CLES_HORODATAGE = ("receivedAt", "received_at", "timestamp", "date", "sentAt")


def _horodatage(body: dict[str, Any]) -> str:
    """Extraire un horodatage exploitable du payload.

    L'application ne renseigne pas toujours le champ, et selon la version il
    porte un nom ou un format différent : ISO 8601, secondes ou millisecondes
    depuis l'époque. Une valeur absente ou nulle donnerait 1970 dans l'interface,
    donc on retombe sur l'heure de réception par Home Assistant, à quelques
    secondes près de l'heure réelle.
    """
    for cle in CLES_HORODATAGE:
        brut = body.get(cle)
        if brut in (None, "", 0, "0"):
            continue

        if isinstance(brut, (int, float)):
            # Millisecondes au-delà de ~1973 en secondes : on ramène en secondes.
            secondes = brut / 1000 if brut > 1e11 else brut
            try:
                return dt_util.utc_from_timestamp(secondes).isoformat()
            except (OverflowError, OSError, ValueError):
                continue

        if (parse := dt_util.parse_datetime(str(brut))) is not None:
            return parse.isoformat()

        _LOGGER.debug("Horodatage %s non exploitable: %r", cle, brut)

    return dt_util.now().isoformat()


def _champ(body: dict[str, Any], *noms: str) -> Any:
    """Retourner le premier champ renseigné parmi plusieurs noms.

    La documentation à paraître renomme ``phoneNumber`` en ``sender`` et
    ``recipient`` selon le sens du message. En acceptant les deux, un même
    code fonctionne avant et après la mise à jour de l'application.
    """
    for nom in noms:
        valeur = body.get(nom)
        if valeur is not None:
            return valeur
    return None


def _normalise(payload: Any) -> list[dict[str, Any]]:
    """Ramener un payload simple ou groupé à une liste d'événements."""
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _signature_valide(cle: str, corps: str, request: Request) -> bool:
    """Vérifier la signature HMAC-SHA256 du webhook.

    L'application signe ``corps_brut + X-Timestamp`` avec la clé définie dans
    Settings > Webhooks > Signing Key. Le corps doit être celui reçu, avant
    tout parsing JSON : re-sérialiser changerait les espaces et l'ordre des
    clés, donc la signature.
    """
    signature = request.headers.get("X-Signature", "")
    horodatage = request.headers.get("X-Timestamp", "")
    if not signature or not horodatage:
        _LOGGER.warning("Webhook sans signature alors qu'une clé est configurée")
        return False

    try:
        envoye_a = int(horodatage)
    except ValueError:
        _LOGGER.warning("X-Timestamp illisible")
        return False

    # Fenêtre temporelle : sans elle, une requête interceptée resterait
    # rejouable indéfiniment avec sa signature d'origine.
    if abs(time.time() - envoye_a) > SIGNATURE_TOLERANCE_SECONDS:
        _LOGGER.warning("Webhook hors de la fenêtre temporelle acceptée")
        return False

    attendu = hmac.new(
        cle.encode(), (corps + horodatage).encode(), hashlib.sha256
    ).hexdigest()
    # Comparaison à temps constant : une comparaison naïve laisserait fuir
    # la signature attendue par mesure du temps de réponse.
    if not hmac.compare_digest(attendu, signature):
        _LOGGER.warning("Signature de webhook invalide")
        # L'ordre de concaténation vient de la documentation, jamais éprouvé
        # contre une vraie requête. En cas d'échec on teste les variantes
        # plausibles pour dire laquelle correspond, plutôt que de laisser
        # chercher à l'aveugle. Aucune valeur secrète n'est journalisée.
        if _LOGGER.isEnabledFor(logging.DEBUG):
            variantes = {
                "corps+horodatage": corps + horodatage,
                "horodatage+corps": horodatage + corps,
                "corps seul": corps,
            }
            for nom, contenu in variantes.items():
                calcul = hmac.new(
                    cle.encode(), contenu.encode(), hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(calcul, signature):
                    _LOGGER.debug(
                        "La signature correspond à la variante « %s » : "
                        "signaler ce message pour correction", nom
                    )
                    break
            else:
                _LOGGER.debug(
                    "Aucune variante ne correspond : la clé configurée diffère "
                    "probablement de celle de l'application"
                )
        return False

    return True


async def async_handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: Request
) -> Response:
    """Traiter un POST entrant."""
    entry: ConfigEntry | None = None
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate.data.get(CONF_WEBHOOK_ID) == webhook_id:
            entry = candidate
            break

    if entry is None or not hasattr(entry, "runtime_data"):
        return Response(status=404)

    corps = await request.text()

    # Journalisé quelle que soit la configuration : c'est le seul moyen de
    # savoir si l'application signe réellement ses envois, sans avoir à
    # activer la vérification et risquer de tout bloquer.
    _LOGGER.debug(
        "Webhook reçu — X-Signature: %s, X-Timestamp: %s",
        "présent" if request.headers.get("X-Signature") else "absent",
        request.headers.get("X-Timestamp", "absent"),
    )

    cle = entry.options.get(CONF_SIGNING_KEY)
    if cle and not _signature_valide(cle, corps, request):
        return Response(status=401)

    try:
        payload = json.loads(corps)
    except ValueError:
        _LOGGER.warning("Webhook SMSGateway : corps non JSON")
        return Response(status=400)

    # L'application attend une réponse 2xx en moins de 30 secondes, faute de
    # quoi elle rejoue l'événement en backoff exponentiel — et les pièces
    # jointes seraient écrites en double. Le traitement, qui peut inclure un
    # téléchargement, part donc en tâche de fond et on répond tout de suite.
    for item in _normalise(payload):
        entry.async_create_background_task(
            hass,
            _async_dispatch_protege(hass, entry, item),
            name=f"smsgate_{item.get('event', 'inconnu')}",
        )

    return Response(status=200)


async def _async_dispatch_protege(
    hass: HomeAssistant, entry: ConfigEntry, item: dict[str, Any]
) -> None:
    """Traiter un événement sans qu'un échec ne remonte dans la tâche de fond."""
    try:
        await _async_dispatch(hass, entry, item)
    except Exception:  # noqa: BLE001 - un item ne doit pas casser les autres
        _LOGGER.exception("Échec du traitement d'un événement SMSGateway")


async def _async_dispatch(
    hass: HomeAssistant, entry: ConfigEntry, item: dict[str, Any]
) -> None:
    """Router un événement unitaire."""
    data = entry.runtime_data
    coordinator = data.coordinator
    event = item.get("event", "")
    body = item.get("payload") or {}
    _LOGGER.debug("Evenement %s, payload brut: %s", event, body)

    if event == EVENT_SMS_RECEIVED:
        contenu = {
            "sender": _champ(body, "sender", "phoneNumber"),
            "message": body.get("message"),
            "sim": body.get("simNumber"),
            "received_at": _horodatage(body),
            "message_id": body.get("messageId"),
            "device_id": item.get("deviceId"),
        }
        hass.bus.async_fire(HA_EVENT_SMS_RECEIVED, contenu)
        async_dispatcher_send(hass, SIGNAL_SMS_RECEIVED.format(entry.entry_id), contenu)

    elif event == EVENT_MMS_RECEIVED:
        hass.bus.async_fire(
            HA_EVENT_MMS_NOTIFIED,
            {
                "sender": _champ(body, "sender", "phoneNumber"),
                "subject": body.get("subject"),
                "size": body.get("size"),
                "content_class": body.get("contentClass"),
                "message_id": body.get("messageId"),
            },
        )

    elif event == EVENT_MMS_DOWNLOADED:
        media_dir = hass.config.path(
            entry.options.get(CONF_MEDIA_DIR, DEFAULT_MEDIA_DIR)
        )
        # NumberSelector renvoie un float : sans conversion, le slice de purge
        # leve TypeError. Les options deja enregistrees sont concernees.
        try:
            keep = int(entry.options.get(CONF_KEEP_ATTACHMENTS, DEFAULT_KEEP_ATTACHMENTS))
        except (TypeError, ValueError):
            keep = DEFAULT_KEEP_ATTACHMENTS
        attachments = body.get("attachments") or []

        resolues = await _async_collect(
            data.api, body.get("messageId", ""), attachments
        )
        fichiers = await hass.async_add_executor_job(
            _write_attachments, media_dir, resolues, keep
        )

        contenu = {
            "sender": _champ(body, "sender", "phoneNumber"),
            "subject": body.get("subject"),
            "message": body.get("body"),
            "received_at": _horodatage(body),
            "message_id": body.get("messageId"),
            "attachments": fichiers,
        }
        hass.bus.async_fire(HA_EVENT_MMS_RECEIVED, contenu)
        async_dispatcher_send(hass, SIGNAL_MMS_RECEIVED.format(entry.entry_id), contenu)

    elif event in (EVENT_SMS_SENT, EVENT_SMS_DELIVERED, EVENT_SMS_FAILED):
        message_id = body.get("messageId", "")
        etat = event.split(":", 1)[1]
        coordinator.update_message_state(message_id, etat)
        contenu = {
            "state": etat,
            "message_id": message_id,
            "recipient": _champ(body, "recipient", "phoneNumber"),
        }
        hass.bus.async_fire(HA_EVENT_STATUS, contenu)
        async_dispatcher_send(hass, SIGNAL_STATUS.format(entry.entry_id), contenu)

    elif event == EVENT_SYSTEM_PING:
        coordinator.note_ping()
        async_dispatcher_send(hass, SIGNAL_PING.format(entry.entry_id))

    else:
        _LOGGER.debug("Événement SMSGateway ignoré: %s", event)
