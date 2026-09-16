"""Écriture et purge des pièces jointes."""
import base64
import os

import pytest
from custom_components.smsgate.webhook_handler import _async_collect, _write_attachments


def _pj(nom, contenu=b"X"):
    return ({"name": nom, "contentType": "image/jpeg"}, contenu)


@pytest.mark.parametrize("keep", [50.0, 50, "50", 3.0])
def test_keep_non_entier(tmp_path, keep):
    """Un float venant de NumberSelector ne doit plus lever TypeError."""
    assert len(_write_attachments(str(tmp_path), [_pj("a.jpg")], keep)) == 1


def test_purge_effective(tmp_path):
    for i in range(10):
        _write_attachments(str(tmp_path), [_pj(f"p{i}.jpg")], 4.0)
    assert len(os.listdir(tmp_path)) == 4


def test_keep_zero(tmp_path):
    r = _write_attachments(str(tmp_path), [_pj("a.jpg")], 0)
    assert len(r) == 1 and len(os.listdir(tmp_path)) == 1


def test_gros_fichier(tmp_path):
    """300 Ko : le cas que shell_command ne pouvait pas traiter."""
    r = _write_attachments(str(tmp_path), [_pj("gros.jpg", os.urandom(300_000))], 50)
    assert r[0]["size"] == 300_000


class _ApiFactice:
    def __init__(self, contenu=None, erreur=None):
        self.contenu, self.erreur, self.appels = contenu, erreur, []

    async def async_download_attachment(self, message_id, part_id):
        self.appels.append((message_id, part_id))
        if self.erreur:
            raise self.erreur
        return self.contenu


async def test_collecte_depuis_base64():
    api = _ApiFactice()
    r = await _async_collect(api, "546", [
        {"name": "a.jpg", "data": base64.b64encode(b"JPEG").decode(), "partId": 1621}])
    assert r[0][1] == b"JPEG"
    assert api.appels == [], "le base64 present evite l'appel reseau"


async def test_collecte_via_api_si_data_absent():
    """data facultatif : la piece jointe est telechargee au lieu d'etre perdue."""
    api = _ApiFactice(contenu=b"BINAIRE")
    r = await _async_collect(api, "546", [
        {"name": "a.jpg", "data": None, "partId": 1621, "contentType": "image/jpeg"}])
    assert r[0][1] == b"BINAIRE"
    assert api.appels == [("546", 1621)]


async def test_collecte_base64_invalide_bascule_sur_api():
    api = _ApiFactice(contenu=b"BINAIRE")
    r = await _async_collect(api, "546", [
        {"name": "a.jpg", "data": "!!!pas-du-base64!!!", "partId": 1621}])
    assert r[0][1] == b"BINAIRE"


async def test_collecte_sans_partid_ignoree():
    api = _ApiFactice(contenu=b"BINAIRE")
    r = await _async_collect(api, "546", [{"name": "a.jpg", "data": None}])
    assert r == [] and api.appels == []


async def test_echec_telechargement_nen_bloque_pas_les_autres():
    api = _ApiFactice(erreur=RuntimeError("404"))
    r = await _async_collect(api, "546", [
        {"name": "ko.jpg", "data": None, "partId": 1},
        {"name": "ok.jpg", "data": base64.b64encode(b"OK").decode()},
    ])
    assert len(r) == 1 and r[0][1] == b"OK"
