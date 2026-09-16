"""Vérification de la signature HMAC des webhooks."""
import hashlib
import hmac
import time

import pytest
from custom_components.smsgate.webhook_handler import _signature_valide

CLE = "ma-cle-secrete"
CORPS = '{"event":"sms:received","payload":{"message":"Coucou"}}'


class _Req:
    def __init__(self, **entetes):
        self.headers = entetes


def _signe(corps, horodatage, cle=CLE):
    return hmac.new(cle.encode(), (corps + horodatage).encode(),
                    hashlib.sha256).hexdigest()


def test_signature_valide():
    h = str(int(time.time()))
    r = _Req(**{"X-Signature": _signe(CORPS, h), "X-Timestamp": h})
    assert _signature_valide(CLE, CORPS, r) is True


def test_signature_fausse():
    h = str(int(time.time()))
    r = _Req(**{"X-Signature": "0" * 64, "X-Timestamp": h})
    assert _signature_valide(CLE, CORPS, r) is False


def test_corps_altere():
    """Un corps modifié en transit doit être rejeté."""
    h = str(int(time.time()))
    r = _Req(**{"X-Signature": _signe(CORPS, h), "X-Timestamp": h})
    altere = CORPS.replace("Coucou", "Virement")
    assert _signature_valide(CLE, altere, r) is False


def test_mauvaise_cle():
    h = str(int(time.time()))
    r = _Req(**{"X-Signature": _signe(CORPS, h, "autre-cle"), "X-Timestamp": h})
    assert _signature_valide(CLE, CORPS, r) is False


@pytest.mark.parametrize("decalage", [-3600, -301, 301, 3600])
def test_rejeu_hors_fenetre(decalage):
    """Une requête interceptee ne doit pas rester rejouable."""
    h = str(int(time.time()) + decalage)
    r = _Req(**{"X-Signature": _signe(CORPS, h), "X-Timestamp": h})
    assert _signature_valide(CLE, CORPS, r) is False


@pytest.mark.parametrize("decalage", [-299, 0, 299])
def test_dans_la_fenetre(decalage):
    h = str(int(time.time()) + decalage)
    r = _Req(**{"X-Signature": _signe(CORPS, h), "X-Timestamp": h})
    assert _signature_valide(CLE, CORPS, r) is True


@pytest.mark.parametrize("entetes", [
    {},
    {"X-Signature": "abc"},
    {"X-Timestamp": "123"},
    {"X-Signature": "abc", "X-Timestamp": "pas-un-nombre"},
])
def test_entetes_manquants_ou_invalides(entetes):
    assert _signature_valide(CLE, CORPS, _Req(**entetes)) is False
