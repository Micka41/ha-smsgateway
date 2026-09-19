# Tests

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements-test.txt
./venv/bin/python -m pytest tests/ --timeout=60
```

Le harnais `pytest-homeassistant-custom-component` démarre un vrai Home
Assistant en mémoire. Il charge les intégrations depuis son propre dossier de
configuration, d'où la copie effectuée par le workflow `test.yml` :

```bash
TARGET=$(python -c "from pytest_homeassistant_custom_component.common import get_test_config_dir; print(get_test_config_dir())")
mkdir -p "$TARGET/custom_components"
cp -r custom_components/smsgate "$TARGET/custom_components/"
```

C'est ce harnais qui a révélé le masquage du composant
`homeassistant.components.webhook` par un sous-module homonyme : un simple
`import` ne le montre pas, seul le chargement complet par le loader le fait
apparaître.

La fixture `api_sans_reseau` de `conftest.py` neutralise les appels réseau pour
toute la durée de chaque test. Sans elle, le déchargement d'une entrée en
teardown tente de joindre le téléphone et `pytest-socket` fait échouer la
suite. Les tests qui vérifient ces appels posent leur propre patch, qui prime.
