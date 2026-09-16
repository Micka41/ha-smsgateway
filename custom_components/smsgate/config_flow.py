"""Config flow de l'intégration SMSGateway."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_WEBHOOK_ID,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SmsGateApi, SmsGateAuthError, SmsGateConnectionError, SmsGateError
from .const import (
    CONF_CHECK_UPDATES,
    CONF_DEFAULT_RECIPIENT,
    CONF_KEEP_ATTACHMENTS,
    CONF_MEDIA_DIR,
    CONF_MESSAGE_PATH,
    CONF_SIGNING_KEY,
    CONF_WEBHOOK_URL,
    DEFAULT_CHECK_UPDATES,
    DEFAULT_KEEP_ATTACHMENTS,
    DEFAULT_MEDIA_DIR,
    DEFAULT_MESSAGE_PATH,
    DEFAULT_PORT,
    DOMAIN,
    MIN_APP_VERSION,
    MIN_APP_VERSION_STR,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_USERNAME): TextSelector(),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_MESSAGE_PATH, default=DEFAULT_MESSAGE_PATH): TextSelector(),
    }
)


def _parse_version(version: str) -> tuple[int, ...] | None:
    """Convertir "1.74.1" en (1, 74, 1).

    Retourne None si la chaîne n'est pas exploitable : on préfère laisser
    passer une version illisible plutôt que bloquer à tort une installation
    valide.
    """
    coeur = version.strip().lstrip("vV").split("-")[0].split("+")[0]
    morceaux = coeur.split(".")
    if not morceaux or not all(m.isdigit() for m in morceaux):
        return None
    return tuple(int(m) for m in morceaux)


def _version_trop_ancienne(version: str | None) -> bool:
    """Indiquer si la version est lisible ET antérieure au minimum requis."""
    if not version:
        return False
    analysee = _parse_version(version)
    if analysee is None:
        return False
    return analysee < MIN_APP_VERSION


class SmsGateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gérer l'ajout d'une passerelle."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Saisie manuelle des paramètres du Local Server."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = int(user_input[CONF_PORT])

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            api = SmsGateApi(
                session=async_get_clientsession(self.hass),
                host=host,
                port=port,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                message_path=user_input.get(CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH),
            )

            try:
                await api.async_check_credentials()
            except SmsGateAuthError:
                errors["base"] = "invalid_auth"
            except SmsGateConnectionError:
                errors["base"] = "cannot_connect"
            except SmsGateError:
                errors["base"] = "unknown"
            else:
                # Contrôle indicatif : une version absente ou illisible ne
                # bloque pas, seule une version explicitement trop ancienne
                # est refusée.
                version = await api.async_version()
                if _version_trop_ancienne(version):
                    errors["base"] = "unsupported_version"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_SCHEMA,
                        errors=errors,
                        description_placeholders={
                            "version": version or "?",
                            "minimum": MIN_APP_VERSION_STR,
                        },
                    )
                return self.async_create_entry(
                    title=f"SMSGateway ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_MESSAGE_PATH: user_input.get(
                            CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH
                        ),
                        CONF_WEBHOOK_ID: webhook.async_generate_id(),
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Modifier l'adresse, le port ou les identifiants d'une passerelle.

        Accessible par le menu de l'intégration. Les entités, leur historique
        et l'appareil sont conservés : seules les données de connexion changent.
        L'``unique_id`` n'est volontairement pas recalculé — il identifie la
        passerelle, pas son adresse du moment.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = int(user_input[CONF_PORT])

            api = SmsGateApi(
                session=async_get_clientsession(self.hass),
                host=host,
                port=port,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                message_path=user_input.get(CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH),
            )

            try:
                await api.async_check_credentials()
            except SmsGateAuthError:
                errors["base"] = "invalid_auth"
            except SmsGateConnectionError:
                errors["base"] = "cannot_connect"
            except SmsGateError:
                errors["base"] = "unknown"
            else:
                version = await api.async_version()
                if _version_trop_ancienne(version):
                    return self.async_show_form(
                        step_id="reconfigure",
                        data_schema=self._schema_connexion(user_input),
                        errors={"base": "unsupported_version"},
                        description_placeholders={
                            "version": version or "?",
                            "minimum": MIN_APP_VERSION_STR,
                        },
                    )
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_MESSAGE_PATH: user_input.get(
                            CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH
                        ),
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema_connexion(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    def _schema_connexion(valeurs: dict[str, Any]) -> vol.Schema:
        """Formulaire de connexion pré-rempli avec les valeurs courantes."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=valeurs.get(CONF_HOST, "")
                ): TextSelector(),
                vol.Required(
                    CONF_PORT, default=valeurs.get(CONF_PORT, DEFAULT_PORT)
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_USERNAME, default=valeurs.get(CONF_USERNAME, "")
                ): TextSelector(),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_MESSAGE_PATH,
                    default=valeurs.get(CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH),
                ): TextSelector(),
            }
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Relancer la saisie quand les identifiants sont refusés."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirmer les nouveaux identifiants."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api = SmsGateApi(
                session=async_get_clientsession(self.hass),
                host=entry.data[CONF_HOST],
                port=entry.data[CONF_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                message_path=entry.data.get(CONF_MESSAGE_PATH, DEFAULT_MESSAGE_PATH),
            )
            try:
                await api.async_check_credentials()
            except SmsGateAuthError:
                errors["base"] = "invalid_auth"
            except SmsGateError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmsGateOptionsFlow:
        """Retourner le flow d'options."""
        return SmsGateOptionsFlow()


class SmsGateOptionsFlow(OptionsFlow):
    """Options : destinataire par défaut, stockage, URL de webhook."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Afficher et enregistrer les options."""
        if user_input is not None:
            nettoye = {k: v for k, v in user_input.items() if v not in (None, "")}
            # NumberSelector produit des float : on stocke des entiers.
            if CONF_KEEP_ATTACHMENTS in nettoye:
                nettoye[CONF_KEEP_ATTACHMENTS] = int(nettoye[CONF_KEEP_ATTACHMENTS])
            return self.async_create_entry(data=nettoye)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEFAULT_RECIPIENT,
                    description={
                        "suggested_value": options.get(CONF_DEFAULT_RECIPIENT, "")
                    },
                ): TextSelector(),
                vol.Optional(
                    CONF_MEDIA_DIR,
                    default=options.get(CONF_MEDIA_DIR, DEFAULT_MEDIA_DIR),
                ): TextSelector(),
                vol.Optional(
                    CONF_KEEP_ATTACHMENTS,
                    default=options.get(CONF_KEEP_ATTACHMENTS, DEFAULT_KEEP_ATTACHMENTS),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=1000, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_CHECK_UPDATES,
                    default=options.get(CONF_CHECK_UPDATES, DEFAULT_CHECK_UPDATES),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_WEBHOOK_URL,
                    description={"suggested_value": options.get(CONF_WEBHOOK_URL, "")},
                ): TextSelector(),
                vol.Optional(
                    CONF_SIGNING_KEY,
                    description={"suggested_value": options.get(CONF_SIGNING_KEY, "")},
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
