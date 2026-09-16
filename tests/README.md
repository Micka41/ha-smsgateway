# Tests

```bash
python3 -m venv venv && ./venv/bin/pip install pytest-homeassistant-custom-component
./venv/bin/python -m pytest tests/ -q
```

Le harnais charge l'intégration depuis `custom_components/` et exécute un vrai
Home Assistant en mémoire. C'est ce qui a permis de détecter le masquage du
composant `homeassistant.components.webhook` par un sous-module homonyme :
un simple `import` du module ne le révèle pas, seul le chargement complet
par le loader HA le fait apparaître.
