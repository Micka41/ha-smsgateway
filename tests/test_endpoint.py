"""Bascule automatique entre /messages et /message."""
import pytest

from custom_components.smsgate.api import SmsGateApi, SmsGateNotFound


class _Api(SmsGateApi):
    """Simule un serveur n'exposant qu'un seul des deux endpoints."""

    def __init__(self, expose):
        super().__init__(None, "h", 8080, "u", "p")
        self.expose, self.appels = expose, []

    async def _request(self, method, path, payload=None):
        self.appels.append(path)
        if path != self.expose:
            raise SmsGateNotFound(f"{path} absent")
        return {"id": "abc"}


async def test_serveur_moderne():
    a = _Api("/messages")
    assert (await a.async_send_sms(["+33"], "x"))["id"] == "abc"
    assert a.appels == ["/messages"], "aucun aller-retour inutile"


async def test_serveur_ancien_bascule():
    a = _Api("/message")
    assert (await a.async_send_sms(["+33"], "x"))["id"] == "abc"
    assert a.appels == ["/messages", "/message"]


async def test_bascule_memorisee():
    """Le chemin qui marche est retenu : une seule requete ensuite."""
    a = _Api("/message")
    await a.async_send_sms(["+33"], "x")
    a.appels.clear()
    await a.async_send_sms(["+33"], "y")
    assert a.appels == ["/message"]


async def test_aucun_des_deux():
    a = _Api("/inexistant")
    with pytest.raises(SmsGateNotFound):
        await a.async_send_sms(["+33"], "x")
