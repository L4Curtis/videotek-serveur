"""Test de bout en bout : scénario complet sur les deux conteneurs lancés.

    python3 tests/e2e.py                          # site sur http://localhost:5000
    python3 tests/e2e.py http://10.11.16.145:5000

À lancer avec les données de préproduction (l'API utilise
donnees/videotheque_test.json) : le scénario se sert des comptes de test
« admin » et « chloe » (bloquée), crée ses propres objets (compte, catégorie,
film, supports) puis les supprime. Le compte créé reste : l'API n'a pas de
route de suppression d'utilisateur.

Chaque formulaire est soumis comme dans un navigateur : la page est d'abord
chargée pour récupérer le jeton CSRF, puis les redirections sont suivies.
"""
import re
import sys
import time

import requests

SITE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/")
ADMIN = ("admin", "admin-2026")    # comptes du fichier de test (préproduction)
BLOQUEE = ("chloe", "chloe-2026")

bilan = {"reussis": 0, "echoues": 0}


def verifier(condition, libelle):
    if condition:
        bilan["reussis"] += 1
        print(f"  \033[32m✓\033[0m {libelle}")
    else:
        bilan["echoues"] += 1
        print(f"  \033[31m✗\033[0m {libelle}")
    return condition


class Navigateur:
    """Session HTTP qui garde le cookie de session, comme un navigateur."""

    def __init__(self):
        self.session = requests.Session()

    def get(self, chemin):
        return self.session.get(SITE + chemin, timeout=30)

    def post(self, chemin, donnees=None, depuis=None):
        """Charge la page `depuis` (jeton CSRF) puis envoie le formulaire."""
        page = self.get(depuis or chemin).text
        jeton = re.search(r'name="csrf" value="([^"]+)"', page)
        donnees = dict(donnees or {})
        if jeton:
            donnees["csrf"] = jeton.group(1)
        return self.session.post(SITE + chemin, data=donnees, timeout=30)


def chercher(motif, texte, flags=0):
    trouve = re.search(motif, texte, flags)
    return trouve.group(1) if trouve else None


def main():
    print(f"Site : {SITE}")
    n = int(time.time())
    nom, mot_de_passe = f"e2e{n}", "e2e-motdepasse"

    print("== Visiteur")
    u = Navigateur()
    r = u.get("/")
    verifier(r.url.startswith(SITE + "/connexion"), "le catalogue renvoie vers la connexion")
    r = u.post("/inscription", {"nom_utilisateur": nom, "prenom": "Test", "nom": "E2E",
                                "email": f"{nom}@exemple.fr", "annee_naissance": "2001",
                                "mot_de_passe": mot_de_passe, "confirmation": mot_de_passe})
    verifier("Votre compte est créé" in r.text, "inscription d'un nouveau compte")
    r = u.post("/inscription", {"nom_utilisateur": nom, "prenom": "Test", "nom": "E2E",
                                "email": f"autre{n}@exemple.fr", "annee_naissance": "2001",
                                "mot_de_passe": mot_de_passe, "confirmation": mot_de_passe})
    verifier("déjà utilisé" in r.text, "inscription refusée : nom d'utilisateur déjà pris")
    r = u.post("/connexion", {"nom_utilisateur": nom, "mot_de_passe": "mauvais"})
    verifier("incorrect" in r.text, "connexion refusée : mauvais mot de passe")
    r = u.post("/connexion", {"nom_utilisateur": BLOQUEE[0], "mot_de_passe": BLOQUEE[1]})
    verifier("bloqué" in r.text, "connexion refusée : compte bloqué")

    print("== Utilisateur")
    r = u.post("/connexion", {"nom_utilisateur": nom, "mot_de_passe": mot_de_passe})
    verifier(r.url == SITE + "/" and "Bienvenue" in r.text, "connexion puis catalogue")
    r = u.get("/?q=dicaprio")
    verifier("Inception" in r.text and "Matrix" not in r.text, "recherche par acteur")
    r = u.get("/?annee=1994&tri=note")
    verifier("Pulp Fiction" in r.text and "Le Roi lion" in r.text and "Inception" not in r.text,
             "filtre par année et tri par note")
    r = u.get("/films/2")
    verifier("Keanu Reeves" in r.text, "fiche d'un film")
    support = chercher(r'action="/emprunter/(\d+)"', r.text)
    r = u.post(f"/emprunter/{support}", {"film_id": "2"}, depuis="/films/2")
    verifier("retour prévu le" in r.text, "emprunt d'un support physique")
    r = u.get("/compte")
    emprunt = chercher(r'action="/emprunts/(\d+)/retour"', r.text)
    verifier(emprunt is not None and "Matrix" in r.text, "emprunt visible dans Mon compte")
    r = u.post(f"/emprunts/{emprunt}/retour", depuis="/compte")
    verifier("Retour de « Matrix » enregistré" in r.text, "retour du film")
    r = u.post("/films/2/avis", {"note": "5", "commentaire": "Test de bout en bout"},
               depuis="/films/2")
    verifier("Votre avis a été enregistré" in r.text and "Test de bout en bout" in r.text,
             "publication d'un avis")
    r = u.post("/envies/3", {"action": "ajouter", "suivant": "/compte"}, depuis="/films/3")
    verifier("ajouté à votre liste d" in r.text and "Interstellar" in r.text,
             "ajout à la liste d'envies")
    r = u.post("/vus/2", {"action": "ajouter"}, depuis="/films/2")
    verifier("marqué comme vu" in r.text, "film marqué comme vu")
    r = u.get("/admin/utilisateurs")
    verifier("réservée aux administrateurs" in r.text, "pages admin refusées à un utilisateur")

    print("== Administrateur")
    a = Navigateur()
    r = a.post("/connexion", {"nom_utilisateur": ADMIN[0], "mot_de_passe": ADMIN[1]})
    verifier("Import TMDB" in r.text, "connexion administrateur (menu d'administration)")
    r = a.post("/admin/categories", {"action": "ajouter", "nom": f"E2E {n}"})
    categorie = chercher(rf'name="categorie_id" value="(\d+)">\s*<input name="nom" value="E2E {n}"',
                         r.text)
    verifier("ajoutée" in r.text and categorie, "ajout d'une catégorie")
    r = a.post("/admin/films/ajouter", {"titre": f"Film E2E {n}", "annee": "2025",
                                        "categories": categorie, "acteurs": "Actrice A, Acteur B",
                                        "description": "Créé par e2e.py", "affiche": ""})
    film = chercher(r"/films/(\d+)$", r.url)
    verifier(film and f"Film E2E {n}" in r.text, "ajout manuel d'un film")
    r = a.post(f"/admin/films/{film}/modifier",
               {"titre": f"Film E2E {n} (modifié)", "annee": "2025", "categories": categorie,
                "acteurs": "Actrice A", "description": "Modifié par e2e.py", "affiche": ""})
    verifier("modifié" in r.text and "Modifié par e2e.py" in r.text, "modification du film")
    r = a.post(f"/admin/films/{film}/supports",
               {"action": "ajouter", "type": "physique", "format": "DVD", "lien": ""})
    nouveau_support = chercher(r'name="support_id" value="(\d+)"', r.text)
    verifier("Support ajouté" in r.text and nouveau_support, "ajout d'un support physique")
    r = a.post(f"/admin/films/{film}/supports",
               {"action": "ajouter", "type": "numérique", "format": "MP4",
                "lien": "https://media.videotek.local/e2e.mp4"})
    verifier("Support ajouté" in r.text and "e2e.mp4" in r.text, "ajout d'un support numérique")

    r = u.post(f"/emprunter/{nouveau_support}", {"film_id": film}, depuis=f"/films/{film}")
    verifier("retour prévu" in r.text, "emprunt du nouveau DVD par l'utilisateur")
    r = a.post(f"/admin/films/{film}/supprimer", depuis=f"/films/{film}")
    verifier("emprunté" in r.text, "suppression du film refusée : support emprunté")
    r = a.get(f"/admin/films/{film}/supports")
    verifier(f"par {nom}" in r.text, "page des supports : emprunteur affiché")
    emprunt = chercher(r'action="/emprunts/(\d+)/retour"', u.get("/compte").text)
    u.post(f"/emprunts/{emprunt}/retour", depuis="/compte")

    print("== Blocage d'un compte connecté")
    r = a.get("/admin/utilisateurs")
    utilisateur = chercher(rf"<strong>{nom}</strong>.*?/admin/utilisateurs/(\d+)/bloquer", r.text, re.S)
    r = a.post(f"/admin/utilisateurs/{utilisateur}/bloquer", {"bloque": "1"},
               depuis="/admin/utilisateurs")
    verifier(f"Compte « {nom} » bloqué" in r.text, "blocage du compte par l'administrateur")
    r = u.get("/")
    verifier(r.url.startswith(SITE + "/connexion") and "bloqué" in r.text,
             "session de l'utilisateur bloqué fermée")
    r = a.post(f"/admin/utilisateurs/{utilisateur}/bloquer", {"bloque": "0"},
               depuis="/admin/utilisateurs")
    verifier("débloqué" in r.text, "déblocage du compte")

    print("== Import TMDB")
    r = a.get("/admin/import?titre=la%20haine")
    if "TMDB indisponible" in r.text:
        verifier("/admin/films/ajouter?titre=la" in r.text,
                 "TMDB indisponible (clé absente ?) : lien vers l'ajout manuel")
    else:
        tmdb_id = chercher(r'name="tmdb_id" value="(\d+)"', r.text)
        verifier(tmdb_id is not None, "recherche sur TMDB : résultats affichés")
        r = a.post("/admin/import", {"tmdb_id": tmdb_id, "titre": "la haine"},
                   depuis="/admin/import?titre=la%20haine")
        importe = chercher(r"/films/(\d+)$", r.url)
        verifier(importe and "importé depuis TMDB" in r.text, "import d'un film depuis TMDB")
        r = a.post(f"/admin/films/{importe}/supprimer", depuis=f"/films/{importe}")
        verifier("supprimé" in r.text, "suppression du film importé")

    print("== Nettoyage")
    r = a.post(f"/admin/films/{film}/supprimer", depuis=f"/films/{film}")
    verifier("supprimé" in r.text, "suppression du film")
    r = a.post("/admin/categories", {"action": "supprimer", "categorie_id": categorie})
    verifier("supprimée" in r.text, "suppression de la catégorie")

    print("== Pages de test du conteneur")
    t = Navigateur()
    verifier("Page HTML simple" in t.get("/test/simple").text, "page HTML simple")
    r = t.post("/test/formulaire", {"prenom": "test", "film": "Matrix", "note": "4"})
    verifier("Merci Test" in r.text, "formulaire et page de traitement")
    verifier("Le Voyage de Chihiro" in t.get("/test/videotheque").text,
             "template Jinja sur un fichier JSON")

    print(f"\nBilan : {bilan['reussis']} réussis, {bilan['echoues']} échoués")
    return 1 if bilan["echoues"] else 0


if __name__ == "__main__":
    sys.exit(main())
