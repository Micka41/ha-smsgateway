"""Reconfiguration d'une passerelle sans la supprimer."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_WEBHOOK_ID


def _flux_reconfigure(hass, entree):
    return hass.config_entries.flow.async_init(
        "smsgate",
        context={"source": config_entries.SOURCE_RECONFIGURE,
                 "entry_id": entree.entry_id},
    )

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/message"}
NOUVELLE = {"host": "192.168.11.150", "port": 8080,
            "username": "sms", "password": "nouveau", "message_path": "/message"}


async def _installer(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
        patch("custom_components.smsgate.async_setup_entry",
              new=AsyncMock(return_value=True)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()
    return hass.config_entries.async_entries("smsgate")[0]


async def test_formulaire_prerempli(hass):
    entree = await _installer(hass)
    r = await _flux_reconfigure(hass, entree)
    assert r["type"] == data_entry_flow.FlowResultType.FORM
    assert r["step_id"] == "reconfigure"
    # voluptuous met UNDEFINED, pas None, sur les cles sans valeur par defaut
    import voluptuous as vol
    champs = {str(k): k.default() for k in r["data_schema"].schema
              if getattr(k, "default", vol.UNDEFINED) is not vol.UNDEFINED}
    assert champs["host"] == "192.168.11.103"
    assert champs["port"] == 8080
    assert champs["username"] == "sms"
    assert "password" not in champs, "le mot de passe ne doit pas etre prerempli"
    print("\n✅ formulaire prerempli avec l'adresse courante")


async def test_changement_ip(hass):
    """L'IP change, l'entité et son unique_id survivent."""
    entree = await _installer(hass)
    ancien_uid = entree.unique_id
    ancien_webhook = entree.data[CONF_WEBHOOK_ID]

    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
        patch("custom_components.smsgate.async_setup_entry",
              new=AsyncMock(return_value=True)),
    ):
        r = await _flux_reconfigure(hass, entree)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], NOUVELLE)
        await hass.async_block_till_done()

    assert r["type"] == data_entry_flow.FlowResultType.ABORT
    assert r["reason"] == "reconfigure_successful"
    e = hass.config_entries.async_entries("smsgate")[0]
    assert e.data[CONF_HOST] == "192.168.11.150"
    assert e.data["password"] == "nouveau"
    assert e.unique_id == ancien_uid, "l'identite ne doit pas suivre l'adresse"
    assert e.data[CONF_WEBHOOK_ID] == ancien_webhook, "le webhook HA doit survivre"
    assert len(hass.config_entries.async_entries("smsgate")) == 1
    print("\n✅ IP changee, unique_id et webhook_id preserves, une seule entree")


async def test_hote_injoignable_refuse(hass):
    """Une adresse erronée ne doit pas être enregistrée."""
    from custom_components.smsgate.api import SmsGateConnectionError
    entree = await _installer(hass)
    with patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
               new=AsyncMock(side_effect=SmsGateConnectionError("boom"))):
        r = await _flux_reconfigure(hass, entree)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], NOUVELLE)
    assert r["type"] == data_entry_flow.FlowResultType.FORM
    assert r["errors"] == {"base": "cannot_connect"}
    e = hass.config_entries.async_entries("smsgate")[0]
    assert e.data[CONF_HOST] == "192.168.11.103", "l'ancienne adresse reste active"
    print("\n✅ adresse injoignable refusee, configuration inchangee")
