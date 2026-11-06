"""Appels à l'API REST (tiers données) avec la bibliothèque requests.

L'adresse de l'API est lue dans la variable d'environnement API_URL
(http://api:5000/api dans le réseau Docker). Chaque fonction renvoie le JSON
reçu et le code de retour : (contenu, code).

Quand un utilisateur est connecté, son identifiant est transmis à l'API dans
l'en-tête X-Utilisateur-Id : l'API vérifie que le compte existe et n'est pas
bloqué. Une réponse 403 (compte bloqué) ou 401 (compte inconnu) lève une
exception que app.py traite en vidant la session.
"""
import os

import requests
from flask import session

API_URL = os.environ.get("API_URL", "http://api:5000/api").rstrip("/")
DELAI_SECONDES = 20  # un import TMDB peut prendre quelques secondes


class ApiInjoignable(Exception):
    """L'API ne répond pas (conteneur arrêté, réseau...)."""


class CompteBloque(Exception):
    """L'API a répondu 403 : le compte de l'utilisateur connecté est bloqué."""


class SessionInvalide(Exception):
    """L'API a répondu 401 : le compte de la session n'existe plus."""


def appeler(methode, chemin, donnees=None, parametres=None, anonyme=False):
    """Envoie une requête JSON à l'API ; renvoie (contenu JSON, code de retour)."""
    entetes = {}
    connecte = not anonyme and "utilisateur_id" in session
    if connecte:
        entetes["X-Utilisateur-Id"] = str(session["utilisateur_id"])
    try:
        reponse = requests.request(methode, f"{API_URL}{chemin}", json=donnees,
                                   params=parametres, headers=entetes,
                                   timeout=DELAI_SECONDES)
    except requests.RequestException as exc:
        raise ApiInjoignable(str(exc)) from exc
    try:
        contenu = reponse.json()
    except ValueError:
        contenu = {"erreur": f"Réponse inattendue de l'API (code {reponse.status_code})"}
    if connecte and reponse.status_code == 403:
        raise CompteBloque()
    if connecte and reponse.status_code == 401:
        raise SessionInvalide()
    return contenu, reponse.status_code


# --- Comptes -----------------------------------------------------------------
def connexion(nom_utilisateur, mot_de_passe):
    return appeler("POST", "/connexion", {"nom_utilisateur": nom_utilisateur,
                                          "mot_de_passe": mot_de_passe}, anonyme=True)


def inscription(champs):
    return appeler("POST", "/utilisateurs", champs, anonyme=True)


def utilisateurs():
    return appeler("GET", "/utilisateurs")


def utilisateur(utilisateur_id):
    return appeler("GET", f"/utilisateurs/{utilisateur_id}")


def bloquer(utilisateur_id, bloque):
    return appeler("PUT", f"/utilisateurs/{utilisateur_id}/bloque", {"bloque": bloque})


def modifier_liste(utilisateur_id, liste, film_id, ajouter):
    """liste : « envies » ou « vus » ; ajout (POST) ou retrait (DELETE)."""
    return appeler("POST" if ajouter else "DELETE",
                   f"/utilisateurs/{utilisateur_id}/{liste}/{film_id}")


# --- Films -------------------------------------------------------------------
def films(q="", annee="", categorie="", tri=""):
    parametres = {cle: valeur for cle, valeur in
                  {"q": q, "annee": annee, "categorie": categorie, "tri": tri}.items() if valeur}
    return appeler("GET", "/films", parametres=parametres)


def film(film_id):
    return appeler("GET", f"/films/{film_id}")


def ajouter_film(champs):
    return appeler("POST", "/films", champs)


def modifier_film(film_id, champs):
    return appeler("PUT", f"/films/{film_id}", champs)


def supprimer_film(film_id):
    return appeler("DELETE", f"/films/{film_id}")


# --- Catégories --------------------------------------------------------------
def categories():
    return appeler("GET", "/categories")


def ajouter_categorie(nom):
    return appeler("POST", "/categories", {"nom": nom})


def renommer_categorie(categorie_id, nom):
    return appeler("PUT", f"/categories/{categorie_id}", {"nom": nom})


def supprimer_categorie(categorie_id):
    return appeler("DELETE", f"/categories/{categorie_id}")


# --- Supports ----------------------------------------------------------------
def ajouter_support(film_id, champs):
    return appeler("POST", f"/films/{film_id}/supports", champs)


def modifier_support(support_id, champs):
    return appeler("PUT", f"/supports/{support_id}", champs)


def supprimer_support(support_id):
    return appeler("DELETE", f"/supports/{support_id}")


# --- Emprunts et avis --------------------------------------------------------
def emprunts(utilisateur_id=None):
    parametres = {"utilisateur_id": utilisateur_id} if utilisateur_id else None
    return appeler("GET", "/emprunts", parametres=parametres)


def emprunter(utilisateur_id, support_id):
    return appeler("POST", "/emprunts", {"utilisateur_id": utilisateur_id,
                                         "support_id": support_id})


def rendre(emprunt_id, utilisateur_id):
    return appeler("PUT", f"/emprunts/{emprunt_id}/retour", {"utilisateur_id": utilisateur_id})


def donner_avis(film_id, utilisateur_id, note, commentaire):
    return appeler("POST", f"/films/{film_id}/avis", {"utilisateur_id": utilisateur_id,
                                                      "note": note,
                                                      "commentaire": commentaire})


# --- TMDB --------------------------------------------------------------------
def rechercher_tmdb(titre):
    return appeler("GET", "/tmdb", parametres={"titre": titre})


def importer_tmdb(tmdb_id):
    return appeler("POST", "/tmdb/import", {"tmdb_id": tmdb_id})
