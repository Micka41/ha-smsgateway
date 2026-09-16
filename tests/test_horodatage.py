"""Normalisation de l'horodatage de réception."""
from custom_components.smsgate.webhook_handler import _horodatage


def test_iso8601():
    r = _horodatage({"receivedAt": "2026-09-05T10:12:45+02:00"})
    assert r.startswith("2026-09-05T10:12:45")


def test_iso_sans_fuseau():
    assert _horodatage({"receivedAt": "2026-09-05T10:12:45"}).startswith("2026-09-05T10:12:45")


def test_epoch_secondes():
    assert _horodatage({"receivedAt": 1757059965}).startswith("2025-09-05")


def test_epoch_millisecondes():
    assert _horodatage({"receivedAt": 1757059965000}).startswith("2025-09-05")


def test_cle_alternative():
    assert _horodatage({"timestamp": "2026-09-05T10:12:45+02:00"}).startswith("2026-09-05")


import pytest


@pytest.mark.parametrize("body", [{}, {"receivedAt": None}, {"receivedAt": 0},
                                  {"receivedAt": ""}, {"receivedAt": "n'importe quoi"}])
def test_repli_sur_maintenant(body):
    """Aucun cas ne doit produire 1970."""
    r = _horodatage(body)
    assert not r.startswith("1970"), r
    assert r.startswith("20")
    print(f"\n  {body} -> {r}")
