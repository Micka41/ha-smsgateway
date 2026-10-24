"""Aucune E/S disque bloquante ne doit s'exécuter dans la boucle d'événements.

Le principe : ``realpath`` et ``is_allowed_path`` sont enveloppés d'une sonde
qui note un appel fait depuis un thread portant une boucle asyncio active,
c'est-à-dire la boucle de Home Assistant. Dans l'executor, aucune boucle ne
tourne et la sonde ne relève rien.
"""
import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core_config import Config

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/messages"}


@pytest.fixture
def sonde():
    """Relever les appels bloquants faits depuis la boucle d'événements."""
    fautes: list[str] = []
    realpath = os.path.realpath
    is_allowed = Config.is_allowed_path

    def _dans_la_boucle() -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    def realpath_sonde(*a, **k):
        if _dans_la_boucle():
            fautes.append("os.path.realpath")
        return realpath(*a, **k)

    def is_allowed_sonde(self, path):
        if _dans_la_boucle():
            fautes.append("Config.is_allowed_path")
        return is_allowed(self, path)

    with (
        patch("custom_components.smsgate.webhook_handler.os.path.realpath",
              side_effect=realpath_sonde),
        patch.object(Config, "is_allowed_path", is_allowed_sonde),
    ):
        yield fautes


async def _installer(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()
    return hass.config_entries.async_entries("smsgate")[0]


async def test_options_hors_boucle(hass, sonde):
    entree = await _installer(hass)
    r = await hass.config_entries.options.async_init(entree.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"media_dir": "media/smsgate", "keep_attachments": 50})
    assert r["type"] == "create_entry"
    assert sonde == [], f"appels bloquants dans la boucle : {sonde}"


async def test_mms_telecharge_hors_boucle(hass, hass_client_no_auth, sonde, tmp_path):
    hass.config.config_dir = str(tmp_path)
    entree = await _installer(hass)
    client = await hass_client_no_auth()
    r = await client.post(
        f"/api/webhook/{entree.data[CONF_WEBHOOK_ID]}",
        json={"event": "mms:downloaded", "deviceId": "d",
              "payload": {"messageId": "546", "sender": "+33600000000",
                          "attachments": [{"partId": 1, "name": "a.jpg",
                                           "contentType": "image/jpeg",
                                           "data": "SlBFRw=="}]}},
    )
    assert r.status == 200
    # Le traitement part en tâche de fond : il faut l'attendre explicitement.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert os.listdir(tmp_path / "media" / "smsgate"), "la pièce jointe doit être écrite"
    assert sonde == [], f"appels bloquants dans la boucle : {sonde}"


async def test_envoi_mms_hors_boucle(hass, sonde, tmp_path):
    entree = await _installer(hass)
    fichier = tmp_path / "photo.jpg"
    fichier.write_bytes(b"JPEG")
    hass.config.allowlist_external_dirs = {str(tmp_path)}

    with patch("custom_components.smsgate.SmsGateApi.async_send_mms",
               new=AsyncMock(return_value={"id": "x"})) as envoi:
        await hass.services.async_call(
            "smsgate", "send_mms",
            {"recipients": ["+33600000000"], "attachments": [str(fichier)],
             "config_entry_id": entree.entry_id},
            blocking=True,
        )
    assert envoi.call_count == 1
    assert sonde == [], f"appels bloquants dans la boucle : {sonde}"
