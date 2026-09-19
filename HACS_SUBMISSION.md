# Soumission au dépôt HACS par défaut

L'intégration est déjà installable dès maintenant en **dépôt personnalisé**
HACS. Cette procédure ne concerne que l'inclusion dans la liste par défaut,
dont la revue prend plusieurs mois.

## Icônes : rien à soumettre ailleurs

Depuis Home Assistant 2026.3, une intégration custom embarque ses images dans
`custom_components/<domaine>/brand/`, et `home-assistant/brands` n'accepte plus
de PR pour les intégrations custom. Les images locales ont priorité sur celles
du dépôt brands.

Les icônes sont donc déjà en place dans `custom_components/smsgate/brand/`,
et le check `brands` de l'action HACS les trouve localement avant d'interroger
le dépôt distant. **Aucune PR préalable n'est nécessaire.**

Deux conséquences à connaître :

- Sur une instance antérieure à 2026.3, l'icône ne s'affichera pas. Le reste
  de l'intégration fonctionne normalement, c'est purement cosmétique.
- Le tableau de bord HACS lit encore ses icônes depuis `data-v2.hacs.xyz` et
  n'affiche pas les images locales — l'icône reste vide dans la boutique HACS
  tout en s'affichant correctement dans les pages Intégrations et Appareils
  de Home Assistant. Bug suivi dans `hacs/integration` #5171.

## 1. Réglages du dépôt GitHub

| Réglage | Où | Valeur |
|---|---|---|
| Visibilité | Settings → General | Public |
| Description | Page d'accueil, roue dentée | ex. « Home Assistant integration for SMS Gateway for Android — send and receive SMS and MMS locally » |
| Topics | Page d'accueil, roue dentée | `home-assistant`, `hacs`, `homeassistant`, `home-automation`, `sms`, `mms`, `android`, `integration` |
| Issues | Settings → General → Features | Activées |

Un dépôt sans description ni topics est rejeté par le check HACS.

## 2. Vérifier les actions

Après le premier push, aller dans **Actions** et confirmer que les deux jobs
sont verts :

- `HACS validation`
- `hassfest validation`

Relancer manuellement au besoin via **Run workflow** (le déclencheur
`workflow_dispatch` est en place).

## 3. Créer une release

Une release GitHub est obligatoire — un simple tag ne suffit pas.

```bash
git tag 2026.09.1
git push origin 2026.09.1
```

Puis **Releases → Draft a new release**, choisir le tag, publier.

Le workflow `release.yml` se déclenche à la publication : il aligne
automatiquement `version` dans `manifest.json` sur le tag, construit
`smsgate.zip` et l'attache à la release. Plus de désynchronisation possible
entre le tag et le manifest.

`hacs.json` déclare `zip_release` et `filename` : HACS installe donc l'archive
plutôt que de cloner le dépôt. Les utilisateurs ne téléchargent que le
composant, sans les tests ni la documentation.

Format de tag calendaire recommandé, comme sur `bwt-aqa-perla-ble`. Un `v`
initial est accepté, le workflow le retire pour le manifest.

**La release doit être créée après que les actions soient passées au vert**,
c'est un point explicite de la checklist.

## 4. Ouvrir la Pull Request

1. Forker `https://github.com/hacs/default`
2. Créer une branche depuis **`master`** (pas `main`)
3. Éditer le fichier `integration` et y insérer, **en respectant l'ordre
   alphabétique** :

```
Micka41/ha-smsgateway
```

4. Ouvrir la PR vers `hacs/default`.

**Titre :**

```
Adds new integration [Micka41/ha-smsgateway]
```

**Corps** — le template s'affiche automatiquement, le remplir intégralement.
Une PR au template mal rempli est fermée sans explication :

```markdown
## Checklist

- [x] I've read the publishing documentation.
- [x] I've added the HACS action to my repository.
- [x] (For integrations only) I've added the hassfest action to my repository.
- [x] The actions are passing without any disabled checks in my repository.
      I've added a link to the action run on my repository below in the links section.
- [x] I've created a new release of the repository after the validation
      actions were run successfully.

## Links

- Link to current release: https://github.com/Micka41/ha-smsgateway/releases/tag/2026.09.1
- Link to HACS action run: https://github.com/Micka41/ha-smsgateway/actions/runs/XXXXXXXXX
- Link to hassfest action run: https://github.com/Micka41/ha-smsgateway/actions/runs/XXXXXXXXX
```

Les liens doivent pointer vers les **runs précis**, pas vers la page Actions.
Les obtenir via **Actions → dernier run vert → copier l'URL**.

## 5. Installation en attendant

HACS → menu → **Dépôts personnalisés** → URL du dépôt, catégorie
« Integration ».

## Points déjà traités dans ce dépôt

- `hacs.json` avec `name` et version minimale de Home Assistant
- `manifest.json` : `version`, `documentation`, `issue_tracker`, `codeowners`,
  `config_flow`, `iot_class`, `integration_type`, clés ordonnées
- Workflows HACS et hassfest, sans check désactivé
- `README.md` en anglais (lu par HACS), `README.fr.md`, `LICENSE`,
  template d'issue
- Icônes 256 et 512 px dans `custom_components/smsgate/brand/`, servies
  localement par Home Assistant 2026.3+
- Traductions FR / EN / DE / IT, `strings.json` identique à `en.json`
