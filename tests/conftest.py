"""Fixtures des tests SMSGateway."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Activer le chargement des intégrations custom dans tous les tests."""
    yield
