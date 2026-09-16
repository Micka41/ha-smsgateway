"""Constantes de l'intégration SMSGateway."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "smsgate"
MANUFACTURER: Final = "SMS Gateway for Android"

# L'envoi MMS (champ mmsMessage) n'existe pas avant cette version.
MIN_APP_VERSION: Final = (1, 74, 1)
MIN_APP_VERSION_STR: Final = "1.74.1"

# --- Configuration -----------------------------------------------------------
CONF_MESSAGE_PATH: Final = "message_path"
CONF_WEBHOOK_URL: Final = "webhook_url"
CONF_DEFAULT_RECIPIENT: Final = "default_recipient"
CONF_MEDIA_DIR: Final = "media_dir"
CONF_KEEP_ATTACHMENTS: Final = "keep_attachments"
CONF_SIGNING_KEY: Final = "signing_key"

# Fenêtre acceptée pour X-Timestamp, contre le rejeu.
SIGNATURE_TOLERANCE_SECONDS: Final = 300
CONF_CHECK_UPDATES: Final = "check_updates"

DEFAULT_PORT: Final = 8080
# Endpoint documenté dans le swagger de l'application. Les versions plus
# anciennes exposaient /message ; api.py bascule automatiquement sur 404.
DEFAULT_MESSAGE_PATH: Final = "/messages"
LEGACY_MESSAGE_PATH: Final = "/message"
DEFAULT_MEDIA_DIR: Final = "media/smsgate"
DEFAULT_KEEP_ATTACHMENTS: Final = 50

SCAN_INTERVAL_SECONDS: Final = 300

# Recherche de nouvelle version de l'application. L'intégration est locale :
# cette vérification est le seul appel sortant, et elle est désactivable.
DEFAULT_CHECK_UPDATES: Final = True
RELEASE_URL: Final = (
    "https://api.github.com/repos/capcom6/android-sms-gateway/releases/latest"
)
RELEASE_SCAN_INTERVAL_HOURS: Final = 12

# --- Événements applicatifs amont --------------------------------------------
EVENT_SMS_RECEIVED: Final = "sms:received"
EVENT_SMS_SENT: Final = "sms:sent"
EVENT_SMS_DELIVERED: Final = "sms:delivered"
EVENT_SMS_FAILED: Final = "sms:failed"
EVENT_SMS_DATA_RECEIVED: Final = "sms:data-received"
EVENT_MMS_RECEIVED: Final = "mms:received"
EVENT_MMS_DOWNLOADED: Final = "mms:downloaded"
EVENT_SYSTEM_PING: Final = "system:ping"

# Identifiant du webhook côté application, par événement.
WEBHOOK_EVENTS: Final = (
    EVENT_SMS_RECEIVED,
    EVENT_SMS_SENT,
    EVENT_SMS_DELIVERED,
    EVENT_SMS_FAILED,
    EVENT_MMS_RECEIVED,
    EVENT_MMS_DOWNLOADED,
    EVENT_SYSTEM_PING,
)

# --- Événements émis sur le bus HA -------------------------------------------
HA_EVENT_SMS_RECEIVED: Final = "smsgate_sms_received"
HA_EVENT_MMS_RECEIVED: Final = "smsgate_mms_received"
HA_EVENT_MMS_NOTIFIED: Final = "smsgate_mms_notified"
HA_EVENT_STATUS: Final = "smsgate_status"

# --- Signaux internes (dispatcher) -------------------------------------------
SIGNAL_SMS_RECEIVED: Final = "smsgate_signal_sms_received_{}"
SIGNAL_MMS_RECEIVED: Final = "smsgate_signal_mms_received_{}"
SIGNAL_STATUS: Final = "smsgate_signal_status_{}"
SIGNAL_PING: Final = "smsgate_signal_ping_{}"

# --- Services ----------------------------------------------------------------
SERVICE_SEND_SMS: Final = "send_sms"
SERVICE_SEND_MMS: Final = "send_mms"

ATTR_RECIPIENTS: Final = "recipients"
ATTR_MESSAGE: Final = "message"
ATTR_SUBJECT: Final = "subject"
ATTR_ATTACHMENTS: Final = "attachments"
ATTR_PRIORITY: Final = "priority"
ATTR_SIM: Final = "sim"
ATTR_TTL: Final = "ttl"
ATTR_CONFIG_ENTRY: Final = "config_entry_id"
