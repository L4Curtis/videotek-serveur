# AGENTS.md — videotek-serveur

Consignes pour toute personne ou tout agent qui fait évoluer ce repo. Lire
aussi le [README](README.md) (plan du site, diagrammes) et le README de
[videotek-api](https://github.com/L4Curtis/videotek-api) (routes et format JSON).

## Rôle du repo

Tiers **présentation** de l'application web 3 tiers du TP RT0705
« Gestion d'une vidéothèque », et point d'entrée du déploiement :

```text
navigateur ──HTTP:5000──▶ videotek-serveur (ce repo) ──HTTP/JSON──▶ videotek-api ──▶ videotheque.json
```

- Le serveur **ne lit ni n'écrit jamais** le fichier JSON : toute donnée passe
  par l'API (`api.py`).
- Il gère la session (cookie signé : `utilisateur_id`, `nom_utilisateur`,
  `role`) et **vérifie le rôle** avant d'appeler les routes *(admin)* de l'API,
  qui, elles, ne le vérifient pas.
- Il contient le `docker-compose.yml` **global** (conteneurs `api` + `serveur`).
  Les deux repos doivent être clonés côte à côte (`../videotek-api`).

## Arborescence

| Fichier | Rôle |
|---|---|
| `app.py` | Routes des pages et des scripts, `login_requis`, `admin_requis`, CSRF, gestion des erreurs de l'API |
| `api.py` | Une fonction par route de l'API ; renvoie `(contenu_json, code)` ; ajoute `X-Utilisateur-Id` ; lève `CompteBloque` (403), `SessionInvalide` (401), `ApiInjoignable` |
| `test_conteneur.py` | Blueprint `/test/...` : pages de test du conteneur demandées par le sujet (sans API) |
| `templates/base.html` | Gabarit : menu selon le rôle, messages flash |
| `templates/_macros.html` | `affiche(film)`, `etoiles(note)`, `note_texte(note)` |
| `templates/*.html` | Un template par page (noms de la conception) |
| `static/style.css` | Toute la mise en forme (pas de framework CSS, pas de JS) |
| `exemples/videotheque.json` | Données de la page de test Jinja |
| `tests/test_serveur.py` | Tests pytest avec une API simulée (`conftest.FausseApi`) |
| `tests/e2e.py` | Scénario complet sur les conteneurs lancés |
| `Dockerfile` | Image commune `videotek-flask:1.0` — **identique** à celle de videotek-api |
| `docker-compose.yml` | Création coordonnée des deux conteneurs, réseau `videotheque_net`, volume `videotek_donnees` |

## Commandes

```bash
cp .env.example .env                                  # CLE_SECRETE
cp ../videotek-api/.env.example ../videotek-api/.env  # VIDEOTHEQUE_FICHIER, TMDB_CLE
docker compose up -d --build                          # site :5000, API :5001
docker compose ps
docker compose logs -f serveur
docker compose exec serveur python -m pytest -v       # tests du serveur
docker compose exec api python -m pytest -v           # tests de l'API
python3 tests/e2e.py http://localhost:5000            # bout en bout (préproduction)
docker compose down                                   # arrêt (le volume de données reste)
```

## Conventions

- **Français partout** : routes, fonctions, variables, templates, messages
  flash, commentaires, commits.
- Une **page** = une route GET (ou GET/POST pour un formulaire) + un template
  qui hérite de `base.html`. Un **script** = une route POST qui appelle l'API,
  fait un `flash(message, "succes" | "erreur")` puis `redirect(...)` : jamais de
  page rendue après un POST réussi (motif POST/redirect/GET).
- Les appels HTTP à l'API passent **uniquement** par les fonctions de `api.py`
  (une fonction par route de l'API). Ne pas appeler `requests` ailleurs.
- Messages d'erreur : afficher `message(contenu)` (champ `erreur` renvoyé par
  l'API) plutôt qu'un texte inventé.
- Les valeurs de formulaire sont converties avant l'envoi (`entier(...)`,
  listes) : l'API attend des entiers JSON, pas des chaînes.
- Dates affichées avec le filtre `date_fr` (`20/11/2026`).
- Chaque `<form method="post">` contient `{{ champ_csrf() }}`.
- Pages protégées : `@login_requis` (utilisateur) ou `@admin_requis`
  (administrateur), placé **sous** `@app.get/post/route`.
- Les redirections construites depuis une donnée du client passent par
  `page_locale(...)` (pas de redirection vers un autre site).
- Le menu d'administration ne s'affiche que si `est_admin` ; cela ne remplace
  jamais `@admin_requis` côté route.

## Contrat avec l'API

- Le format des données et les codes de retour sont définis par videotek-api.
  Toute modification d'une route doit être faite dans les deux repos en même
  temps (`videotek-api/app.py` + `api.py` ici + tests + README).
- 403 signifie toujours « compte bloqué » : `api.appeler` lève `CompteBloque`,
  la session est vidée. Ne pas intercepter cette exception dans une route.
- L'identifiant transmis à l'API est toujours celui de la session, jamais une
  valeur venue du formulaire.

## Docker

- Le code est monté en volume (`.:/app`) et Flask tourne avec `--reload` : pas
  besoin de reconstruire l'image après une modification du code.
- Une nouvelle dépendance Python doit être ajoutée au `Dockerfile` **des deux
  repos** (image commune), puis `docker compose up -d --build`.
- L'image commune n'est construite qu'une fois : seul le service `serveur` a un
  `build`, le service `api` utilise `image: videotek-flask:1.0` avec
  `pull_policy: never`. Ne pas remettre de `build` sur les deux services : deux
  constructions simultanées de la même étiquette échouent (« already exists »).
- Ports : 5000 (site) et 5001 (API, tests uniquement). Le serveur joint l'API
  par `http://api:5000/api` sur le réseau `videotheque_net`.
- Ne jamais activer le mode debug de Flask (débogueur exposé sur le réseau).

## Tests

- Toute nouvelle page ou script s'accompagne d'un test dans
  `tests/test_serveur.py` (programmer les réponses avec
  `fausse_api.repondre(...)`, vérifier l'appel avec `fausse_api.dernier(...)`).
- Après un changement visible, relancer `tests/e2e.py` sur les conteneurs en
  préproduction et vérifier la page dans un navigateur.

## Ce qu'il ne faut pas faire

- Lire ou écrire `videotheque.json` depuis ce repo.
- Committer `.env` ou une clé secrète.
- Mettre de la logique métier (disponibilité, unicité…) dans le serveur : elle
  est dans l'API. Le serveur contrôle seulement l'accès et la saisie.

## Git

- Branche `main`, commits courts et thématiques, message en français à
  l'impératif (« Ajoute la page des supports »).
- Pas de ligne `Co-Authored-By` ni de mention d'outil ou d'assistant dans les
  commits : l'auteur est le titulaire du repo.

## Vérifications avant de terminer

- [ ] `python -m pytest` vert
- [ ] `docker compose up -d --build` puis `python3 tests/e2e.py` vert en préproduction
- [ ] Pages vérifiées dans un navigateur (visiteur, utilisateur, administrateur)
- [ ] README à jour (plan du site, tableau des pages) si une route change
- [ ] `Dockerfile` toujours identique à celui de videotek-api
- [ ] `git status` propre : pas de `.env`
