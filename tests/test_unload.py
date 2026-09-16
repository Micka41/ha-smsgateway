"""Régression : décharger une entrée qui n'a jamais démarré."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries

from custom_components.smsgate.api import SmsGateConnectionError

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/message"}


async def test_retrait_entree_jamais_demarree(hass):
    """Si la passerelle ne répond plus au démarrage, runtime_data n'existe pas.

    Retirer l'entrée dans cet état levait AttributeError dans async_unload_entry.
    """
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
        # La passerelle devient injoignable juste apres la configuration
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(side_effect=SmsGateConnectionError("injoignable"))),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()

        entree = hass.config_entries.async_entries("smsgate")[0]
        assert entree.state is config_entries.ConfigEntryState.SETUP_RETRY
        assert not hasattr(entree, "runtime_data"), \
            "le premier rafraichissement a echoue avant l'affectation"

        resultat = await hass.config_entries.async_remove(entree.entry_id)
        await hass.async_block_till_done()

    assert resultat["require_restart"] is False
    assert hass.config_entries.async_entries("smsgate") == []
    print("\n✅ entree jamais demarree retiree sans AttributeError")
