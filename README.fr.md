# SMSGateway — intégration Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/releases)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/Micka41/ha-smsgateway)
[![GitHub license](https://img.shields.io/github/license/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/issues)
[![GitHub stars](https://img.shields.io/github/stars/Micka41/ha-smsgateway.svg)](https://github.com/Micka41/ha-smsgateway/stargazers)
[![Validate](https://github.com/Micka41/ha-smsgateway/actions/workflows/validate.yml/badge.svg)](https://github.com/Micka41/ha-smsgateway/actions/workflows/validate.yml)

> 🇬🇧 [English version](README.md)

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/micka41 "Buy Me A Coffee") [<img style="background:#ccc;border-radius:10px" alt="PayPal" src="https://www.paypalobjects.com/paypal-ui/logos/svg/paypal-color.svg" width="200" height="40px" />](https://paypal.me/mpicaud41)

Envoi et réception de **SMS et MMS** via l'application
**[SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway)**
en mode Local Server.

> Aucun cloud, aucun broker MQTT. Le téléphone et Home Assistant dialoguent
> directement sur le réseau local.

![SMSGateway](custom_components/smsgate/brand/icon.png)

## Fonctionnalités

- 📤 **Envoi SMS et MMS** — pièces jointes, sujet, SIM, priorité, TTL
- 📥 **Réception SMS et MMS** — pièces jointes écrites dans `/config/media/smsgate/`
- 🖼️ **Entité image** — dernière photo reçue par MMS
- 🔒 **Webhooks signés** — vérification HMAC-SHA256 et protection contre le rejeu
- 🩺 **Diagnostic du téléphone** — batterie, charge, connexion, messages en échec
- 🔑 **Destinataires nommés** — `{PAPA}` résolu depuis `secrets.yaml`
- 🌍 **Multilingue** — français, anglais, allemand, italien

## Entités

| Entité | Type | Description |
|---|---|---|
| Disponible | binary_sensor | La passerelle répond à `/health` |
| Connexion Internet | binary_sensor | Connectivité du téléphone |
| En charge | binary_sensor | Une alimentation est branchée |
| Batterie | sensor (%) | Niveau de batterie |
| Messages en échec | sensor | Échecs de la dernière heure |
| Dernier SMS | sensor | Expéditeur ; texte et SIM en attributs |
| Dernier MMS | sensor | Expéditeur ; sujet, corps et chemins des pièces jointes en attributs |
| Dernier statut d'envoi | sensor | `sent`, `delivered` ou `failed` |
| Dernière image MMS | image | Photo reçue la plus récente |
| SMS | notify | Créée uniquement si un destinataire par défaut est défini |

Une entité dont le contrôle `/health` remonte `fail` devient indisponible
plutôt que d'afficher une valeur non fiable.

## Prérequis

Sur le téléphone :

- **SMS Gateway for Android 1.74.1 minimum** — l'envoi MMS (`mmsMessage`)
  n'existe pas dans les versions antérieures
- Permissions `SEND_SMS`, `RECEIVE_SMS`, et pour les MMS entrants
  `RECEIVE_MMS` + `RECEIVE_WAP_PUSH`
- Application définie comme **application SMS par défaut** — indiquée en amont
  comme nécessaire à un envoi MMS fiable
- Data mobile active avec APN MMS, sinon l'envoi MMS échoue silencieusement
- `Local Server` activé, bouton `Offline` pressé

Dans Home Assistant :

- Version 2025.1.0 minimum
- Une **URL externe en HTTPS**, exigée par le build sécurisé de l'application
- Pour envoyer un MMS depuis un chemin hors `/config`, ajouter le dossier à
  `allowlist_external_dirs`

## Installation

### Via HACS (recommandé)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Micka41&repository=ha-smsgateway&category=integration)

Ou manuellement :

1. Ouvrir HACS → **Intégrations**
2. Cliquer sur ⋮ → **Dépôts personnalisés**
3. Ajouter `https://github.com/Micka41/ha-smsgateway` — Catégorie : **Integration**
4. Installer **SMSGateway**
5. Redémarrer Home Assistant

### Manuelle

```bash
cp -r custom_components/smsgate \
  /config/custom_components/smsgate
```

Redémarrer Home Assistant.

L'icône de l'intégration est embarquée dans `custom_components/smsgate/brand/`
et s'affiche à partir de Home Assistant 2026.3, qui a introduit les images de
marque locales.

## Configuration

### Mise en service

**Paramètres → Appareils et services → Ajouter une intégration → SMSGateway**,
puis renseigner l'hôte, le port et les identifiants du Local Server affichés
dans l'application.

La version de l'application est contrôlée à la configuration : en dessous de
1.74.1, l'ajout est refusé avec un message explicite plutôt que d'échouer plus
tard au premier MMS.

### Options

| Option | Rôle |
|---|---|
| Destinataire par défaut | Crée l'entité `notify` visant ce numéro |
| Dossier des pièces jointes | Relatif au dossier de configuration, `media/smsgate` par défaut |
| Pièces jointes conservées | Rétention, les plus anciennes sont purgées |
| URL de webhook forcée | Laisser vide pour utiliser l'URL externe de Home Assistant |
| Clé de signature des webhooks | Dans l'application, Settings > Webhooks > Signing Key |

### Changer l'adresse de la passerelle

Si l'IP du téléphone change, passer par **⋮ → Reconfigurer**. Les entités, leur
historique et l'identifiant de webhook Home Assistant sont conservés — inutile
de supprimer puis recréer l'intégration. La nouvelle adresse est testée avant
d'être enregistrée : un hôte injoignable est refusé et l'ancienne configuration
reste active.

## Webhooks et build sécurisé

Deux contrôles indépendants s'appliquent, et il faut satisfaire les deux.

**L'URL enregistrée dans l'application** doit être en `https://` avec un
certificat valide et une chaîne complète. Le build « secure » refuse `http://`
et les adresses IP nues à l'enregistrement — c'est donc l'URL externe de Home
Assistant, servie par un reverse proxy, qui est utilisée. Si aucune URL externe
n'est configurée et qu'aucune URL n'est forcée dans les options, l'intégration
ne démarre pas et crée une réparation plutôt que d'enregistrer une URL vouée à
l'échec.

**L'IP source du POST entrant** est vérifiée côté Home Assistant
(`local_only`). Le paquet arrive du reverse proxy, ou du téléphone lui-même si
`use_x_forwarded_for` est actif : dans les deux cas une adresse privée, donc le
contrôle passe.

À vérifier côté infrastructure :

- le DNS interne résout le nom externe vers le reverse proxy ;
- le pare-feu autorise le téléphone à joindre le reverse proxy en 443 ;
- le certificat est reconnu par Android — une AC publique convient, une AC
  interne ajoutée manuellement n'est pas approuvée par les applications depuis
  Android 7 ;
- `use_x_forwarded_for` et `trusted_proxies` sont renseignés si l'IP réelle du
  téléphone doit apparaître dans les journaux.

### Signature

L'application signe chaque webhook en HMAC-SHA256. Reporter la clé de
**Settings > Webhooks > Signing Key** dans les options : les requêtes non
signées ou mal signées sont alors rejetées en 401, et celles datant de plus de
cinq minutes sont refusées pour empêcher le rejeu. Laisser le champ vide pour
accepter les requêtes non signées.

Les webhooks entrants sont acquittés immédiatement puis traités en tâche de
fond : l'application attend un 2xx en moins de 30 secondes, faute de quoi un
téléchargement lent provoquerait un rejeu et des fichiers en double.

## Services / Actions

### `smsgate.send_sms`

| Champ | Requis | Description |
|---|---|---|
| `recipients` | oui | Un ou plusieurs numéros, ou des alias `{NOM}` |
| `message` | oui | Contenu du texte |
| `priority` | non | 100 ou plus contourne les limites de débit |
| `sim` | non | Emplacement SIM, 1 à 3 |
| `ttl` | non | Expiration en secondes |
| `config_entry_id` | non | Quelle passerelle, si plusieurs sont configurées |

```yaml
action: smsgate.send_sms
data:
  recipients: ["{PAPA}"]
  message: "Portail ouvert"
```

### `smsgate.send_mms`

| Champ | Requis | Description |
|---|---|---|
| `recipients` | oui | Un ou plusieurs numéros, ou des alias `{NOM}` |
| `attachments` | oui | Chemins absolus, dans un dossier autorisé |
| `message` | non | Corps du texte |
| `subject` | non | Sujet |
| `priority`, `sim`, `ttl`, `config_entry_id` | non | Comme ci-dessus |

```yaml
action: smsgate.send_mms
data:
  recipients: ["{PAPA}", "{MAMAN}"]
  subject: "Poulailler"
  message: "Snapshot du matin"
  attachments:
    - /config/media/snapshots/poulailler.jpg
```

## Destinataires nommés

Les numéros se déclarent dans `secrets.yaml`, préfixés `smsgate_` :

```yaml
smsgate_papa: "+33612345678"
smsgate_maman: "+33698765432"
```

`{PAPA}` s'utilise ensuite partout où un destinataire est attendu — y compris
dans l'éditeur visuel et les outils de développement, ce que `!secret` ne
permet pas — seul ou mélangé à des numéros littéraux :

```yaml
action: smsgate.send_sms
data:
  recipients: ["{PAPA}", "{MAMAN}", "+33600000000"]
  message: "Portail ouvert"
```

La casse est ignorée. Le fichier est relu dès que sa date de modification
change : un numéro corrigé est actif sans redémarrage.

**Seules les clés préfixées `smsgate_` sont accessibles.** Sans cette
restriction, un alias mal tapé comme `{LATITUDE}` enverrait un autre secret du
fichier par SMS. Un alias inconnu interrompt l'envoi avec une erreur listant
les alias définis — jamais leur valeur.

## Événements

| Événement | Déclenché par |
|---|---|
| `smsgate_sms_received` | SMS entrant |
| `smsgate_mms_notified` | Notification MMS (métadonnées, avant téléchargement) |
| `smsgate_mms_received` | MMS téléchargé, avec chemins des pièces jointes |
| `smsgate_status` | `sent` / `delivered` / `failed` |

```yaml
triggers:
  - trigger: event
    event_type: smsgate_sms_received
conditions:
  - condition: template
    value_template: "{{ 'portail' in trigger.event.data.message | lower }}"
```

`smsgate_status` se déclenche **une fois par partie** sur un SMS multipartie :
un long message fait donc changer le capteur de statut plusieurs fois.

## Fonctionnement

L'envoi est un simple POST HTTP vers le Local Server de l'application. La
réception repose sur les webhooks : l'intégration en enregistre un par
événement sur le téléphone au démarrage et les retire au déchargement, pour que
l'application ne martèle jamais une URL morte.

`android-sms-gateway` sur PyPI ne couvre pas encore le champ `mmsMessage`.
Faire cohabiter la bibliothèque pour les SMS et des appels directs pour les MMS
imposerait deux piles HTTP et deux chemins d'authentification pour un gain nul :
`api.py` utilise donc uniquement la session aiohttp partagée de Home Assistant.
Le jour où la bibliothèque gère les MMS, la bascule se fait dans ce seul
fichier.

L'endpoint d'envoi documenté est `/messages`. Les anciennes versions
n'exposaient que `/message` ; l'intégration bascule automatiquement sur 404 et
retient celui qui répond.

## Compatibilité

Testé avec :
- SMS Gateway for Android 1.74.1, build sécurisé, mode Local Server
- Home Assistant 2025.1 et 2026.x

L'authentification JWT est **indisponible en mode Local** — l'application
retourne 501 — donc Basic auth est la seule option, comme documenté en amont.

## Contribuer

Les issues et pull requests sont bienvenues. Merci d'y joindre :
- la version de Home Assistant ;
- la version et le build de SMS Gateway for Android (secure ou insecure) ;
- les journaux de l'intégration, avec `debug` activé pour
  `custom_components.smsgate`.

```yaml
logger:
  logs:
    custom_components.smsgate: debug
```

Les journaux debug contiennent le **texte de vos messages** et les pièces
jointes en base64. Anonymiser avant publication, et repasser en `info` ensuite.

## Licence

Licence MIT — voir [LICENSE](LICENSE)
