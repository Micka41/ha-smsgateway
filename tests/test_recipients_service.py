"""Résolution des alias de bout en bout via les services."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/message"}


async def _installer(hass, tmp_path, secrets):
    (tmp_path / "secrets.yaml").write_text(secrets)
    hass.config.config_dir = str(tmp_path)
    hass.data.pop("smsgate_secrets_cache", None)
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


async def test_sms_avec_alias(hass, tmp_path):
    await _installer(hass, tmp_path,
                     'smsgate_papa: "+33612345678"\nlatitude: 47.6\n')
    envoye = AsyncMock(return_value={"id": "abc"})
    with patch("custom_components.smsgate.SmsGateApi.async_send_sms", new=envoye):
        await hass.services.async_call(
            "smsgate", "send_sms",
            {"recipients": ["{PAPA}", "+33600000000"], "message": "Coucou"},
            blocking=True)
    assert envoye.call_args.kwargs["recipients"] == ["+33612345678", "+33600000000"]
    print("\n✅ {PAPA} traduit depuis secrets.yaml")


async def test_secret_non_prefixe_bloque(hass, tmp_path):
    """{LATITUDE} ne doit pas partir par SMS."""
    await _installer(hass, tmp_path,
                     'smsgate_papa: "+33612345678"\nlatitude: 47.6\n')
    envoye = AsyncMock(return_value={"id": "abc"})
    with patch("custom_components.smsgate.SmsGateApi.async_send_sms", new=envoye):
        with pytest.raises(HomeAssistantError) as e:
            await hass.services.async_call(
                "smsgate", "send_sms",
                {"recipients": ["{LATITUDE}"], "message": "x"}, blocking=True)
    assert "47.6" not in str(e.value)
    assert envoye.call_count == 0, "aucun envoi ne doit partir"
    print("\n✅ secret non prefixe inaccessible, rien n'est envoye")
