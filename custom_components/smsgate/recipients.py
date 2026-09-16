"""Destinataires nommés, résolus depuis ``secrets.yaml``.

Un alias ``{MICKA}`` écrit dans les services d'envoi est traduit par la valeur
de la clé ``smsgate_micka`` de ``/config/secrets.yaml``. Les numéros restent
donc hors de ``.storage``, tout en étant utilisables depuis l'éditeur visuel
et les outils de développement, ce que ``!secret`` ne permet pas.

Seules les clés préfixées ``smsgate_`` sont accessibles : sans cette
restriction, un alias mal tapé — ``{LATITUDE}``, ``{TOKEN}`` — enverrait un
secret quelconque par SMS.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import yaml

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Un alias est un nom entouré d'accolades, sans accolade imbriquée.
ALIAS = re.compile(r"^\{([^{}]+)\}$")

# Seules les clés de secrets.yaml portant ce préfixe sont exposées.
PREFIXE = "smsgate_"

SECRETS_FILE = "secrets.yaml"
CACHE = f"{DOMAIN}_secrets_cache"


class RecipientError(ValueError):
    """Alias inconnu, ou fichier de secrets illisible."""


def _charger(chemin: str) -> dict[str, str]:
    """Lire secrets.yaml et n'en garder que les clés préfixées.

    Appel bloquant : à exécuter dans l'executor. Un fichier absent donne un
    répertoire vide, ce qui n'est pas une erreur : tous les numéros peuvent
    être écrits littéralement.
    """
    try:
        with open(chemin, encoding="utf-8") as handle:
            brut = yaml.safe_load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError) as err:
        # On ne journalise jamais le contenu du fichier.
        raise RecipientError(f"{SECRETS_FILE} illisible: {type(err).__name__}") from err

    if not isinstance(brut, dict):
        return {}

    contacts: dict[str, str] = {}
    for cle, valeur in brut.items():
        if not isinstance(cle, str) or not cle.startswith(PREFIXE):
            continue
        nom = cle[len(PREFIXE) :].strip().upper()
        if nom and valeur is not None:
            contacts[nom] = str(valeur).strip()
    return contacts


def _lire_avec_cache(hass: HomeAssistant, chemin: str) -> dict[str, str]:
    """Recharger le fichier seulement s'il a changé.

    La date de modification et la taille servent de témoin : un numéro
    corrigé est donc actif sans redémarrage, sans relire le fichier à
    chaque message.
    """
    try:
        stat = os.stat(chemin)
        temoin = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        temoin = None

    cache = hass.data.get(CACHE)
    if cache is not None and cache[0] == temoin:
        return cache[1]

    contacts = _charger(chemin)
    hass.data[CACHE] = (temoin, contacts)
    return contacts


async def async_resolve(hass: HomeAssistant, destinataires: list[str]) -> list[str]:
    """Remplacer les alias par leur numéro.

    Une entrée qui n'est pas un alias est renvoyée telle quelle : un numéro
    littéral reste utilisable, avec ou sans secrets.yaml.
    """
    if not any(ALIAS.match(entree.strip()) for entree in destinataires):
        return list(destinataires)

    chemin = hass.config.path(SECRETS_FILE)
    contacts = await hass.async_add_executor_job(_lire_avec_cache, hass, chemin)

    resolus: list[str] = []
    for entree in destinataires:
        correspondance = ALIAS.match(entree.strip())
        if correspondance is None:
            resolus.append(entree)
            continue

        nom = correspondance.group(1).strip().upper()
        if nom not in contacts:
            connus = ", ".join(sorted(contacts)) or "aucun"
            raise RecipientError(
                f"destinataire {{{nom}}} inconnu : ajouter "
                f"{PREFIXE}{nom.lower()} dans {SECRETS_FILE}. "
                f"Alias disponibles : {connus}"
            )
        resolus.append(contacts[nom])

    return resolus


def invalidate_cache(hass: HomeAssistant) -> Any:
    """Vider le cache, utilisé au déchargement de la dernière entrée."""
    return hass.data.pop(CACHE, None)
