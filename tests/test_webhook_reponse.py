"""Réponse immédiate et rejet des webhooks non signés."""
import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_WEBHOOK_ID

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/messages"}
EVENEMENT = {"event": "sms:received",
             "payload": {"phoneNumber": "+33612345678", "message": "Coucou",
                         "messageId": "1", "receivedAt": "2026-09-05T12:00:00+02:00"}}


async def _installer(hass, options=None):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "pass", "version": "1.74.1"})),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()
        entree = hass.config_entries.async_entries("smsgate")[0]
        if options:
            hass.config_entries.async_update_entry(entree, options=options)
            await hass.async_block_till_done()
    return hass.config_entries.async_entries("smsgate")[0]


async def test_reponse_immediate(hass, hass_client_no_auth):
    """Un traitement lent ne doit pas retarder la reponse au-dela des 30 s."""
    entree = await _installer(hass)
    client = await hass_client_no_auth()

    lent = asyncio.Event()

    async def _bloque(*a, **k):
        await asyncio.sleep(3600)  # traitement volontairement interminable

    with patch("custom_components.smsgate.webhook_handler._async_dispatch",
               new=AsyncMock(side_effect=_bloque)):
        debut = time.monotonic()
        r = await client.post(f"/api/webhook/{entree.data[CONF_WEBHOOK_ID]}",
                              json=EVENEMENT)
        duree = time.monotonic() - debut

    assert r.status == 200
    assert duree < 1, f"reponse en {duree:.1f}s alors que le traitement dure 1h"
    print(f"\n✅ reponse en {duree*1000:.0f} ms malgre un traitement bloquant")


async def test_sans_cle_accepte(hass, hass_client_no_auth):
    entree = await _installer(hass)
    client = await hass_client_no_auth()
    r = await client.post(f"/api/webhook/{entree.data[CONF_WEBHOOK_ID]}", json=EVENEMENT)
    assert r.status == 200
    print("\n✅ sans cle configuree : accepte")


async def test_avec_cle_signature_valide(hass, hass_client_no_auth):
    entree = await _installer(hass, {"signing_key": "ma-cle"})
    client = await hass_client_no_auth()
    corps = json.dumps(EVENEMENT)
    h = str(int(time.time()))
    sig = hmac.new(b"ma-cle", (corps + h).encode(), hashlib.sha256).hexdigest()
    r = await client.post(f"/api/webhook/{entree.data[CONF_WEBHOOK_ID]}",
                          data=corps,
                          headers={"Content-Type": "application/json",
                                   "X-Signature": sig, "X-Timestamp": h})
    assert r.status == 200
    print("\n✅ signature valide : accepte")


async def test_avec_cle_signature_absente_rejete(hass, hass_client_no_auth):
    """Une fois la cle posee, un faux SMS non signe doit etre refuse."""
    entree = await _installer(hass, {"signing_key": "ma-cle"})
    client = await hass_client_no_auth()
    r = await client.post(f"/api/webhook/{entree.data[CONF_WEBHOOK_ID]}", json=EVENEMENT)
    print("\noptions vues:", dict(entree.options), "| etat:", entree.state)
    print("statut obtenu:", r.status)
    assert r.status == 401
    print("\n✅ non signe alors qu'une cle existe : rejete en 401")
