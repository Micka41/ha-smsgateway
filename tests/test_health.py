"""Entités alimentées par /health, sur la réponse réelle du téléphone."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries

SAISIE = {"host": "192.168.11.103", "port": 8080,
          "username": "sms", "password": "secret", "message_path": "/message"}

# Réponse réelle relevée sur l'appareil
SANTE = {
    "checks": {
        "messages:failed": {"description": "Failed messages for last hour",
                            "observedUnit": "messages", "observedValue": 0, "status": "pass"},
        "connection:status": {"description": "Internet connection status",
                              "observedUnit": "boolean", "observedValue": 1, "status": "pass"},
        "connection:transport": {"description": "Network transport type",
                                 "observedUnit": "flags", "observedValue": 4, "status": "pass"},
        "connection:cellular": {"description": "Cellular network type",
                                "observedUnit": "index", "observedValue": 0, "status": "pass"},
        "battery:level": {"description": "Battery level in percent",
                          "observedUnit": "percent", "observedValue": 74, "status": "pass"},
        "battery:charging": {"description": "Is the phone charging?",
                             "observedUnit": "flags", "observedValue": 0, "status": "pass"},
    },
    "releaseId": 1540, "status": "pass", "version": "1.74.1",
}


async def _installer(hass, sante):
    await hass.config.async_update(external_url="https://ha.mpicaud.com")
    with (
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_check_credentials",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.config_flow.SmsGateApi.async_version",
              new=AsyncMock(return_value="1.74.1")),
        patch("custom_components.smsgate.SmsGateApi.async_health",
              new=AsyncMock(return_value=sante)),
        patch("custom_components.smsgate.SmsGateApi.async_register_webhook",
              new=AsyncMock(return_value=None)),
        patch("custom_components.smsgate.SmsGateApi.async_delete_webhook",
              new=AsyncMock(return_value=None)),
    ):
        r = await hass.config_entries.flow.async_init(
            "smsgate", context={"source": config_entries.SOURCE_USER})
        await hass.config_entries.flow.async_configure(r["flow_id"], SAISIE)
        await hass.async_block_till_done()


async def test_entites_sante(hass):
    """Chaque contrôle produit la bonne valeur."""
    await _installer(hass, SANTE)
    p = "192_168_11_103"

    batterie = hass.states.get(f"sensor.smsgateway_{p}_battery")
    assert batterie.state == "74"
    assert batterie.attributes["device_class"] == "battery"
    assert batterie.attributes["unit_of_measurement"] == "%"

    echecs = hass.states.get(f"sensor.smsgateway_{p}_failed_messages")
    assert echecs.state == "0"

    net = hass.states.get(f"binary_sensor.smsgateway_{p}_internet_connection")
    assert net.state == "on"

    charge = hass.states.get(f"binary_sensor.smsgateway_{p}_charging")
    assert charge.state == "off", "0 = pas en charge"

    dispo = hass.states.get(f"binary_sensor.smsgateway_{p}_available")
    assert dispo.attributes["transport_raw"] == 4
    assert dispo.attributes["cellular_raw"] == 0
    print("\n✅ batterie 74%, echecs 0, internet on, charge off, bruts exposes")


async def test_charge_sans_fil(hass):
    """observedValue=4 (sans fil) doit compter comme en charge."""
    sante = {**SANTE, "checks": {**SANTE["checks"],
             "battery:charging": {"observedUnit": "flags", "observedValue": 4, "status": "pass"}}}
    await _installer(hass, sante)
    etat = hass.states.get("binary_sensor.smsgateway_192_168_11_103_charging")
    assert etat.state == "on", "drapeau non nul = en charge"
    print("\n✅ drapeau 4 interprete comme en charge")


async def test_check_en_echec_rend_indisponible(hass):
    """Un contrôle en 'fail' ne doit pas produire de valeur inventée."""
    sante = {**SANTE, "checks": {**SANTE["checks"],
             "battery:level": {"observedUnit": "percent", "observedValue": 0, "status": "fail"}}}
    await _installer(hass, sante)
    etat = hass.states.get("sensor.smsgateway_192_168_11_103_battery")
    assert etat.state == "unavailable"
    print("\n✅ statut fail -> entite indisponible, pas de 0 trompeur")


async def test_check_absent(hass):
    """Un /health sans checks ne doit pas casser l'intégration."""
    await _installer(hass, {"status": "pass", "version": "1.74.1"})
    etat = hass.states.get("sensor.smsgateway_192_168_11_103_battery")
    assert etat.state == "unavailable"
    assert hass.states.get("sensor.smsgateway_192_168_11_103_last_sms") is not None
    print("\n✅ checks absents : degradation propre")
