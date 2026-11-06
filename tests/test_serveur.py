"""Tests du serveur web : pages, scripts, contrôle d'accès, session, CSRF.

L'API est simulée (conftest.FausseApi) : ces tests ne demandent pas que le
conteneur « api » tourne. Le scénario complet sur les vrais conteneurs est
dans tests/e2e.py.
"""
import requests

import app as module_app
from conftest import ALICE, connecter


def texte(reponse):
    return reponse.get_data(as_text=True)


# ------------------------------------------------------------ contrôle d'accès
def test_visiteur_renvoye_vers_connexion(client):
    reponse = client.get("/")
    assert reponse.status_code == 302
    assert reponse.headers["Location"].startswith("/connexion")
    assert client.get("/compte").headers["Location"] == "/connexion?suivant=/compte"


def test_pages_visiteur(client):
    assert "Se connecter" in texte(client.get("/connexion"))
    assert "Créer mon compte" in texte(client.get("/inscription"))


def test_admin_reserve_a_l_administrateur(client):
    connecter(client)
    reponse = client.get("/admin/utilisateurs", follow_redirects=True)
    assert "réservée aux administrateurs" in texte(reponse)
    assert "Ajouter un film" not in texte(client.get("/"))  # menu sans liens admin


def test_admin_accede_aux_pages_admin(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("GET", "/utilisateurs", [ALICE])
    for page in ("/admin/utilisateurs", "/admin/categories", "/admin/films/ajouter",
                 "/admin/films/1/supports", "/admin/films/1/modifier", "/admin/import"):
        assert client.get(page).status_code == 200, page
    assert "Import TMDB" in texte(client.get("/"))


# ------------------------------------------------------------------ connexion
def test_connexion_cree_la_session(client, fausse_api):
    fausse_api.repondre("POST", "/connexion",
                        {"id": 2, "nom_utilisateur": "alice", "role": "utilisateur"})
    reponse = client.post("/connexion?suivant=/compte",
                          data={"nom_utilisateur": "alice", "mot_de_passe": "x"})
    assert reponse.headers["Location"] == "/compte"
    with client.session_transaction() as session:
        assert session["utilisateur_id"] == 2 and session["role"] == "utilisateur"
    appel = fausse_api.dernier("POST", "/connexion")
    assert appel["json"] == {"nom_utilisateur": "alice", "mot_de_passe": "x"}
    assert "X-Utilisateur-Id" not in appel["entetes"]


def test_connexion_refusee(client, fausse_api):
    fausse_api.repondre("POST", "/connexion", {"erreur": "Compte bloqué par un administrateur"}, 403)
    reponse = client.post("/connexion", data={"nom_utilisateur": "chloe", "mot_de_passe": "x"})
    assert reponse.status_code == 200 and "Compte bloqué" in texte(reponse)


def test_redirection_externe_refusee(client, fausse_api):
    fausse_api.repondre("POST", "/connexion",
                        {"id": 2, "nom_utilisateur": "alice", "role": "utilisateur"})
    reponse = client.post("/connexion?suivant=//pirate.example",
                          data={"nom_utilisateur": "alice", "mot_de_passe": "x"})
    assert reponse.headers["Location"] == "/"


def test_inscription(client, fausse_api):
    fausse_api.repondre("POST", "/utilisateurs", {"id": 5}, 201)
    formulaire = {"nom_utilisateur": "david", "prenom": "David", "nom": "Petit",
                  "email": "david@exemple.fr", "annee_naissance": "2000",
                  "mot_de_passe": "david-2026", "confirmation": "david-2026"}
    assert client.post("/inscription", data=formulaire).headers["Location"] == "/connexion"
    assert fausse_api.dernier("POST", "/utilisateurs")["json"]["annee_naissance"] == 2000


def test_inscription_mots_de_passe_differents(client, fausse_api):
    reponse = client.post("/inscription", data={"nom_utilisateur": "david",
                                                "mot_de_passe": "a" * 8, "confirmation": "b" * 8})
    assert "ne sont pas identiques" in texte(reponse)
    assert not any(a["chemin"] == "/utilisateurs" for a in fausse_api.appels)


def test_deconnexion(client):
    connecter(client)
    assert client.get("/deconnexion").headers["Location"] == "/connexion"
    with client.session_transaction() as session:
        assert "utilisateur_id" not in session


def test_compte_bloque_ferme_la_session(client, fausse_api):
    connecter(client)
    fausse_api.repondre("GET", "/films", {"erreur": "Compte bloqué"}, 403)
    reponse = client.get("/")
    assert reponse.headers["Location"] == "/connexion"
    with client.session_transaction() as session:
        assert "utilisateur_id" not in session


def test_identifiant_transmis_a_l_api(client, fausse_api):
    connecter(client)
    client.get("/")
    assert fausse_api.dernier("GET", "/films")["entetes"]["X-Utilisateur-Id"] == "2"


def test_api_injoignable(client, monkeypatch):
    def panne(*args, **kwargs):
        raise requests.ConnectionError("conteneur arrêté")

    monkeypatch.setattr(requests, "request", panne)
    connecter(client)
    reponse = client.get("/")
    assert reponse.status_code == 503 and "ne répond pas" in texte(reponse)


def test_csrf(client, fausse_api):
    module_app.app.config.update(CSRF_DESACTIVE=False)
    connecter(client)
    with client.session_transaction() as session:
        session["csrf"] = "jeton-valide"
    refuse = client.post("/films/1/avis", data={"note": "4"}, follow_redirects=True)
    assert "Formulaire expiré" in texte(refuse)
    fausse_api.repondre("POST", "/films/1/avis", {"id": 9}, 201)
    accepte = client.post("/films/1/avis", data={"note": "4", "csrf": "jeton-valide"})
    assert accepte.headers["Location"] == "/films/1#avis"


# ------------------------------------------------------- pages de l'utilisateur
def test_catalogue_transmet_recherche_filtres_et_tri(client, fausse_api):
    connecter(client)
    reponse = client.get("/?q=inception&annee=2010&categorie=2&tri=note")
    page = texte(reponse)
    assert "Inception" in page and "Action, Science-Fiction" in page and "4,5" in page
    assert fausse_api.dernier("GET", "/films")["params"] == {
        "q": "inception", "annee": "2010", "categorie": "2", "tri": "note"}


def test_fiche_film(client):
    connecter(client)
    page = texte(client.get("/films/1"))
    assert "Leonardo DiCaprio" in page and "Très bon film" in page
    assert "Emprunter" in page and "Regarder" in page
    assert "Dans ma liste d" in page  # film 1 dans la liste d'envies d'alice
    assert "Supprimer" not in page    # boutons réservés à l'administrateur


def test_fiche_film_inexistant(client):
    connecter(client)
    assert client.get("/films/42").status_code == 404


def test_emprunter(client, fausse_api):
    connecter(client)
    fausse_api.repondre("POST", "/emprunts", {"id": 7, "film_id": 1, "titre": "Inception",
                                              "date_retour_prevue": "2026-11-20"}, 201)
    reponse = client.post("/emprunter/1", data={"film_id": "1"}, follow_redirects=True)
    assert "retour prévu le 20/11/2026" in texte(reponse)
    assert fausse_api.dernier("POST", "/emprunts")["json"] == {"utilisateur_id": 2,
                                                               "support_id": 1}


def test_emprunt_refuse(client, fausse_api):
    connecter(client)
    fausse_api.repondre("POST", "/emprunts", {"erreur": "Ce support n'est pas disponible"}, 409)
    reponse = client.post("/emprunter/1", data={"film_id": "1"}, follow_redirects=True)
    assert "pas disponible" in texte(reponse)


def test_liste_envies_ajout_et_retrait(client, fausse_api):
    connecter(client)
    fausse_api.repondre("DELETE", "/utilisateurs/2/envies/1", {"liste_envies": []})
    reponse = client.post("/envies/1", data={"action": "retirer", "suivant": "/compte"})
    assert reponse.headers["Location"] == "/compte"
    fausse_api.repondre("POST", "/utilisateurs/2/vus/1", {"films_vus": [1]})
    assert client.post("/vus/1", data={"action": "ajouter"}).headers["Location"] == "/films/1"


def test_mon_compte(client, fausse_api):
    connecter(client)
    fausse_api.repondre("GET", "/emprunts", [
        {"id": 4, "utilisateur_id": 2, "support_id": 1, "date_emprunt": "2026-10-01",
         "date_retour_prevue": "2026-10-15", "date_retour_effective": None,
         "film_id": 1, "titre": "Inception", "format": "Blu-ray"}])
    page = texte(client.get("/compte"))
    assert "Alice Martin" in page and "En retard" in page and "Rendre" in page
    assert fausse_api.dernier("GET", "/emprunts")["params"] == {"utilisateur_id": 2}


def test_rendre(client, fausse_api):
    connecter(client)
    fausse_api.repondre("PUT", "/emprunts/4/retour", {"id": 4, "titre": "Inception"})
    reponse = client.post("/emprunts/4/retour", follow_redirects=True)
    assert "Retour de « Inception » enregistré" in texte(reponse)


# ---------------------------------------------------------------- administration
def test_ajouter_film(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("POST", "/films", {"id": 13, "titre": "La Haine"}, 201)
    reponse = client.post("/admin/films/ajouter", data={
        "titre": "La Haine", "annee": "1995", "categories": ["1", "2"],
        "acteurs": "Vincent Cassel, Hubert Koundé,", "description": "", "affiche": ""})
    assert reponse.headers["Location"] == "/films/13"
    assert fausse_api.dernier("POST", "/films")["json"] == {
        "titre": "La Haine", "annee": 1995, "categories": [1, 2],
        "acteurs": ["Vincent Cassel", "Hubert Koundé"], "description": "", "affiche": None}


def test_supprimer_film_refuse(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("DELETE", "/films/1", {"erreur": "Un support de ce film est emprunté"}, 409)
    reponse = client.post("/admin/films/1/supprimer", follow_redirects=True)
    assert "emprunté" in texte(reponse)


def test_supports_modifier(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("PUT", "/supports/1", {"id": 1})
    client.post("/admin/films/1/supports", data={
        "action": "modifier", "support_id": "1", "type": "physique", "format": "DVD",
        "lien": "", "etait_physique": "1", "emprunte": "0"})
    assert fausse_api.dernier("PUT", "/supports/1")["json"] == {
        "type": "physique", "format": "DVD", "lien": None, "disponible": False}


def test_import_tmdb_indisponible(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("GET", "/tmdb", {"erreur": "TMDB indisponible : clé TMDB non configurée"}, 502)
    page = texte(client.get("/admin/import?titre=dune"))
    assert "TMDB indisponible" in page and "/admin/films/ajouter?titre=dune" in page


def test_import_tmdb(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("POST", "/tmdb/import", {"id": 14, "titre": "Dune"}, 201)
    reponse = client.post("/admin/import", data={"tmdb_id": "438631", "titre": "dune"})
    assert reponse.headers["Location"] == "/films/14"
    assert fausse_api.dernier("POST", "/tmdb/import")["json"] == {"tmdb_id": 438631}


def test_admin_ne_peut_pas_se_bloquer(client, fausse_api):
    connecter(client, 1, "admin", "administrateur")
    fausse_api.repondre("GET", "/utilisateurs", [ALICE])
    reponse = client.post("/admin/utilisateurs/1/bloquer", data={"bloque": "1"},
                          follow_redirects=True)
    assert "propre compte" in texte(reponse)
    assert not any(a["methode"] == "PUT" for a in fausse_api.appels)


# ----------------------------------------------------------- pages de test
def test_pages_de_test_du_conteneur(client):
    assert "Page HTML simple" in texte(client.get("/test/simple"))
    resultat = texte(client.post("/test/formulaire", data={
        "prenom": "alice", "film": "Inception", "note": "5", "genres": ["Action", "Drame"]}))
    assert "Merci Alice" in resultat and "5/5" in resultat and "Action, Drame" in resultat
    erreurs = texte(client.post("/test/formulaire", data={"prenom": "", "note": "9"}))
    assert "Le prénom est obligatoire" in erreurs and "entre 1 et 5" in erreurs
    videotheque = texte(client.get("/test/videotheque"))
    assert "Inception" in videotheque and "8 films sur 8" in videotheque
    assert "Le Voyage de Chihiro" in texte(client.get("/test/videotheque?genre=3"))
