"""Tests du config flow SMSGateway contre un vrai Home Assistant."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_WEBHOOK_ID

from custom_components.smsgate.api import SmsGateAuthError, SmsGateConnectionError

SAISIE = {
    "host": "192.168.11.103",
    "port": 8080,
    "username": "sms",
    "password": "secret",
    "message_path": "/message",
}


async def test_formulaire_affiche(hass):
    """Le flux s'initialise sans UnknownHandler."""
    try:
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER}
        )
    except data_entry_flow.UnknownHandler:
        pytest.fail("UnknownHandler = 'Invalid handler specified'")
    assert r["type"] == data_entry_flow.FlowResultType.FORM
    assert r["step_id"] == "user"


async def test_creation_entree(hass):
    """Une saisie valide crée l'entrée avec un webhook_id généré."""
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    r = await hass.config_entries.flow.async_init(
        "smsgate", context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "ok"})),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()
    assert r["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert r["title"] == "SMSGateway (192.168.11.103)"
    assert CONF_WEBHOOK_ID in r["data"] and len(r["data"][CONF_WEBHOOK_ID]) > 20
    print("\n✅ webhook_id genere:", r["data"][CONF_WEBHOOK_ID])


@pytest.mark.parametrize(
    ("exception", "attendu"),
    [(SmsGateAuthError, "invalid_auth"), (SmsGateConnectionError, "cannot_connect")],
)
async def test_erreurs(hass, exception, attendu):
    """Les erreurs d'API remontent dans le formulaire."""
    r = await hass.config_entries.flow.async_init(
        "smsgate", context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
        new=AsyncMock(side_effect=exception("boom")),
    ):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
    assert r["type"] == data_entry_flow.FlowResultType.FORM
    assert r["errors"] == {"base": attendu}


async def test_doublon(hass):
    """Une même passerelle ne peut pas être ajoutée deux fois."""
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "ok"})),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        for attendu in (
            data_entry_flow.FlowResultType.CREATE_ENTRY,
            data_entry_flow.FlowResultType.ABORT,
        ):
            r = await hass.config_entries.flow.async_init(
                "smsgate", context={"source": config_entries.SOURCE_USER}
            )
            if attendu is data_entry_flow.FlowResultType.ABORT:
                r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
                assert r["reason"] == "already_configured"
            else:
                r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
            assert r["type"] == attendu


async def test_setup_complet_url_https(hass):
    """De bout en bout : entrée créée, webhooks pointés vers l'URL externe HTTPS."""
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    enregistres = []

    async def _register(app_id, url, event):
        enregistres.append((app_id, url, event))

    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "ok"})),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(side_effect=_register)),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()

        entree = hass.config_entries.async_entries("smsgate")[0]
        assert entree.state is config_entries.ConfigEntryState.LOADED, entree.state

        assert len(enregistres) == 7, f"7 evenements attendus, {len(enregistres)}"
        urls = {u for _, u, _ in enregistres}
        assert len(urls) == 1
        url = urls.pop()
        assert url.startswith("https://ha.mpicaud.com/api/webhook/")
        assert entree.data[CONF_WEBHOOK_ID] in url
        print("\n✅ URL enregistree cote application :", url)
        print("✅ evenements :", sorted(e for _, _, e in enregistres))

        etats = hass.states.async_entity_ids()
        print("✅ entites creees :", [e for e in etats if "smsgate" in e])


async def test_refus_si_url_interne_http(hass):
    """Sans URL externe HTTPS, l'entrée ne démarre pas au lieu d'enregistrer une URL morte."""
    await hass.config.async_update(external_url=None, internal_url="http://192.168.12.101:8123")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "ok"})),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)) as reg,
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()

        entree = hass.config_entries.async_entries("smsgate")[0]
        assert entree.state is config_entries.ConfigEntryState.SETUP_RETRY, entree.state
        assert reg.call_count == 0, "aucun webhook ne doit etre enregistre"
        print("\n✅ SETUP_RETRY et aucun webhook enregistre en http interne")
