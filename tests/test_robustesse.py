"""Régressions : webhook réenregistré, réauthentification, purge confinée."""
import os
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState

from custom_components.smsgate.api import SmsGateAuthError
from custom_components.smsgate.webhook_handler import (
    _write_attachments,
    media_dir_path,
)

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/messages"}


async def _creer_entree(hass):
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


# --- 1. Webhook HA : pas de « Handler is already defined » après un retry ---

async def test_retry_apres_url_corrigee(hass):
    """Sans URL HTTPS l'entrée attend ; une fois l'URL posée, elle doit démarrer.

    Avant correction, le webhook HA était enregistré avant le contrôle d'URL :
    le retry levait ValueError et l'entrée restait cassée jusqu'au redémarrage.
    """
    await hass.config.async_update(external_url=None,
                                   internal_url="http://192.168.12.101:8123")
    entree = await _creer_entree(hass)
    assert entree.state is ConfigEntryState.SETUP_RETRY

    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    assert await hass.config_entries.async_reload(entree.entry_id)
    await hass.async_block_till_done()

    assert entree.state is ConfigEntryState.LOADED


async def test_rechargements_successifs(hass):
    """Le webhook HA est retiré au déchargement : on peut recharger en boucle."""
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    entree = await _creer_entree(hass)
    for _ in range(3):
        assert await hass.config_entries.async_reload(entree.entry_id)
        await hass.async_block_till_done()
        assert entree.state is ConfigEntryState.LOADED


# --- 2. Identifiants refusés : flux de réauthentification ------------------

async def test_auth_refusee_declenche_reauth(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with patch("custom_components.smsgate.SmsGateApi.async_health",
               new=AsyncMock(side_effect=SmsGateAuthError("401"))):
        entree = await _creer_entree(hass)

    assert entree.state is ConfigEntryState.SETUP_ERROR
    flux = hass.config_entries.flow.async_progress_by_handler("smsgate")
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flux), \
        "un flux de réauthentification doit être proposé"


# --- 3. Purge : seuls les fichiers de l'intégration -------------------------

def _pj(nom):
    return ({"name": nom, "contentType": "image/jpeg"}, b"X")


def test_purge_epargne_les_fichiers_utilisateur(tmp_path):
    """Un dossier partagé ne doit perdre aucun fichier étranger à l'intégration."""
    for nom in ("vacances.jpg", "notes.txt", "20260101-120000.jpg"):
        (tmp_path / nom).write_bytes(b"perso")
    (tmp_path / "sous-dossier").mkdir()

    for i in range(10):
        _write_attachments(str(tmp_path), [_pj(f"p{i}.jpg")], 3)

    restants = set(os.listdir(tmp_path))
    assert {"vacances.jpg", "notes.txt", "20260101-120000.jpg", "sous-dossier"} <= restants
    a_nous = [f for f in restants if f[:8].isdigit() and "_" in f]
    assert len(a_nous) == 3, f"rétention attendue à 3, obtenu {len(a_nous)}"


def test_dossier_confine_au_config(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    assert media_dir_path(hass, "media/smsgate") == os.path.realpath(
        tmp_path / "media" / "smsgate")
    for hors in ("/etc", "/tmp", "../dehors", "media/../../dehors", "", "."):
        assert media_dir_path(hass, hors) is None, hors


def test_lien_symbolique_sortant_refuse(hass, tmp_path):
    """Un lien sous /config pointant ailleurs ne doit pas ouvrir la purge."""
    config = tmp_path / "config"
    dehors = tmp_path / "dehors"
    config.mkdir()
    dehors.mkdir()
    (config / "piege").symlink_to(dehors)
    hass.config.config_dir = str(config)
    assert media_dir_path(hass, "piege") is None


async def test_option_dossier_hors_config_refusee(hass):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    entree = await _creer_entree(hass)
    r = await hass.config_entries.options.async_init(entree.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"media_dir": "/home", "keep_attachments": 50})
    assert r["type"] == "form"
    assert r["errors"] == {"media_dir": "invalid_media_dir"}
    assert "media_dir" not in entree.options, "rien ne doit être enregistré"
