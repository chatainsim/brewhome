#!/bin/bash
# Démarrage de BrewHome
cd "$(dirname "$0")"

# Création de l'environnement virtuel si nécessaire
if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv venv
fi

# Mise à jour des dépendances (inclut waitress pour le serveur de production)
echo "Vérification des dépendances..."
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

echo "BrewHome démarré sur http://0.0.0.0:5000 (waitress)"
venv/bin/python app.py
