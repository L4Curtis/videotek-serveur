"""Serveur web de la vidéothèque (tiers présentation).

Chaque page correspond à une route Flask et à un template Jinja. Les
« scripts » (routes POST sans page) traitent un formulaire ou un bouton,
appellent l'API, puis redirigent vers une page avec un message flash.

La session Flask (cookie signé) contient l'identifiant, le nom d'utilisateur
et le rôle de l'utilisateur connecté. Connexion et inscription sont ouvertes
au visiteur, les pages /admin sont réservées à l'administrateur, toutes les
autres demandent d'être connecté. Si l'API répond 403 (compte bloqué), la
session est vidée et l'utilisateur est renvoyé vers la connexion.
"""
import os
import secrets
from datetime import datetime
from functools import wraps
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from markupsafe import Markup

import api
from test_conteneur import bp as pages_de_test

ROLE_ADMIN = "administrateur"
FUSEAU = ZoneInfo("Europe/Paris")
CLE_A_REMPLACER = "a-remplacer"

app = Flask(__name__)
_cle = os.environ.get("CLE_SECRETE", "")
if not _cle or _cle == CLE_A_REMPLACER:
    app.logger.warning("CLE_SECRETE non définie : clé aléatoire, les sessions seront "
                       "perdues à chaque redémarrage du serveur")
    _cle = secrets.token_hex(32)
app.secret_key = _cle  # signe le cookie de session
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.register_blueprint(pages_de_test)


# =============================================================================
# Outils
# =============================================================================
def aujourdhui():
    return datetime.now(FUSEAU).date().isoformat()


def entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def message(contenu, defaut="Une erreur est survenue."):
    """Message d'erreur renvoyé par l'API ({"erreur": "..."})."""
    if isinstance(contenu, dict) and contenu.get("erreur"):
        return contenu["erreur"]
    return defaut


def page_locale(cible, defaut):
    """N'accepte qu'un chemin du site (« /films/3 ») : pas de redirection externe."""
    if cible and cible.startswith("/") and not cible.startswith("//") and "\\" not in cible:
        return cible
    return defaut


def page_erreur(titre, texte, code):
    return render_template("erreur.html", titre=titre, message=texte), code


def avec_genres(films, categories):
    """Ajoute à chaque film la liste des noms de ses genres."""
    noms = {c["id"]: c["nom"] for c in categories}
    for film in films:
        film["genres"] = [noms[c] for c in film.get("categories", []) if c in noms]
    return films


@app.template_filter("date_fr")
def date_fr(valeur):
    """« 2026-11-20 » → « 20/11/2026 »."""
    if not valeur:
        return ""
    annee, mois, jour = valeur.split("-")
    return f"{jour}/{mois}/{annee}"


@app.context_processor
def variables_des_templates():
    return {"est_admin": session.get("role") == ROLE_ADMIN, "aujourdhui": aujourdhui()}


# =============================================================================
# Protection CSRF : chaque formulaire POST contient un jeton lié à la session
# =============================================================================
def jeton_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@app.template_global()
def champ_csrf():
    return Markup(f'<input type="hidden" name="csrf" value="{jeton_csrf()}">')


@app.before_request
def verifier_jeton_csrf():
    if request.method != "POST" or app.config.get("CSRF_DESACTIVE"):
        return None
    recu = request.form.get("csrf", "").encode()
    attendu = session.get("csrf", "").encode()
    if recu and secrets.compare_digest(recu, attendu):
        return None
    flash("Formulaire expiré : merci de recommencer.", "erreur")
    origine = urlsplit(request.referrer or "")
    retour = origine.path if origine.netloc == request.host else None
    return redirect(page_locale(retour, url_for("catalogue")))


# =============================================================================
# Contrôle d'accès
# =============================================================================
def login_requis(vue):
    """La page demande d'être connecté ; sinon renvoi vers la connexion."""
    @wraps(vue)
    def verification(*args, **kwargs):
        if "utilisateur_id" not in session:
            if request.path != "/":
                flash("Connectez-vous pour accéder à cette page.", "erreur")
            suivant = request.full_path.rstrip("?") if request.method == "GET" else None
            return redirect(url_for("connexion", suivant=suivant))
        return vue(*args, **kwargs)
    return verification


def admin_requis(vue):
    """La page est réservée à l'administrateur (rôle lu dans la session)."""
    @wraps(vue)
    def verification(*args, **kwargs):
        if session.get("role") != ROLE_ADMIN:
            flash("Cette page est réservée aux administrateurs.", "erreur")
            return redirect(url_for("catalogue"))
        return vue(*args, **kwargs)
    return login_requis(verification)


@app.errorhandler(api.CompteBloque)
def compte_bloque(_exc):
    session.clear()
    flash("Votre compte a été bloqué par un administrateur.", "erreur")
    return redirect(url_for("connexion"))


@app.errorhandler(api.SessionInvalide)
def session_invalide(_exc):
    session.clear()
    flash("Votre session n'est plus valide : reconnectez-vous.", "erreur")
    return redirect(url_for("connexion"))


@app.errorhandler(api.ApiInjoignable)
def api_injoignable(_exc):
    return page_erreur("Service indisponible",
                       "L'API de la vidéothèque ne répond pas. Réessayez dans quelques instants.",
                       503)


@app.errorhandler(400)
def requete_invalide(_exc):
    return page_erreur("Requête invalide", "Le formulaire envoyé est incomplet.", 400)


@app.errorhandler(404)
def page_inexistante(_exc):
    return page_erreur("Page introuvable", "Cette page n'existe pas.", 404)


# =============================================================================
# Visiteur : connexion, inscription, déconnexion
# =============================================================================
@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if request.method == "GET" and "utilisateur_id" in session:
        return redirect(url_for("catalogue"))
    nom_utilisateur = ""
    if request.method == "POST":
        nom_utilisateur = request.form.get("nom_utilisateur", "").strip()
        contenu, code = api.connexion(nom_utilisateur, request.form.get("mot_de_passe", ""))
        if code == 200:
            session.clear()
            session.update(utilisateur_id=contenu["id"],
                           nom_utilisateur=contenu["nom_utilisateur"],
                           role=contenu["role"])
            flash(f"Bienvenue, {contenu['nom_utilisateur']} !", "succes")
            return redirect(page_locale(request.args.get("suivant"), url_for("catalogue")))
        flash(message(contenu), "erreur")
    return render_template("connexion.html", nom_utilisateur=nom_utilisateur)


@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    if request.method == "POST":
        formulaire = request.form
        if formulaire.get("mot_de_passe", "") != formulaire.get("confirmation", ""):
            flash("Les deux mots de passe saisis ne sont pas identiques.", "erreur")
        else:
            contenu, code = api.inscription({
                "nom_utilisateur": formulaire.get("nom_utilisateur", "").strip(),
                "prenom": formulaire.get("prenom", "").strip(),
                "nom": formulaire.get("nom", "").strip(),
                "email": formulaire.get("email", "").strip(),
                "annee_naissance": entier(formulaire.get("annee_naissance")),
                "mot_de_passe": formulaire.get("mot_de_passe", ""),
            })
            if code == 201:
                flash("Votre compte est créé : vous pouvez vous connecter.", "succes")
                return redirect(url_for("connexion"))
            flash(message(contenu), "erreur")
        return render_template("inscription.html", valeurs=formulaire)
    return render_template("inscription.html", valeurs={})


@app.get("/deconnexion")
def deconnexion():
    session.clear()
    flash("Vous êtes déconnecté.", "succes")
    return redirect(url_for("connexion"))


# =============================================================================
# Utilisateur connecté : catalogue, fiche, avis, emprunts, listes, compte
# =============================================================================
@app.get("/")
@login_requis
def catalogue():
    filtres = {cle: request.args.get(cle, "").strip() for cle in ("q", "annee", "categorie", "tri")}
    films, code = api.films(**filtres)
    if code != 200:
        flash(message(films), "erreur")
        films = []
    categories, _ = api.categories()
    return render_template("catalogue.html", films=avec_genres(films, categories),
                           categories=categories, filtres=filtres)


@app.get("/films/<int:film_id>")
@login_requis
def fiche_film(film_id):
    film, code = api.film(film_id)
    if code == 404:
        return page_erreur("Film introuvable", "Ce film n'existe pas ou a été supprimé.", 404)
    if code != 200:
        return page_erreur("Erreur", message(film), 502)
    categories, _ = api.categories()
    utilisateur, _ = api.utilisateur(session["utilisateur_id"])
    mon_avis = next((a for a in film["avis"]
                     if a["utilisateur_id"] == session["utilisateur_id"]), None)
    return render_template("film.html", film=avec_genres([film], categories)[0],
                           mon_avis=mon_avis,
                           dans_envies=film_id in utilisateur.get("liste_envies", []),
                           deja_vu=film_id in utilisateur.get("films_vus", []))


@app.post("/films/<int:film_id>/avis")
@login_requis
def donner_avis(film_id):
    contenu, code = api.donner_avis(film_id, session["utilisateur_id"],
                                    entier(request.form.get("note")),
                                    request.form.get("commentaire", "").strip() or None)
    if code == 201:
        flash("Votre avis a été enregistré.", "succes")
    else:
        flash(message(contenu), "erreur")
    return redirect(url_for("fiche_film", film_id=film_id) + "#avis")


@app.post("/emprunter/<int:support_id>")
@login_requis
def emprunter(support_id):
    contenu, code = api.emprunter(session["utilisateur_id"], support_id)
    if code == 201:
        flash(f"Emprunt de « {contenu['titre']} » enregistré : retour prévu le "
              f"{date_fr(contenu['date_retour_prevue'])}.", "succes")
        film_id = contenu["film_id"]
    else:
        flash(message(contenu), "erreur")
        film_id = entier(request.form.get("film_id"))
    return redirect(url_for("fiche_film", film_id=film_id) if film_id else url_for("catalogue"))


LISTES = {
    "envies": ("ajouté à votre liste d'envies", "retiré de votre liste d'envies"),
    "vus": ("marqué comme vu", "retiré de vos films vus"),
}


def modifier_liste(liste, film_id):
    ajouter = request.form.get("action") != "retirer"
    contenu, code = api.modifier_liste(session["utilisateur_id"], liste, film_id, ajouter)
    if code == 200:
        flash(f"Film {LISTES[liste][0 if ajouter else 1]}.", "succes")
    else:
        flash(message(contenu), "erreur")
    return redirect(page_locale(request.form.get("suivant"),
                                url_for("fiche_film", film_id=film_id)))


@app.post("/envies/<int:film_id>")
@login_requis
def envies(film_id):
    return modifier_liste("envies", film_id)


@app.post("/vus/<int:film_id>")
@login_requis
def vus(film_id):
    return modifier_liste("vus", film_id)


@app.get("/compte")
@login_requis
def compte():
    utilisateur_id = session["utilisateur_id"]
    utilisateur, _ = api.utilisateur(utilisateur_id)
    emprunts, _ = api.emprunts(utilisateur_id)
    films, _ = api.films()
    par_id = {film["id"]: film for film in films}
    return render_template(
        "compte.html", utilisateur=utilisateur,
        en_cours=[e for e in emprunts if e["date_retour_effective"] is None],
        rendus=[e for e in emprunts if e["date_retour_effective"] is not None],
        envies=[par_id[i] for i in utilisateur["liste_envies"] if i in par_id],
        vus=[par_id[i] for i in utilisateur["films_vus"] if i in par_id])


@app.post("/emprunts/<int:emprunt_id>/retour")
@login_requis
def rendre(emprunt_id):
    contenu, code = api.rendre(emprunt_id, session["utilisateur_id"])
    if code == 200:
        flash(f"Retour de « {contenu['titre']} » enregistré, merci !", "succes")
    else:
        flash(message(contenu), "erreur")
    return redirect(url_for("compte"))


# =============================================================================
# Administrateur : films, supports, catégories, import TMDB, utilisateurs
# =============================================================================
def champs_film(formulaire):
    """Formulaire d'un film → champs JSON attendus par l'API."""
    acteurs = formulaire.get("acteurs", "").replace("\n", ",").split(",")
    return {
        "titre": formulaire.get("titre", "").strip(),
        "annee": entier(formulaire.get("annee")),
        "categories": [c for c in map(entier, formulaire.getlist("categories")) if c is not None],
        "acteurs": [a.strip() for a in acteurs if a.strip()],
        "description": formulaire.get("description", "").strip(),
        "affiche": formulaire.get("affiche", "").strip() or None,
    }


@app.route("/admin/films/ajouter", methods=["GET", "POST"])
@admin_requis
def ajouter_film():
    if request.method == "POST":
        film = champs_film(request.form)
        contenu, code = api.ajouter_film(film)
        if code == 201:
            flash(f"Film « {contenu['titre']} » ajouté.", "succes")
            return redirect(url_for("fiche_film", film_id=contenu["id"]))
        flash(message(contenu), "erreur")
    else:  # titre prérempli quand on vient de l'import TMDB
        film = {"titre": request.args.get("titre", "").strip()}
    categories, _ = api.categories()
    return render_template("admin_film.html", film=film, film_id=None, categories=categories)


@app.route("/admin/films/<int:film_id>/modifier", methods=["GET", "POST"])
@admin_requis
def modifier_film(film_id):
    if request.method == "POST":
        film = champs_film(request.form)
        contenu, code = api.modifier_film(film_id, film)
        if code == 200:
            flash(f"Film « {contenu['titre']} » modifié.", "succes")
            return redirect(url_for("fiche_film", film_id=film_id))
        if code == 404:
            return page_erreur("Film introuvable", message(contenu), 404)
        flash(message(contenu), "erreur")
    else:
        film, code = api.film(film_id)
        if code == 404:
            return page_erreur("Film introuvable", "Ce film n'existe pas ou a été supprimé.", 404)
    categories, _ = api.categories()
    return render_template("admin_film.html", film=film, film_id=film_id, categories=categories)


@app.post("/admin/films/<int:film_id>/supprimer")
@admin_requis
def supprimer_film(film_id):
    contenu, code = api.supprimer_film(film_id)
    if code == 200:
        flash(contenu["message"], "succes")
        return redirect(url_for("catalogue"))
    flash(message(contenu), "erreur")
    return redirect(url_for("fiche_film", film_id=film_id))


@app.route("/admin/films/<int:film_id>/supports", methods=["GET", "POST"])
@admin_requis
def supports_film(film_id):
    if request.method == "POST":
        action = request.form.get("action")
        support_id = entier(request.form.get("support_id"))
        champs = {"type": request.form.get("type", ""),
                  "format": request.form.get("format", "").strip(),
                  "lien": request.form.get("lien", "").strip() or None}
        if action == "ajouter":
            contenu, code = api.ajouter_support(film_id, champs)
            reussi, texte = code == 201, "Support ajouté."
        elif action == "modifier" and support_id:
            # la case « disponible » n'existe que pour un support déjà physique et non emprunté
            if (champs["type"] == "physique" and request.form.get("etait_physique") == "1"
                    and request.form.get("emprunte") != "1"):
                champs["disponible"] = request.form.get("disponible") == "1"
            contenu, code = api.modifier_support(support_id, champs)
            reussi, texte = code == 200, "Support modifié."
        elif action == "supprimer" and support_id:
            contenu, code = api.supprimer_support(support_id)
            reussi, texte = code == 200, "Support supprimé."
        else:
            abort(400)
        flash(texte if reussi else message(contenu), "succes" if reussi else "erreur")
        return redirect(url_for("supports_film", film_id=film_id))

    film, code = api.film(film_id)
    if code == 404:
        return page_erreur("Film introuvable", "Ce film n'existe pas ou a été supprimé.", 404)
    emprunts, _ = api.emprunts()
    en_cours = {e["support_id"]: e for e in emprunts if e["date_retour_effective"] is None}
    return render_template("admin_supports.html", film=film, en_cours=en_cours)


@app.route("/admin/categories", methods=["GET", "POST"])
@admin_requis
def gerer_categories():
    if request.method == "POST":
        action = request.form.get("action")
        categorie_id = entier(request.form.get("categorie_id"))
        nom = request.form.get("nom", "").strip()
        if action == "ajouter":
            contenu, code = api.ajouter_categorie(nom)
            reussi, texte = code == 201, f"Catégorie « {nom} » ajoutée."
        elif action == "renommer" and categorie_id:
            contenu, code = api.renommer_categorie(categorie_id, nom)
            reussi, texte = code == 200, f"Catégorie renommée en « {nom} »."
        elif action == "supprimer" and categorie_id:
            contenu, code = api.supprimer_categorie(categorie_id)
            reussi, texte = code == 200, contenu.get("message", "Catégorie supprimée.")
        else:
            abort(400)
        flash(texte if reussi else message(contenu), "succes" if reussi else "erreur")
        return redirect(url_for("gerer_categories"))

    categories, _ = api.categories()
    films, _ = api.films()
    nb_films = {c["id"]: sum(c["id"] in f["categories"] for f in films) for c in categories}
    return render_template("admin_categories.html", categories=categories, nb_films=nb_films)


@app.route("/admin/import", methods=["GET", "POST"])
@admin_requis
def import_tmdb():
    if request.method == "POST":
        contenu, code = api.importer_tmdb(entier(request.form.get("tmdb_id")))
        if code == 201:
            flash(f"« {contenu['titre']} » a été importé depuis TMDB.", "succes")
            return redirect(url_for("fiche_film", film_id=contenu["id"]))
        flash(message(contenu), "erreur")
        return redirect(url_for("import_tmdb", titre=request.form.get("titre", "")))

    titre = request.args.get("titre", "").strip()
    resultats, erreur_tmdb = None, None
    if titre:
        contenu, code = api.rechercher_tmdb(titre)
        if code == 200:
            resultats = contenu
        else:
            erreur_tmdb = message(contenu)
    return render_template("admin_import.html", titre=titre, resultats=resultats,
                           erreur_tmdb=erreur_tmdb)


@app.get("/admin/utilisateurs")
@admin_requis
def gerer_utilisateurs():
    utilisateurs, _ = api.utilisateurs()
    return render_template("admin_utilisateurs.html", utilisateurs=utilisateurs)


@app.post("/admin/utilisateurs/<int:utilisateur_id>/bloquer")
@admin_requis
def bloquer_utilisateur(utilisateur_id):
    if utilisateur_id == session["utilisateur_id"]:
        flash("Vous ne pouvez pas bloquer votre propre compte.", "erreur")
        return redirect(url_for("gerer_utilisateurs"))
    bloque = request.form.get("bloque") == "1"
    contenu, code = api.bloquer(utilisateur_id, bloque)
    if code == 200:
        flash(f"Compte « {contenu['nom_utilisateur']} » {'bloqué' if bloque else 'débloqué'}.",
              "succes")
    else:
        flash(message(contenu), "erreur")
    return redirect(url_for("gerer_utilisateurs"))
