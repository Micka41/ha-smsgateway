"""Résolution des alias depuis secrets.yaml."""
import pytest

from custom_components.smsgate.recipients import (
    RecipientError,
    _charger,
    async_resolve,
)

SECRETS = """
smsgate_papa: "+33612345678"
smsgate_maman: "+33698765432"
latitude: 47.6
mon_token_api: "sk-tres-secret"
http_password: "motdepasse"
"""


@pytest.fixture
def config(hass, tmp_path):
    """Écrire un secrets.yaml dans le dossier de configuration."""
    def _ecrire(contenu=SECRETS):
        f = tmp_path / "secrets.yaml"
        f.write_text(contenu)
        hass.config.config_dir = str(tmp_path)
        hass.data.pop("smsgate_secrets_cache", None)
        return f
    return _ecrire


def test_seules_les_cles_prefixees(tmp_path):
    """Le filtre par préfixe est la protection centrale."""
    f = tmp_path / "secrets.yaml"
    f.write_text(SECRETS)
    c = _charger(str(f))
    assert c == {"PAPA": "+33612345678", "MAMAN": "+33698765432"}
    assert "LATITUDE" not in c
    assert "MON_TOKEN_API" not in c
    assert "HTTP_PASSWORD" not in c


def test_fichier_absent(tmp_path):
    """Un secrets.yaml absent n'est pas une erreur."""
    assert _charger(str(tmp_path / "inexistant.yaml")) == {}


def test_fichier_vide(tmp_path):
    f = tmp_path / "secrets.yaml"
    f.write_text("")
    assert _charger(str(f)) == {}


def test_yaml_invalide(tmp_path):
    f = tmp_path / "secrets.yaml"
    f.write_text("smsgate_papa: [non ferme\n")
    with pytest.raises(RecipientError) as e:
        _charger(str(f))
    assert "sk-tres-secret" not in str(e.value)


async def test_resolution(hass, config):
    config()
    assert await async_resolve(hass, ["{PAPA}"]) == ["+33612345678"]


async def test_casse_ignoree(hass, config):
    config()
    assert await async_resolve(hass, ["{Papa}"]) == ["+33612345678"]


async def test_melange_avec_numeros(hass, config):
    config()
    r = await async_resolve(hass, ["{PAPA}", "+33600000000", "{MAMAN}"])
    assert r == ["+33612345678", "+33600000000", "+33698765432"]


async def test_numero_litteral_sans_fichier(hass, tmp_path):
    """Sans secrets.yaml, les numéros littéraux fonctionnent."""
    hass.config.config_dir = str(tmp_path)
    hass.data.pop("smsgate_secrets_cache", None)
    assert await async_resolve(hass, ["+33612345678"]) == ["+33612345678"]


async def test_alias_de_secret_non_prefixe_refuse(hass, config):
    """{LATITUDE} ne doit jamais atteindre la valeur du fichier."""
    config()
    with pytest.raises(RecipientError) as e:
        await async_resolve(hass, ["{LATITUDE}"])
    assert "47.6" not in str(e.value)
    assert "MAMAN, PAPA" in str(e.value)


async def test_alias_inconnu_message_utile(hass, config):
    """TONTON n'est pas defini : l'erreur doit dire quoi ajouter, sans fuiter."""
    config()
    with pytest.raises(RecipientError) as e:
        await async_resolve(hass, ["{TONTON}"])
    msg = str(e.value)
    assert "smsgate_tonton" in msg, "l'erreur doit indiquer la clé à créer"
    assert "+33612345678" not in msg, "aucune valeur ne doit fuiter"


async def test_relecture_apres_modification(hass, config):
    """Un numéro corrigé doit être actif sans redémarrage."""
    f = config()
    assert await async_resolve(hass, ["{PAPA}"]) == ["+33612345678"]
    import os, time
    f.write_text('smsgate_papa: "+33699999999"\n')
    os.utime(f, (time.time() + 2, time.time() + 2))
    assert await async_resolve(hass, ["{PAPA}"]) == ["+33699999999"]
