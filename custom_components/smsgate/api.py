"""Client de l'API locale de SMS Gateway for Android.

Le client PyPI ``android-sms-gateway`` ne gère pas encore le champ
``mmsMessage``. Plutôt que de faire cohabiter deux piles HTTP et deux chemins
d'authentification pour couvrir SMS d'un côté et MMS de l'autre, tout passe ici
par la session aiohttp partagée de Home Assistant.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from typing import Any

import aiohttp
from aiohttp import BasicAuth, ClientError, ClientTimeout

from .const import DEFAULT_MESSAGE_PATH, LEGACY_MESSAGE_PATH

_LOGGER = logging.getLogger(__name__)

TIMEOUT = ClientTimeout(total=30)


class SmsGateError(Exception):
    """Erreur générique de l'API."""


class SmsGateAuthError(SmsGateError):
    """Identifiants refusés par le Local Server."""


class SmsGateConnectionError(SmsGateError):
    """Passerelle injoignable."""


class SmsGateNotFound(SmsGateError):
    """Ressource absente (HTTP 404)."""


class SmsGateApi:
    """Enveloppe minimale autour de l'API locale."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
        message_path: str = DEFAULT_MESSAGE_PATH,
    ) -> None:
        """Initialiser le client."""
        self._session = session
        self._host = host
        self._port = port
        self._auth = BasicAuth(username, password)
        self._message_path = message_path if message_path.startswith("/") else f"/{message_path}"

    @property
    def base_url(self) -> str:
        """Retourner l'URL de base du Local Server."""
        return f"http://{self._host}:{self._port}"

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        """Exécuter une requête et normaliser les erreurs."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                method, url, json=payload, auth=self._auth, timeout=TIMEOUT
            ) as response:
                body = await response.text()

                if response.status in (401, 403):
                    raise SmsGateAuthError(f"Authentification refusée (HTTP {response.status})")
                if response.status == 404:
                    raise SmsGateNotFound(f"{path} absent (HTTP 404)")
                if response.status >= 400:
                    raise SmsGateError(f"HTTP {response.status}: {body[:200]}")

                if not body.strip():
                    return {}
                try:
                    return json.loads(body)
                except ValueError:
                    return body
        except (ClientError, TimeoutError) as err:
            raise SmsGateConnectionError(f"{url} injoignable: {err}") from err

    # --- Diagnostic ----------------------------------------------------------

    async def async_health(self) -> dict[str, Any]:
        """Interroger l'endpoint de santé du Local Server.

        Il expose la version de l'application, l'état de la connexion et le
        niveau de batterie. En cas d'absence — ancienne version, ou autre
        service à l'écoute sur ce port — on retombe sur ``/webhooks``, dont la
        présence est garantie puisque l'enregistrement l'utilise.
        """
        try:
            result = await self._request("GET", "/health")
        except SmsGateAuthError:
            raise
        except SmsGateError as err:
            _LOGGER.debug("/health indisponible (%s), repli sur /webhooks", err)
            webhooks = await self.async_list_webhooks()
            return {"status": "ok", "webhooks": len(webhooks)}

        return result if isinstance(result, dict) else {"status": "ok"}

    async def async_version(self) -> str | None:
        """Retourner la version applicative, ou None si indisponible."""
        try:
            health = await self.async_health()
        except SmsGateError:
            return None
        version = health.get("version")
        return version if isinstance(version, str) and version else None

    async def async_check_credentials(self) -> None:
        """Valider hôte et identifiants pendant le config flow."""
        await self._request("GET", "/webhooks")

    # --- Envoi ---------------------------------------------------------------

    @staticmethod
    def _base_payload(
        recipients: list[str],
        sim: int | None,
        priority: int | None,
        ttl: int | None,
    ) -> dict[str, Any]:
        """Construire les champs communs SMS/MMS."""
        payload: dict[str, Any] = {"phoneNumbers": recipients}
        if sim is not None:
            payload["simNumber"] = int(sim)
        if priority is not None:
            payload["priority"] = int(priority)
        if ttl is not None:
            payload["ttl"] = int(ttl)
        return payload

    async def _async_post_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Poster un message, en basculant sur l'ancien endpoint si besoin.

        Le swagger documente ``/messages``. Les versions plus anciennes de
        l'application n'exposaient que ``/message`` : plutôt que d'imposer un
        réglage, on bascule une fois sur 404 et on retient le chemin qui marche.
        """
        try:
            result = await self._request("POST", self._message_path, payload)
        except SmsGateNotFound:
            secours = (
                LEGACY_MESSAGE_PATH
                if self._message_path == DEFAULT_MESSAGE_PATH
                else DEFAULT_MESSAGE_PATH
            )
            _LOGGER.info(
                "%s absent, bascule sur %s", self._message_path, secours
            )
            result = await self._request("POST", secours, payload)
            self._message_path = secours
        return result if isinstance(result, dict) else {}

    async def async_download_attachment(self, message_id: str, part_id: int) -> bytes:
        """Télécharger une pièce jointe MMS depuis l'appareil.

        Utilisé quand le webhook ne porte pas le contenu : le champ ``data``
        est documenté comme facultatif.
        """
        url = f"{self.base_url}/inbox/{message_id}/attachments/{part_id}"
        try:
            async with self._session.get(
                url, auth=self._auth, timeout=TIMEOUT
            ) as response:
                if response.status in (401, 403):
                    raise SmsGateAuthError("Authentification refusée")
                if response.status == 404:
                    raise SmsGateNotFound(f"pièce jointe {message_id}/{part_id} absente")
                if response.status >= 400:
                    raise SmsGateError(f"HTTP {response.status}")
                return await response.read()
        except (ClientError, TimeoutError) as err:
            raise SmsGateConnectionError(f"{url} injoignable: {err}") from err

    async def async_send_sms(
        self,
        recipients: list[str],
        message: str,
        sim: int | None = None,
        priority: int | None = None,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """Envoyer un SMS."""
        payload = self._base_payload(recipients, sim, priority, ttl)
        payload["textMessage"] = {"text": message}
        return await self._async_post_message(payload)

    async def async_send_mms(
        self,
        recipients: list[str],
        attachments: list[dict[str, str]],
        message: str | None = None,
        subject: str | None = None,
        sim: int | None = None,
        priority: int | None = None,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """Envoyer un MMS.

        ``attachments`` attend des dicts déjà encodés :
        ``{"contentType": ..., "name": ..., "data": <base64>}``.
        """
        if not attachments:
            raise SmsGateError("Un MMS exige au moins une pièce jointe")

        payload = self._base_payload(recipients, sim, priority, ttl)
        mms: dict[str, Any] = {"attachments": attachments}
        if message:
            mms["text"] = message
        if subject:
            mms["subject"] = subject
        payload["mmsMessage"] = mms
        return await self._async_post_message(payload)

    @staticmethod
    def encode_attachment(path: str) -> dict[str, str]:
        """Lire un fichier et le convertir en pièce jointe MMS.

        Appel bloquant : à exécuter via ``async_add_executor_job``.
        """
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        return {
            "contentType": content_type,
            "name": os.path.basename(path),
            "data": data,
        }

    # --- Webhooks ------------------------------------------------------------

    async def async_list_webhooks(self) -> list[dict[str, Any]]:
        """Lister les webhooks enregistrés côté application."""
        result = await self._request("GET", "/webhooks")
        return result if isinstance(result, list) else []

    async def async_register_webhook(self, webhook_id: str, url: str, event: str) -> None:
        """Enregistrer un webhook."""
        await self._request(
            "POST", "/webhooks", {"id": webhook_id, "url": url, "event": event}
        )

    async def async_delete_webhook(self, webhook_id: str) -> None:
        """Supprimer un webhook, en ignorant une absence."""
        try:
            await self._request("DELETE", f"/webhooks/{webhook_id}")
        except SmsGateError as err:
            _LOGGER.debug("Suppression du webhook %s ignorée: %s", webhook_id, err)
