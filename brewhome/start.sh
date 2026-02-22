#!/bin/bash
# Démarrage de BrewHome
cd "$(dirname "$0")"

# Création de l'environnement virtuel si nécessaire
if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv venv
    venv/bin/pip install -q -r requirements.txt
fi

echo "BrewHome démarré sur http://0.0.0.0:5000"
venv/bin/python app.py
