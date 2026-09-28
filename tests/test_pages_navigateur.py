"""
LES PAGES DOIVENT S'AFFICHER, PAS SEULEMENT SE PARSER.

⚠️ TROIS PANNES EN UNE SOIRÉE ONT MONTRÉ CE QUI MANQUAIT, et aucune n'était détectable en lisant
le fichier :

  1. Un commentaire citant une fermeture de commentaire refermait le bloc en avance — TOUT le
     script de `/cogs` devenait invalide. La page s'affichait, muette.
  2. `onclick="basculer(${JSON.stringify(zone)})"` rendait `onclick="basculer("` : l'attribut se
     fermait au premier guillemet. Les catégories de l'inventaire ne s'ouvraient pas, les champs
     n'enregistraient rien. La page n'avait JAMAIS fonctionné.
  3. Une variable lue avant sa déclaration laissait `/marge` entièrement vide.

Dans les trois cas, `node --check` était content : c'est le HTML PRODUIT À L'EXÉCUTION qui était
cassé, ou l'ordre d'exécution. Seul un navigateur répond à « est-ce que ça s'affiche ».

⚠️ ET LE RÉSEAU EST BOUCHONNÉ, PAS APPELÉ. Un test qui interroge Vendus serait lent, dépendant
d'une clé, et il échouerait pour des raisons qui n'ont rien à voir avec la page.

⚠️ CE TEST S'IGNORE S'IL N'Y A PAS DE NAVIGATEUR, et il dit comment l'installer. Un test qui
exige un binaire absent bloque toute la suite pour tout le monde ; un test qui se tait sans
raison ne sert à rien. Variables reconnues : `CHROME_BIN` (le binaire) et `CHROME_LIB_PATH`
(bibliothèques, pour un Chromium extrait à la main).
"""
import glob
import io
import json
import os
import re
import shutil
import subprocess

import pytest
from jinja2 import Environment, FileSystemLoader

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _navigateur():
    """Le binaire et son environnement, ou `None`. Vérifié en le LANÇANT, pas en le trouvant."""
    candidats = [os.environ.get("CHROME_BIN")] if os.environ.get("CHROME_BIN") else []
    candidats += [shutil.which(n) for n in
                  ("chromium", "chromium-browser", "google-chrome", "chrome-headless-shell")]
    candidats += sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell")))
    candidats += sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))

    env = dict(os.environ)
    if os.environ.get("CHROME_LIB_PATH"):
        env["LD_LIBRARY_PATH"] = os.environ["CHROME_LIB_PATH"]

    for c in [x for x in candidats if x and os.path.exists(x)]:
        try:
            r = subprocess.run([c, "--headless", "--no-sandbox", "--disable-gpu", "--version"],
                               capture_output=True, timeout=25, env=env)
            if r.returncode == 0:
                return c, env
        except (OSError, subprocess.SubprocessError):
            continue
    return None


NAVIGATEUR = _navigateur()
SANS = pytest.mark.skipif(
    NAVIGATEUR is None,
    reason="aucun navigateur utilisable — installer chromium, ou renseigner CHROME_BIN "
           "(et CHROME_LIB_PATH si le binaire est extrait à la main)")

# ── Ce que chaque page doit AVOIR AFFICHÉ une fois son script passé ───────────────────────────
#
# ⚠️ ON VÉRIFIE DU TEXTE RENDU, PAS LA PRÉSENCE D'UN GABARIT. Un conteneur vide prouve que le
# script est mort ; c'est exactement ce qui s'est produit trois fois.
CAS = {
    "marge.html": {
        "reponses": {
            "/api/marge": {
                "periode": {"de": "2026-09-20", "a": "2026-09-26", "jours": 7},
                "ca_ht": 4210.55, "cogs_theorique": 1180.2, "marge_theorique_pct": 72.0,
                "marge_theorique_eur": 3030.35, "documents": 183, "couverture_ca_pct": 86.4,
                "sans_recette": ["Tea of the month"], "ca_sans_recette": 572.4,
                "achats_factures": 1642.9, "ingredients_sans_prix": ["Sel"], "avertissements": [],
            },
            "/api/variance": {
                "etat": "ok", "periode": {"de": "2026-09-21", "a": "2026-09-24"},
                "comptes": {"communs": 5},
                "totaux": {"cout_ecart": 38.4, "cogs_reel": 1218.6, "couverture_pct": 61.5},
                "marge": {"marge_reelle_pct": 71.1, "marge_theorique_pct": 72.0},
            },
        },
        "attendu": ["71,1", "4 210,55", "Marge réelle", "183", "septembre"],
        # ⚠️ Un format anglais à l'écran veut dire que le formateur a été contourné.
        "interdit": ["4210,55", "NaN", "undefined", "ingrédient(s)"],
    },
    "arquivo_faturas.html": {
        "reponses": {
            "/api/arquivo-faturas/6": {
                "fatura": {"id": 6, "data": "2026-09-23", "fornecedor": "TALHO DO CAMPO",
                           "nif": "515344940", "numero": "FS 1A2601/1844",
                           "subtotal_cents": 2830, "vat_cents": 383, "total_cents": 3213,
                           "posted_at": None, "scanned_by": None},
                "linhas": [
                    {"line_no": 1, "raw_text": ",32 Uni Fiambre 23% 6,40 Preco: 20,00/Uni",
                     "qty": 0.32, "unit": "Uni", "unit_price_cents": 2000,
                     "line_total_cents": 640, "ingredient": "El Tambo",
                     "price_per_ref": 20.0, "qty_ref": 0.32, "match_source": "asked"},
                    {"line_no": 2, "raw_text": ",478 Uni Paupiette KG 6% 16,73",
                     "qty": 0.478, "unit": "KG", "unit_price_cents": 3500,
                     "line_total_cents": 1673, "ingredient": None,
                     "price_per_ref": None, "qty_ref": None, "match_source": "unmatched"},
                ],
                "resumo": {"id": 6, "linhas": 2, "linhas_sem_ingrediente": 1,
                           "valor_sem_ingrediente_cents": 1673, "ecart_cents": 0,
                           "total_cents": 3213},
            },
            # ⚠️ LE BOUCHON COMPARE PAR PRÉFIXE : la liste doit venir APRÈS le détail, sinon
            # « /api/arquivo-faturas » attrape aussi « /api/arquivo-faturas/6 » et l'écran de
            # détail reçoit la liste — un test vert sur une page qui ne marche pas.
            "/api/arquivo-faturas": {
                "periodo": {"de": None, "a": None},
                "fornecedores": ["LIDL & Cia", "TALHO DO CAMPO"],
                "faturas": [
                    {"id": 6, "data": "2026-09-23", "fornecedor": "TALHO DO CAMPO",
                     "numero": "FS 1A2601/1844", "total_cents": 3213, "subtotal_cents": 2830,
                     "vat_cents": 383, "linhas": 3, "linhas_sem_ingrediente": 2,
                     "valor_sem_ingrediente_cents": 2573, "ecart_cents": 0},
                    {"id": 7, "data": "2026-09-18", "fornecedor": "LIDL & Cia",
                     "numero": "VD 044100326/000374", "total_cents": 669, "subtotal_cents": 631,
                     "vat_cents": 38, "linhas": 0, "linhas_sem_ingrediente": 0,
                     "valor_sem_ingrediente_cents": 0, "ecart_cents": None},
                ],
                "totais": {"faturas": 2, "total_cents": 3882, "sem_ingrediente_cents": 2573,
                           "com_divergencia": 0, "sem_linhas": 1},
            },
        },
        # ⚠️ ON EXIGE LE MONTANT NON RATTACHÉ ET « aucune ligne lue » : ce sont les deux
        # signaux pour lesquels l'écran existe. Un tableau qui s'affiche sans eux est un
        # tableau qui ne sert à rien.
        "attendu": ["TALHO DO CAMPO", "25,73", "2/3 sans ingrédient", "aucune ligne lue",
                    "38,82", "23 sept. 2026"],
        "interdit": ["NaN", "undefined", "ligne(s)", "32.13", "[object Object]"],
    },
    "inventario.html": {
        "reponses": {
            "/api/inventario": {
                "jour": "2026-09-27", "seance": None, "comptes": {},
                "valeur_source": "achats", "valeur_jours": 60,
                "ingredients": [
                    {"name": 'Café "Bica"', "unit_ref": "kg", "category": "café", "valeur": 380},
                    {"name": "Lait frais", "unit_ref": "l", "category": "lait", "valeur": 420},
                    {"name": "Sucre", "unit_ref": "kg", "category": "divers", "valeur": 3},
                ],
            },
        },
        "attendu": ["L'essentiel", "Lait frais", "essentiels comptés", "data-nom"],
        "interdit": ["NaN", "undefined", "JSON.stringify"],
    },
}

# ⚠️ LE PIÈGE EST PIÉGÉ : une erreur non rattrapée écrit dans le titre, qui survit au `--dump-dom`.
#    C'est le seul canal qui traverse un rendu sans protocole de débogage.
SONDE = """<script>
window.addEventListener('error', function (e) {
  document.title = 'ERREUR ' + (e && e.message ? e.message : 'inconnue');
});
window.addEventListener('unhandledrejection', function (e) {
  document.title = 'ERREUR promesse ' + (e && e.reason ? e.reason : '');
});
window.fetch = function (u) {
  var url = String(u), d = __REPONSES__, r = null;
  for (var k in d) if (url.indexOf(k) === 0) { r = d[k]; break; }
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve(r || {}); } });
};
</script>"""


def _rendre(nom, reponses, tmp_path):
    env = Environment(loader=FileSystemLoader(os.path.join(RACINE, "templates")))
    html = env.get_template(nom).render(v="test", role="admin")
    sonde = SONDE.replace("__REPONSES__", json.dumps(reponses))
    # ⚠️ AVANT LES SCRIPTS DE LA PAGE, sinon le bouchon arrive après le premier appel.
    html = re.sub(r"<body[^>]*>", lambda m: m.group(0) + sonde, html, count=1)
    chemin = tmp_path / nom
    io.open(chemin, "w", encoding="utf-8").write(html)
    return chemin


@SANS
@pytest.mark.parametrize("nom", sorted(CAS))
def test_la_page_s_affiche_vraiment(nom, tmp_path):
    binaire, env = NAVIGATEUR
    cas = CAS[nom]
    chemin = _rendre(nom, cas["reponses"], tmp_path)

    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--virtual-time-budget=4000", "file://" + str(chemin)],
        capture_output=True, text=True, timeout=90, env=env)
    dom = r.stdout

    assert dom.strip(), f"{nom} : le navigateur n'a rien rendu\n{r.stderr[:400]}"

    """
    ⚠️ ON REGARDE CE QUI EST AFFICHÉ, PAS LE CODE QUI L'AFFICHE. `--dump-dom` rend le document
    ENTIER, scripts et styles compris : chercher « JSON.stringify » ou « undefined » dedans
    trouvait le source du fichier et faisait échouer un rendu parfaitement correct. C'est la
    même faute que celle qu'on passe la journée à corriger ailleurs — un contrôle qui lit du
    code comme s'il était du texte affiché.
    """
    rendu = re.sub(r"<script[\s\S]*?</script>", " ", dom, flags=re.I)
    rendu = re.sub(r"<style[\s\S]*?</style>", " ", rendu, flags=re.I)

    titre = re.search(r"<title[^>]*>(.*?)</title>", dom, re.S)
    assert not (titre and titre.group(1).startswith("ERREUR")), (
        f"{nom} : erreur JavaScript non rattrapée — « {titre.group(1)[:200]} »")

    for m in cas["attendu"]:
        assert m in rendu, (
            f"{nom} : « {m} » absent du rendu — le script est mort ou n'a rien écrit. "
            "C'est exactement la panne qu'aucun contrôle de syntaxe ne voit.")
    for m in cas["interdit"]:
        assert m not in rendu, f"{nom} : « {m} » apparaît à l'écran"
