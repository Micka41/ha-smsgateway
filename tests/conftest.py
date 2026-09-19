"""Fixtures des tests SMSGateway."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Activer le chargement des intégrations custom dans tous les tests."""
    yield


@pytest.fixture(autouse=True)
def api_sans_reseau():
    """Neutraliser les appels réseau pour toute la durée du test.

    Sans ça, le déchargement d'une entrée en fin de test appelle
    async_delete_webhook sur le vrai téléphone : pytest-socket bloque la
    connexion et l'erreur remonte en teardown, rendant la suite instable.
    Les tests qui vérifient ces appels posent leur propre patch, prioritaire.
    """
    with (
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value={"status": "pass", "version": "1.74.1"})),
    ):
        yield
