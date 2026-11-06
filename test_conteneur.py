"""Pages de test du conteneur Flask (partie « Création et test des conteneurs
Flask » du sujet). Elles fonctionnent sans l'API :

- /test/simple      : une page HTML simple ;
- /test/formulaire  : un formulaire, traité en Python puis affiché avec Jinja ;
- /test/videotheque : un template Jinja qui exploite les données d'un fichier
                      JSON (exemples/videotheque.json).
"""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

bp = Blueprint("test", __name__, url_prefix="/test")

FICHIER_EXEMPLE = Path(__file__).resolve().parent / "exemples" / "videotheque.json"
GENRES = ["Action", "Animation", "Comédie", "Drame", "Science-Fiction"]


@bp.get("/")
def accueil():
    return render_template("test/index.html")


@bp.get("/simple")
def page_simple():
    return render_template("test/simple.html")


@bp.route("/formulaire", methods=["GET", "POST"])
def formulaire():
    if request.method == "GET":
        return render_template("test/formulaire.html", genres=GENRES)

    # Traitement du formulaire en Python
    prenom = request.form.get("prenom", "").strip()
    film = request.form.get("film", "").strip()
    note = request.form.get("note", "")
    genres = [g for g in request.form.getlist("genres") if g in GENRES]
    erreurs = []
    if not prenom:
        erreurs.append("Le prénom est obligatoire.")
    if not film:
        erreurs.append("Le titre du film est obligatoire.")
    if note not in ("1", "2", "3", "4", "5"):
        erreurs.append("La note doit être comprise entre 1 et 5.")
    return render_template("test/resultat.html", prenom=prenom, film=film,
                           note=int(note) if not erreurs else 0, genres=genres,
                           erreurs=erreurs)


@bp.get("/videotheque")
def videotheque():
    with open(FICHIER_EXEMPLE, encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    noms = {c["id"]: c["nom"] for c in donnees["categories"]}
    genre = request.args.get("genre", type=int)
    films = [f for f in donnees["films"] if genre is None or genre in f["categories"]]
    return render_template("test/videotheque.html",
                           films=sorted(films, key=lambda f: f["annee"]),
                           categories=donnees["categories"], noms=noms, genre=genre,
                           total=len(donnees["films"]))
