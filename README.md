# SMSGateway — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/releases)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/Micka41/ha-smsgateway)
[![GitHub license](https://img.shields.io/github/license/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/issues)
[![GitHub stars](https://img.shields.io/github/stars/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/stargazers)
[![Validate](https://github.com/Micka41/ha-smsgateway/actions/workflows/validate.yml/badge.svg)](https://github.com/Micka41/ha-smsgateway/actions/workflows/validate.yml)

> 🇫🇷 [Version française](README.fr.md)

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/micka41 "Buy Me A Coffee") [<img style="background:#ccc;border-radius:10px" alt="PayPal" src="https://www.paypalobjects.com/paypal-ui/logos/svg/paypal-color.svg" width="200" height="40px" />](https://paypal.me/mpicaud41)

Send and receive **SMS and MMS** through the
**[SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway)**
app in Local Server mode.

> No cloud, no MQTT broker. The phone and Home Assistant talk directly over the
> local network.

![SMSGateway](custom_components/smsgate/brand/icon.png)

## Features

- 📤 **SMS and MMS sending** — attachments, subject, SIM slot, priority, TTL
- 📥 **SMS and MMS reception** — attachments written to `/config/media/smsgate/`
- 🖼️ **Image entity** — the last picture received by MMS
- 🔒 **Signed webhooks** — HMAC-SHA256 verification with replay protection
- 🩺 **Phone diagnostics** — battery, charging, connectivity, failed messages
- 🔑 **Named recipients** — `{PAPA}` resolved from `secrets.yaml`
- 🌍 **Multilingual** — French, English, German, Italian

## Entities

| Entity | Type | Description |
|---|---|---|
| Available | binary_sensor | Gateway responds to `/health` |
| Internet connection | binary_sensor | Phone's connectivity |
| Charging | binary_sensor | Any power source connected |
| Battery | sensor (%) | Phone battery level |
| Failed messages | sensor | Failures over the last hour |
| Last SMS | sensor | Sender; text and SIM as attributes |
| Last MMS | sensor | Sender; subject, body and attachment paths as attributes |
| Last send status | sensor | `sent`, `delivered` or `failed` |
| Last MMS image | image | Most recent received picture |
| SMS | notify | Only created when a default recipient is set |

An entity whose `/health` check reports `fail` becomes unavailable rather than
showing an unreliable value.

## Requirements

On the phone:

- **SMS Gateway for Android 1.74.1 or later** — MMS sending (`mmsMessage`) does
  not exist in earlier versions
- Permissions `SEND_SMS`, `RECEIVE_SMS`, plus `RECEIVE_MMS` and
  `RECEIVE_WAP_PUSH` for incoming MMS
- The app set as the **default SMS app** — stated upstream as required for
  reliable MMS sending
- Mobile data enabled with a working MMS APN, otherwise MMS sending fails
  silently
- `Local Server` enabled, `Offline` button pressed

In Home Assistant:

- Version 2025.1.0 or later
- An **HTTPS external URL**, required by the app's secure build
- To send an MMS from a path outside `/config`, add the folder to
  `allowlist_external_dirs`

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Micka41&repository=ha-smsgateway&category=integration)

Or manually:

1. Open HACS → **Integrations**
2. Click ⋮ → **Custom repositories**
3. Add `https://github.com/Micka41/ha-smsgateway` — Category: **Integration**
4. Install **SMSGateway**
5. Restart Home Assistant

### Manual

```bash
cp -r custom_components/smsgate \
  /config/custom_components/smsgate
```

Restart Home Assistant.

The integration icon ships in `custom_components/smsgate/brand/` and is
displayed from Home Assistant 2026.3 onwards, which introduced local brand
images.

## Configuration

### Setup

**Settings → Devices and services → Add integration → SMSGateway**, then enter
the host, port and Local Server credentials shown in the app.

The app version is checked during setup: anything below 1.74.1 is rejected with
an explicit message rather than failing later on the first MMS.

### Options

| Option | Purpose |
|---|---|
| Default recipient | Creates the `notify` entity targeting this number |
| Attachment folder | Relative to the configuration folder, `media/smsgate` by default |
| Attachments to keep | Retention, oldest files are pruned |
| Webhook URL override | Leave empty to use the Home Assistant external URL |
| Webhook signing key | From the app, Settings > Webhooks > Signing Key |

### Changing the gateway address

If the phone's IP changes, use **⋮ → Reconfigure**. Entities, their history and
the Home Assistant webhook ID are preserved — no need to delete and re-add the
integration. The new address is tested before being saved: an unreachable host
is rejected and the previous configuration stays active.

## Webhooks and the secure build

Two independent checks apply, and both must be satisfied.

**The URL registered in the app** must be `https://` with a valid certificate
and a complete chain. The secure build rejects `http://` and bare IP addresses
at registration time, so the Home Assistant external URL — served through a
reverse proxy — is the one used. If no external URL is configured and no URL is
forced in the options, the integration refuses to start and raises a repair
issue rather than registering a URL that is bound to fail.

**The source IP of the incoming POST** is checked by Home Assistant
(`local_only`). The packet arrives from the reverse proxy, or from the phone
itself when `use_x_forwarded_for` is enabled: a private address either way, so
the check passes.

Worth verifying on the network side:

- internal DNS resolves the external hostname to the reverse proxy;
- the firewall lets the phone reach the reverse proxy on port 443;
- Android trusts the certificate — a public CA works, a manually installed
  internal CA is not trusted by apps since Android 7;
- `use_x_forwarded_for` and `trusted_proxies` are set if the phone's real IP
  should appear in the logs.

### Signature

The app signs every webhook with HMAC-SHA256. Copy the key from **Settings >
Webhooks > Signing Key** into the integration options: unsigned or badly signed
requests are then rejected with 401, and requests older than five minutes are
refused to prevent replay. Leave the field empty to accept unsigned requests.

Incoming webhooks are acknowledged immediately and processed in the background:
the app expects a 2xx within 30 seconds, and a slow attachment download would
otherwise trigger a retry and duplicate files.

## Services / Actions

### `smsgate.send_sms`

| Field | Required | Description |
|---|---|---|
| `recipients` | yes | One or more numbers, or `{NAME}` aliases |
| `message` | yes | Text content |
| `priority` | no | 100 or above bypasses rate limits |
| `sim` | no | SIM slot, 1 to 3 |
| `ttl` | no | Expiry in seconds |
| `config_entry_id` | no | Which gateway, when several are configured |

```yaml
action: smsgate.send_sms
data:
  recipients: ["{PAPA}"]
  message: "Gate opened"
```

### `smsgate.send_mms`

| Field | Required | Description |
|---|---|---|
| `recipients` | yes | One or more numbers, or `{NAME}` aliases |
| `attachments` | yes | Absolute paths, inside an allowed folder |
| `message` | no | Text body |
| `subject` | no | Subject |
| `priority`, `sim`, `ttl`, `config_entry_id` | no | As above |

```yaml
action: smsgate.send_mms
data:
  recipients: ["{PAPA}", "{MAMAN}"]
  subject: "Chicken coop"
  message: "Morning snapshot"
  attachments:
    - /config/media/snapshots/coop.jpg
```

## Named recipients

Numbers are declared in `secrets.yaml`, prefixed with `smsgate_`:

```yaml
smsgate_papa: "+33612345678"
smsgate_maman: "+33698765432"
```

`{PAPA}` can then be used anywhere a recipient is expected — including the
visual editor and developer tools, which `!secret` does not allow — on its own
or mixed with literal numbers:

```yaml
action: smsgate.send_sms
data:
  recipients: ["{PAPA}", "{MAMAN}", "+33600000000"]
  message: "Gate opened"
```

Case is ignored. The file is re-read whenever its modification time changes, so
a corrected number takes effect without a restart.

**Only keys prefixed with `smsgate_` are reachable.** Without that restriction,
a mistyped alias such as `{LATITUDE}` would send another secret from the file
over SMS. An unknown alias aborts the send with an error listing the defined
aliases — never their values.

## Events

| Event | Fired on |
|---|---|
| `smsgate_sms_received` | Incoming SMS |
| `smsgate_mms_notified` | MMS notification (metadata, before download) |
| `smsgate_mms_received` | MMS downloaded, with attachment paths |
| `smsgate_status` | `sent` / `delivered` / `failed` |

```yaml
triggers:
  - trigger: event
    event_type: smsgate_sms_received
conditions:
  - condition: template
    value_template: "{{ 'gate' in trigger.event.data.message | lower }}"
```

`smsgate_status` fires **once per part** on multipart SMS, so a long message
flips the status sensor several times.

## How it works

Sending is a plain HTTP POST to the app's Local Server. Receiving relies on
webhooks: the integration registers one per event on the phone at startup and
removes them on unload, so the app never hammers a dead URL.

`android-sms-gateway` on PyPI does not cover the `mmsMessage` field yet.
Combining the library for SMS with direct calls for MMS would mean two HTTP
stacks and two authentication paths for no benefit, so `api.py` uses only the
shared aiohttp session from Home Assistant. Once the library supports MMS, the
switch happens in that single file.

The documented send endpoint is `/messages`. Older app versions only exposed
`/message`; the integration switches automatically on a 404 and remembers which
one answered.

## Compatibility

Tested on:
- SMS Gateway for Android 1.74.1, secure build, Local Server mode
- Home Assistant 2025.1 and 2026.x

JWT authentication is **not available in Local mode** — the app returns 501 —
so Basic auth is the only option, as documented upstream.

## Contributing

Issues and pull requests are welcome. Please include:
- Home Assistant version
- SMS Gateway for Android version and build (secure or insecure)
- Integration logs, with `debug` enabled for `custom_components.smsgate`

```yaml
logger:
  logs:
    custom_components.smsgate: debug
```

Debug logs contain the **text of your messages** and base64 attachments.
Anonymise before posting, and switch back to `info` afterwards.

## License

MIT License — see [LICENSE](LICENSE)
