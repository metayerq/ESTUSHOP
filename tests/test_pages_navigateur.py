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
    # ⚠️ REMONTÉE DE LA CAISSE LE 30/09/2026. L'écran émet des documents fiscaux : un script
    # mort y produirait un formulaire vide, ou pire un bouton actif sur un brouillon incomplet.
    # On exige donc les trois étapes rendues, le mode d'émission ANNONCÉ, et le bouton DÉSACTIVÉ
    # tant qu'il manque quelque chose.
    "faturar.html": {
        "reponses": {
            "/api/faturar/referenciais": {
                # ⚠️ TOUT LE CATALOGUE, PAS UN FILTRE. Le marqueur « sans catégorie » hérité de
                # la caisse ne rendait qu'un article — « sticks » — et cachait la fiche qui
                # avait servi à la seule facture réelle. L'écran l'a dit avant nous.
                "artigos": [
                    {"id": 900, "titre": "sticks", "reference": "STK1", "categorie": None,
                     "categoria": "", "taux": 23},
                    {"id": 372683324, "titre": "Comissao sobre vendas", "reference": "VCOM141",
                     "categorie": 342853712, "categoria": "Extra", "taux": 23},
                    {"id": 700, "titre": "Espresso", "reference": "ESP", "categorie": 1,
                     "categoria": "Coffee", "taux": 13},
                ],
                "pagamentos": [{"id": 342853234, "titre": "Multibanco"},
                               {"id": 342853233, "titre": "Numerario"}],
                "clientes": [{"id": 372689903, "nom": "TOMOKO HIRAOJI.", "nif": "332457389",
                              "adresse": "Rua Heróis de Quionga 17", "code_postal": "1170-178",
                              "ville": "Lisboa", "email": "", "incomplet": False},
                             {"id": 372689904, "nom": "", "nif": "500000000", "adresse": "",
                              "code_postal": "", "ville": "", "email": "", "incomplet": True}],
                # La dernière facture réelle, telle que le cache la porte.
                "ultima": {"jour": "2026-09-08", "numero": "FR 01P2026/1", "type": "FR",
                           "client": {"nom": "TOMOKO HIRAOJI.", "nif": "332457389",
                                      "adresse": "Rua Heróis de Quionga 17",
                                      "code_postal": "1170-178", "ville": "Lisboa", "email": ""},
                           "lignes": [{"libelle": "Comissao sobre venda popup 15 agosto",
                                       "montant_cents": 13650, "ttc": True, "taux": 23,
                                       "qty": 1, "service_id": 0}],
                           "moyen_paiement": "Multibanco"},
                "caixa": 342853246,
                "modo": "tests",
            },
        },
        "attendu": [
            # Les trois étapes : la troisième existe pour être lue avant d'émettre.
            "L'acquéreur", "Les prestations", "Relire, puis émettre",
            # ⚠️ LE MODE EST ANNONCÉ. Émettre en « tests » en croyant émettre pour de vrai
            # laisse le client sans facture ; l'inverse abîme une série fiscale.
            "mode tests", "342853246",
            # ⚠️ LA REPRISE DE LA DERNIÈRE FACTURE, la fonction la plus utile de l'écran : une
            # facture tous les deux mois, et entre deux personne ne se souvient de rien.
            "FR 01P2026/1", "Reprendre cette facture", "émise le 2026-09-08",
            # Le catalogue entier est proposé, avec sa catégorie — « Espresso · Coffee » prouve
            # qu'aucun filtre ne cache les fiches vendables.
            "Comissao sobre vendas", "Espresso", "Coffee",
            "Multibanco", "TOMOKO HIRAOJI.",
            # La relecture reprend la forme du document imprimé : c'est l'objet qu'on compare.
            "Descrição", "Taxa", "Sumário",
            # ⚠️ ET CE QUI MANQUE EST DIT, EN ENTIER, dès le premier rendu.
            "Il manque", "nom du client", "NIF à 9 chiffres",
            # Le scénario ci-dessous tape dans le champ montant : la frappe doit survivre et le
            # montant déduit doit suivre. 136,50 TTC à 23 % font 110,98 € HT.
            "SAISIE-OK", "DEDUIT-OK", "110,98",
        ],
        # ⚠️ CE QUI NE DOIT SURTOUT PAS S'AFFICHER. Le référentiel annonce `modo: "tests"` :
        # voir « émission réelle » voudrait dire que l'écran affiche le mode qu'il suppose et
        # non celui que le serveur donne. On émettrait pour de vrai en croyant essayer — ou
        # l'inverse, qui laisse le client sans facture.
        "interdit": ["émission réelle",
                     # ⚠️ LE CHAMP MONTANT DOIT RESTER SAISISSABLE. Le tableau était redessiné à
                     # chaque frappe : le champ en cours de saisie était détruit, perdait le
                     # focus, et plus rien ne pouvait y être tapé. L'écran s'affichait
                     # parfaitement et ne servait à rien.
                     "SAISIE-PERDUE", "DEDUIT-MUET"],
        # Le scénario tape un montant et vérifie que la frappe survit ET que le montant déduit
        # suit. Il écrit son verdict dans la page, que le dump ramène.
        "scenario": """
(function attendre(n){
  var champ = document.querySelector('#fa-corps input[inputmode=decimal]');
  if(!champ && n < 60) return setTimeout(function(){ attendre(n+1); }, 20);
  var marque = document.createElement('div');
  document.body.appendChild(marque);
  if(!champ){ marque.textContent = 'SAISIE-PERDUE aucun champ montant'; return; }
  champ.focus();
  champ.value = '136,50';
  champ.dispatchEvent(new Event('input', {bubbles:true}));
  var vivant = document.querySelector('#fa-corps input[inputmode=decimal]');
  var focus  = document.activeElement === vivant;
  var garde  = vivant && vivant.value === '136,50';
  var deduit = (document.getElementById('fa-deduit-0') || {}).textContent || '';
  marque.textContent =
    (focus && garde ? 'SAISIE-OK' : 'SAISIE-PERDUE focus=' + focus + ' valeur=' + (vivant && vivant.value)) +
    ' | ' + (deduit.indexOf('110,98') >= 0 ? 'DEDUIT-OK ' + deduit : 'DEDUIT-MUET ' + deduit);
})(0);
""",
    },
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
                    {"id": 12, "line_no": 1, "raw_text": ",32 Uni Fiambre 23% 6,40 Preco: 20,00/Uni",
                     "qty": 0.32, "unit": "Uni", "unit_price_cents": 2000,
                     "line_total_cents": 640, "ingredient": "Jambon artisanal",
                     "price_per_ref": None, "qty_ref": None, "match_source": "asked"},
                    {"id": 13, "line_no": 2, "raw_text": ",478 Uni Paupiette KG 6% 16,73",
                     "qty": 0.478, "unit": "KG", "unit_price_cents": 3500,
                     "line_total_cents": 1673, "ingredient": None,
                     "price_per_ref": None, "qty_ref": None, "match_source": "unmatched"},
                ],
                "resumo": {"id": 6, "linhas": 2, "linhas_sem_ingrediente": 1,
                           "valor_sem_ingrediente_cents": 1673, "ecart_cents": 0,
                           "total_cents": 3213, "linhas_sem_valor": 1,
                           "valor_hors_couts_cents": 2313},
            },
            # ⚠️ Le détail charge aussi la liste des ingrédients : sans bouchon, `fetch`
            # rend `{}` et le `<select>` de rattachement reste vide — l'écran d'édition
            # s'afficherait sans sa seule fonction.
            "/api/arquivo-faturas/ingredientes": {
                "ingredientes": [{"name": "Café Gardelli", "unit_ref": "kg"},
                                 {"name": "El Tambo", "unit_ref": "kg"}],
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
                           "hors_custos_cents": 3213, "linhas_sem_valor": 1,
                           "com_divergencia": 0, "sem_linhas": 1},
            },
        },
        # ⚠️ ON EXIGE LE MONTANT NON RATTACHÉ ET « aucune ligne lue » : ce sont les deux
        # signaux pour lesquels l'écran existe. Un tableau qui s'affiche sans eux est un
        # tableau qui ne sert à rien.
        "attendu": ["TALHO DO CAMPO", "2/3 sans ingrédient", "aucune ligne lue",
                    "38,82", "23 sept. 2026",
                    # ⚠️ ON EXIGE LES COMMANDES D'ÉCRITURE : un écran d'archive qui ne se
                    # corrige plus se dégraderait sans que rien ne rougisse.
                    "Supprimer cette facture", "Ajouter une ligne", "Café Gardelli",
                    # ⚠️ ET SURTOUT L'ÉTAT QUI A L'AIR RÉPARÉ : une ligne rattachée dont la
                    # conversion d'unité a échoué ne pèse RIEN dans les coûts. L'avertissement
                    # ne vivait que le temps d'un clic ; il doit survivre au rechargement.
                    "32,13", "sans quantité de référence",
                    "ne compte dans AUCUN coût de revient",
                    # La fiche remplace le tableau : ses deux moitiés portent le sens.
                    "Sur la facture", "En stock, pour les coûts", "Ligne 1"],
        "interdit": ["NaN", "undefined", "ligne(s)", "32.13", "[object Object]"],
        # Ouvre directement la facture 6 : c'est aussi ce que fait un lien partagé.
        "suffixe": "?id=6",
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


def _rendre(nom, reponses, tmp_path, scenario=None):
    env = Environment(loader=FileSystemLoader(os.path.join(RACINE, "templates")))
    html = env.get_template(nom).render(v="test", role="admin")
    sonde = SONDE.replace("__REPONSES__", json.dumps(reponses))
    # ⚠️ AVANT LES SCRIPTS DE LA PAGE, sinon le bouchon arrive après le premier appel.
    html = re.sub(r"<body[^>]*>", lambda m: m.group(0) + sonde, html, count=1)
    # ⚠️ LE SCÉNARIO PASSE APRÈS LES SCRIPTS DE LA PAGE, et il attend que l'écran soit peuplé.
    # Sans lui, ce harnais ne voit qu'un rendu figé : il ne peut pas attraper une page qui
    # s'affiche correctement mais devient inutilisable dès qu'on y tape — c'est arrivé deux fois.
    if scenario:
        html = html.replace("</body>", "<script>" + scenario + "</script></body>", 1)
    chemin = tmp_path / nom
    io.open(chemin, "w", encoding="utf-8").write(html)
    return chemin


@SANS
@pytest.mark.parametrize("nom", sorted(CAS))
def test_la_page_s_affiche_vraiment(nom, tmp_path):
    binaire, env = NAVIGATEUR
    cas = CAS[nom]
    chemin = _rendre(nom, cas["reponses"], tmp_path, cas.get("scenario"))

    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--virtual-time-budget=4000", "file://" + str(chemin) + cas.get("suffixe", "")],
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
