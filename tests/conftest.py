"""Fixtures : application Flask de test et fausse API (requests simulé)."""
import copy

import pytest

import api
import app as module_app

CATEGORIES = [{"id": 1, "nom": "Action"}, {"id": 2, "nom": "Science-Fiction"}]
FILM = {
    "id": 1, "titre": "Inception", "categories": [1, 2], "annee": 2010,
    "acteurs": ["Leonardo DiCaprio", "Elliot Page"], "description": "Un voleur de rêves.",
    "affiche": None, "tmdb_id": 27205, "date_ajout": "2026-09-02",
    "note_moyenne": 4.5, "nb_avis": 2,
}
FICHE = {**FILM,
         "supports": [{"id": 1, "film_id": 1, "type": "physique", "format": "Blu-ray",
                       "disponible": True, "lien": None},
                      {"id": 3, "film_id": 1, "type": "numérique", "format": "MKV",
                       "disponible": True, "lien": "https://media.videotek.local/inception.mkv"}],
         "avis": [{"id": 1, "utilisateur_id": 3, "film_id": 1, "note": 4,
                   "commentaire": "Très bon film", "date": "2026-09-07",
                   "nom_utilisateur": "bob"}]}
ALICE = {"id": 2, "nom_utilisateur": "alice", "prenom": "Alice", "nom": "Martin",
         "email": "alice@exemple.fr", "annee_naissance": 2003, "role": "utilisateur",
         "bloque": False, "liste_envies": [1], "films_vus": []}


class FausseReponse:
    def __init__(self, code, contenu):
        self.status_code = code
        self._contenu = contenu

    def json(self):
        if self._contenu is None:
            raise ValueError("pas de JSON")
        return self._contenu


class FausseApi:
    """Remplace requests.request : réponses programmées par (méthode, chemin)."""

    def __init__(self):
        self.appels = []
        self.reponses = {
            ("GET", "/categories"): (200, CATEGORIES),
            ("GET", "/films"): (200, [FILM]),
            ("GET", "/films/1"): (200, FICHE),
            ("GET", "/utilisateurs/2"): (200, ALICE),
            ("GET", "/emprunts"): (200, []),
        }

    def repondre(self, methode, chemin, contenu, code=200):
        self.reponses[(methode, chemin)] = (code, contenu)

    def request(self, methode, url, json=None, params=None, headers=None, timeout=None):
        chemin = url[len(api.API_URL):]
        self.appels.append({"methode": methode, "chemin": chemin, "json": json,
                            "params": params, "entetes": headers or {}})
        code, contenu = self.reponses.get((methode, chemin),
                                          (404, {"erreur": "Ressource inexistante"}))
        return FausseReponse(code, copy.deepcopy(contenu))

    def dernier(self, methode, chemin):
        return next(a for a in reversed(self.appels)
                    if a["methode"] == methode and a["chemin"] == chemin)


@pytest.fixture
def fausse_api(monkeypatch):
    fausse = FausseApi()
    monkeypatch.setattr(api.requests, "request", fausse.request)
    return fausse


@pytest.fixture
def client(fausse_api):
    module_app.app.config.update(TESTING=True, CSRF_DESACTIVE=True)
    yield module_app.app.test_client()
    module_app.app.config.update(CSRF_DESACTIVE=False)


def connecter(client, utilisateur_id=2, nom_utilisateur="alice", role="utilisateur"):
    with client.session_transaction() as session:
        session.update(utilisateur_id=utilisateur_id, nom_utilisateur=nom_utilisateur, role=role)
