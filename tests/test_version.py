"""Contrôle de la version minimale de l'application."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow

from custom_components.smsgate.config_flow import _parse_version, _version_trop_ancienne

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/message"}


@pytest.mark.parametrize(("brut", "attendu"), [
    ("1.74.1", (1, 74, 1)), ("v1.74.1", (1, 74, 1)),
    ("1.74.1-beta", (1, 74, 1)), ("1.74.1+build9", (1, 74, 1)),
    ("2.0", (2, 0)), ("", None), ("inconnue", None), ("1.x.3", None),
])
def test_parse(brut, attendu):
    assert _parse_version(brut) == attendu


@pytest.mark.parametrize(("version", "bloque"), [
    ("1.74.1", False), ("1.75.0", False), ("2.0.0", False),
    ("1.74.0", True), ("1.68.0", True), ("1.0.0", True),
    # Une version absente ou illisible ne doit jamais bloquer
    (None, False), ("", False), ("inconnue", False), ("1.x", False),
])
def test_seuil(version, bloque):
    assert _version_trop_ancienne(version) is bloque


async def _lancer(hass, version):
    r = await hass.config_entries.flow.async_init(
        "smsgate", context={"source": config_entries.SOURCE_USER})
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value=version)),
        # On isole le config flow : le démarrage de l'entrée est testé ailleurs
        patch("custom_components.smsgate.async_setup_entry",
              new=AsyncMock(return_value=True)),
    ):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()
    return r


async def test_version_trop_ancienne_refusee(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    r = await _lancer(hass, "1.68.0")
    assert r["type"] == data_entry_flow.FlowResultType.FORM
    assert r["errors"] == {"base": "unsupported_version"}
    assert r["description_placeholders"]["version"] == "1.68.0"
    assert r["description_placeholders"]["minimum"] == "1.74.1"


async def test_version_suffisante_acceptee(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    r = await _lancer(hass, "1.74.1")
    assert r["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_version_absente_ne_bloque_pas(hass):
    """Si /health n'expose pas la version, l'installation doit rester possible."""
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    r = await _lancer(hass, None)
    assert r["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
