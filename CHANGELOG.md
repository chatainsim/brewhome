# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

---

## [2026-05-21]

### Ajouté
- **Catalogue — recherche en temps réel** : dans Paramètres > Catalogue, un champ de recherche filtre instantanément la liste par nom et sous-catégorie
- **Recettes — avertissement volume insuffisant** : lorsque les volumes d'eau saisis manuellement ne permettent pas d'atteindre le volume cible de la recette, une alerte ambrée s'affiche avec le volume estimé réel
- **GitHub** : connexion du répertoire local au dépôt `https://github.com/chatainsim/brewhome` — premier push de l'ensemble du code
- **CHANGELOG.md** : ce fichier

### Modifié
- **Recettes — calcul pré-ébullition en mode manuel** : en mode saisie manuelle des volumes d'eau, le pré-ébullition affiché est désormais calculé à partir de l'eau réellement utilisée (et non de la cible), avec recalcul du volume final estimé
- **Documentation** : mise à jour de `README.md`, `INSTALL.md` et `API.md` (champs `water_mash_override`, `water_sparge_override`, `ferm_profile` ; endpoints fork et historique des recettes)

### Corrigé
- **Recettes — mode visualisation** : les valeurs de saisie manuelle des volumes d'eau ne s'affichaient pas en mode visualisation d'une recette (JS compilé obsolète)

---
