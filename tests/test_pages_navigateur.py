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
            # ⚠️ LA BANDE D'ÉTAT DU BANDEAU GLOBAL, SUR CETTE PAGE COMME SUR LES AUTRES.
            # Un écart (singulier) et trois boissons (pluriel) : la même réponse exerce
            # les deux accords, et « 1 jour(s) » ne peut plus passer.
            "/api/statut": {
                "ca": 41855, "ca_texte": "418,55 €", "compare": "+12 % vs mardi dernier",
                "tickets": 63, "moyen_texte": "6,64 €",
                "ecarts": 1, "boissons_dues": 3, "caisse_ok": None,
            },
            "/api/faturar/referenciais": {
                # ⚠️ TOUT LE CATALOGUE, PAS UN FILTRE. Le marqueur « sans catégorie » hérité de
                # la caisse ne rendait qu'un article — « sticks » — et cachait la fiche qui avait
                # servi à la seule facture réelle. L'écran l'a dit avant nous.
                "artigos": [
                    {"id": 900, "titre": "sticks", "reference": "STK1", "categorie": None,
                     "categoria": "", "taux": 23},
                    {"id": 372683324, "titre": "Comissão sobre vendas", "reference": "VCOM141",
                     "categorie": 342853712, "categoria": "Extra", "taux": 23},
                    {"id": 700, "titre": "Espresso", "reference": "VICE10", "categorie": 1,
                     "categoria": "Coffee", "taux": 13},
                ],
                "pagamentos": [{"id": 342853234, "titre": "Multibanco"},
                               {"id": 342853233, "titre": "Numerario"}],
                "clientes": [{"id": 372689903, "nom": "TOMOKO HIRAOJI.", "nif": "332457389",
                              "adresse": "Rua Heróis de Quionga 17", "code_postal": "1170-178",
                              "ville": "Lisboa", "email": "", "incomplet": False},
                             {"id": 372689904, "nom": "", "nif": "500000000", "adresse": "",
                              "code_postal": "", "ville": "", "email": "", "incomplet": True}],
                # La dernière facture réelle, avec l'article DÉJÀ RÉSOLU par le serveur.
                "ultima": {"jour": "2026-09-08", "numero": "FR 01P2026/1", "type": "FR",
                           "client": {"nom": "TOMOKO HIRAOJI.", "nif": "332457389",
                                      "adresse": "Rua Heróis de Quionga 17",
                                      "code_postal": "1170-178", "ville": "Lisboa", "email": ""},
                           "lignes": [{"libelle": "Comissão sobre venda popup 15 agosto",
                                       "montant_cents": 13650, "ttc": True, "taux": 23,
                                       "qty": 1, "service_id": 372683324,
                                       "source_article": "reference"}],
                           "moyen_paiement": "Multibanco"},
                "caixa": 342853246,
                "modo": "tests",
            },
            # ⚠️ APRÈS `/referenciais`, jamais avant : le bouchon compare par préfixe.
            "/api/faturar": {"ok": True, "numero": "FR 01P2026/2", "id": 378400001,
                             "atcud": "J69MJVX5-2", "total": 136.50},
        },
        "attendu": [
            "L'acquéreur", "Les prestations", "Le document",
            # ⚠️ LE FIL DES ÉTAPES BOUGE : « 1 · Qui » tant que c'est à faire, « ✓ Qui »
            # une fois acquis. Trois pastilles numérotées vertes se lisaient encore comme
            # trois choses à faire. La transition est tracée par le scénario ; ici on exige
            # l'état final, facture émise, tout acquis.
            "✓ Relire",
            "ETAPE-NEUVE", "ETAPE-FAITE",
            # ⚠️ DE VRAIS ACCORDS DANS LA BANDE D'ÉTAT : elle est sous les yeux toute
            # la journée, et c'est là qu'un écart de caisse se rattrape.
            "1 jour à vérifier", "3 boissons dues", "418,55 €",
            # ⚠️ LE MODE EST ANNONCÉ : liseré, badge, libellé du bouton.
            "TESTS · caisse 342853246",
            "Multibanco", "TOMOKO HIRAOJI.", "Ce qui partira",
            "Descrição", "Taxa", "Sumário",
            # ⚠️ AUCUN ✗ AVANT D'AVOIR TOUCHÉ : un écran neuf tout en rouge apprend à ignorer
            # le rouge, et c'est celui qui compte qu'on rate ensuite.
            "CHECK-VIERGE oui", "OUVERTURE-CALME", "PRESELECTION-OK", "REFERENCE-VISIBLE",
            "FOCUS-OFFRE-TOUT",
            # ⚠️ LE CRITÈRE DU POINT 1 : reprendre suffit, article compris.
            "REPRISE-COMPLETE",
            # ⚠️ ET L'ACCENT TRAVERSE : « Comissão », pas « Comissao ».
            "Comissão sobre venda popup 15 agosto",
            # Tout le catalogue est offert, fiches vendables comprises.
            "CATALOGUE-COMPLET",
            "SAISIE-OK", "DEDUIT-OK", "TOTALLIGNE-OK",
            # ⚠️ LA BASCULE HT/TTC : une seule, globale, et elle change le montant facturé.
            "BASCULE-UNIQUE", "HT-VERS-TTC-OK", "RETOUR-TTC-OK",
            # ⚠️ TOUT DOIT SE FAIRE AU CLAVIER, liste d'articles comprise.
            "CLAVIER-OK", "AIDE-OUVRABLE", "ACCORD-FICHES-OK",
            "FR-SANS-ECHEANCE", "FT-SANS-REGLEMENT", "ENTREE-NOUVELLE-LIGNE",
            "ECART-SIGNALE", "EMAIL-EXPLICITE",
            "PRET-OUI", "CONFIRM-OK",
            # ⚠️ LE VERROU POST-ÉMISSION, la correction la plus importante de cet écran.
            "VERROU-OK", "NUMERO-OK", "PDF-OK",
        ],
        "interdit": [
            # Le mode réel ne doit pas s'afficher quand le serveur annonce « tests ».
            "RÉEL · caisse", "Émettre — RÉEL",
            # Les bandeaux du haut ont disparu : un seul endroit dit ce qui manque.
            "Il manque :",
            "SAISIE-PERDUE", "DEDUIT-MUET", "TOTALLIGNE-MUET", "ECART-MUET", "EMAIL-IMPLICITE",
            "BASCULE-PAR-LIGNE", "HT-VERS-TTC-MUET", "RETOUR-TTC-MUET",
            "CLAVIER-MUET", "AIDE-MUETTE", "ACCORD-FICHES-MUET",
            "FR-AVEC-ECHEANCE", "FT-AVEC-REGLEMENT", "OUVERTURE-ENCOMBREE",
            "ENTREE-MUETTE", "PRESELECTION-MUETTE", "REFERENCE-ABSENTE", "FOCUS-SE-FILTRE",
            "REPRISE-TROUEE", "REPRISE-ABSENTE", "CATALOGUE-FILTRE", "PRET-NON",
            "CONFIRM-ABSENT", "VERROU-ROMPU", "NUMERO-MUET", "PDF-ABSENT", "CHECK-VIERGE non",
            "ETAPE-NEUVE-MUETTE", "ETAPE-FIGEE",
            # Les accords de formulaire administratif, nulle part.
            "jour(s)", "boisson(s)", "due(s)", "fiche(s)", "proposée(s)",
            # ⚠️ PAS « 3 boisson » : c'est un préfixe de la bonne sortie, et le marqueur
            # interdit rougissait sur le rendu correct. Un contrôle qui se déclenche sur
            # ce qu'il cherche à obtenir ne contrôle rien.
            "1 jours", "3 boisson due", "1 jour(s)",
            "NaN", "undefined",
        ],
        "scenario": r"""
(function attendre(n){
  var E = function(i){ return document.getElementById(i); };
  if((!E('fa-reprendre') || E('fa-reprendre').hidden) && n < 80)
    return setTimeout(function(){ attendre(n+1); }, 20);
  var trace = function(t){ var d = document.createElement('div'); d.textContent = t;
                           document.body.appendChild(d); };

  /* ⚠️ L'ÉCRAN S'OUVRE CALME. La ligne vide prenait le focus au chargement : la liste
     d'articles se dépliait toute seule par-dessus le reste, avant même qu'un client soit
     choisi — alors que l'étape 1 est le client. */
  trace((E('cba0-liste').hidden && document.activeElement !== E('cba0-input'))
        ? 'OUVERTURE-CALME' : 'OUVERTURE-ENCOMBREE');

  /* ⚠️ LA LIGNE NEUVE ARRIVE AVEC LE DERNIER ARTICLE, ET RIEN D'AUTRE. L'article est pré-posé
     et VISIBLE — on peut le changer ; le libellé et le montant restent vides, parce que
     réimprimer le texte et la somme du mois dernier serait une faute, pas une aide. */
  var libelle = document.querySelector('#fa-corps input[aria-label^="Libellé imprimé"]');
  var somme   = document.querySelector('#fa-corps input[inputmode=decimal]');
  trace((E('cba0-input').value.indexOf('Comiss') === 0 && !libelle.value && !somme.value)
        ? 'PRESELECTION-OK'
        : 'PRESELECTION-MUETTE art=' + E('cba0-input').value
          + ' lib=' + libelle.value + ' mt=' + somme.value);

  /* ⚠️ LA RÉFÉRENCE IDENTIFIE LA FICHE, LE TITRE NON. La facture imprime ce code dans la
     colonne « Código », et deux fiches peuvent porter le même titre. */
  var refChamp = E('fa-ref-0').textContent.indexOf('VCOM141') >= 0;
  E('cba0-input').focus();
  var texteListe = E('cba0-liste').textContent;
  var refListe = texteListe.indexOf('VCOM141') >= 0;
  trace((refChamp && refListe) ? 'REFERENCE-VISIBLE'
        : 'REFERENCE-ABSENTE champ=' + refChamp + ' liste=' + refListe);

  /* ⚠️ CLIQUER DANS UN CHAMP DÉJÀ REMPLI OFFRE TOUT LE CATALOGUE. S'en servir comme filtre
     n'offrait que la fiche déjà posée : changer d'article demandait de tout effacer d'abord. */
  trace((texteListe.indexOf('Espresso') >= 0 && texteListe.indexOf('sticks') >= 0)
        ? 'FOCUS-OFFRE-TOUT' : 'FOCUS-SE-FILTRE ' + texteListe.slice(0,70));
  E('cba0-input').blur(); cbFermer('cba0');

  var vierge = E('fa-check').textContent.replace(/\s+/g,' ').trim();
  trace('CHECK-VIERGE ' + (vierge.indexOf('\u2717') < 0 ? 'oui' : 'non ' + vierge));

  var etape = function(){ return E('fa-et-1').textContent.replace(/\s+/g,' ').trim(); };
  trace(etape() === '1 \u00b7 Qui' ? 'ETAPE-NEUVE' : 'ETAPE-NEUVE-MUETTE ' + etape());

  /* ⚠️ LE COMPTE DE FICHES S'ACCORDE AUSSI, et il dit combien sont MASQUÉES. Une fiche sans
     nom ne peut pas porter une facture : elle est cachée par défaut, et le compte doit
     l'annoncer plutôt que la faire disparaître en silence. Le bouchon en a deux, dont une
     sans nom — les deux accords passent par ici. */
  var boutons = E('fa-client-zone').querySelectorAll('button');
  var compte = function(){ return E('fa-client-zone').textContent.replace(/\s+/g,' '); };
  var un = compte().indexOf('1 fiche proposée') >= 0;
  boutons[1].click();
  var deux = compte().indexOf('2 fiches proposées') >= 0;
  trace((un && deux) ? 'ACCORD-FICHES-OK' : 'ACCORD-FICHES-MUET ' + compte().slice(0,90));
  E('fa-client-zone').querySelectorAll('button')[1].click();

  var reprise = document.querySelector('#fa-reprendre button');
  if(!reprise){ trace('REPRISE-ABSENTE'); return; }
  reprise.click();
  trace(etape() === '\u2713 Qui' ? 'ETAPE-FAITE' : 'ETAPE-FIGEE ' + etape());
  var art = E('cba0-input');
  trace((art && art.value.indexOf('Comiss') === 0)
        ? 'REPRISE-COMPLETE' : 'REPRISE-TROUEE article=' + (art && art.value));

  art.focus(); art.value = '';
  art.dispatchEvent(new Event('input', {bubbles:true}));
  var liste = E('cba0-liste').textContent;
  trace((liste.indexOf('Espresso') >= 0 && liste.indexOf('Coffee') >= 0)
        ? 'CATALOGUE-COMPLET' : 'CATALOGUE-FILTRE ' + liste.slice(0,70));
  /* ⚠️ LA LISTE SE PARCOURT AU CLAVIER. Un <li> qui n'écoute que `mousedown` est une liste
     que personne ne peut traverser sans souris. */
  art.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowDown', bubbles:true}));
  art.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
  trace((E('cba0-input').value && E('cba0-liste').hidden)
        ? 'CLAVIER-OK'
        : 'CLAVIER-MUET v=' + E('cba0-input').value + ' cache=' + E('cba0-liste').hidden);

  /* On repose ensuite l'article de la facture réelle, à la souris. */
  var art2 = E('cba0-input');
  art2.focus(); art2.value = '';
  art2.dispatchEvent(new Event('input', {bubbles:true}));
  document.querySelector('#cba0-liste li[data-v="372683324"]')
    .dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));

  /* ⚠️ L'EXPLICATION DU PIÈGE TTC/HT ÉTAIT UN `title` : rien au clavier, rien au doigt. */
  var aide = E('fa-aide-ttc'), texte = E('fa-aide-ttc-texte');
  var cacheAvant = texte.hidden;
  aide.click();
  trace((cacheAvant && !texte.hidden
         && aide.getAttribute('aria-expanded') === 'true'
         && texte.textContent.indexOf('136,51') >= 0) ? 'AIDE-OUVRABLE' : 'AIDE-MUETTE');

  var champ = document.querySelector('#fa-corps input[inputmode=decimal]');
  champ.focus(); champ.value = '136,50';
  champ.dispatchEvent(new Event('input', {bubbles:true}));
  var vivant = document.querySelector('#fa-corps input[inputmode=decimal]');
  trace((document.activeElement === vivant && vivant.value === '136,50')
        ? 'SAISIE-OK' : 'SAISIE-PERDUE');
  trace((E('fa-deduit-0').textContent.indexOf('110,98') >= 0) ? 'DEDUIT-OK' : 'DEDUIT-MUET');
  trace((E('fa-lt-0').textContent.indexOf('136,50') >= 0) ? 'TOTALLIGNE-OK' : 'TOTALLIGNE-MUET');

  /* ⚠️ LA BASCULE HT/TTC EST GLOBALE, ET ELLE DÉCIDE DU MONTANT FACTURÉ : 136,50 saisis en HT
     font une facture à 167,90 €. Une bascule par ligne rendait deux lignes incohérentes. */
  trace(document.querySelectorAll('#fa-corps .fa-seg').length === 0
        ? 'BASCULE-UNIQUE' : 'BASCULE-PAR-LIGNE');
  E('fa-seg-ttc').children[1].click();
  trace((E('fa-deduit-0').textContent.indexOf('167,90') >= 0
         && E('fa-lt-0').textContent.indexOf('167,90') >= 0)
        ? 'HT-VERS-TTC-OK'
        : 'HT-VERS-TTC-MUET d=' + E('fa-deduit-0').textContent
                        + ' t=' + E('fa-lt-0').textContent);
  E('fa-seg-ttc').children[0].click();
  trace((E('fa-lt-0').textContent.indexOf('136,50') >= 0) ? 'RETOUR-TTC-OK' : 'RETOUR-TTC-MUET');

  var taux = document.querySelector('#fa-corps select');
  taux.value = '13'; taux.dispatchEvent(new Event('change', {bubbles:true}));
  trace((E('fa-corps').textContent.indexOf('fiche (23%)') >= 0) ? 'ECART-SIGNALE' : 'ECART-MUET');
  taux.value = '23'; taux.dispatchEvent(new Event('change', {bubbles:true}));

  E('fa-client-zone').querySelector('button').click();
  var mail = E('c-email'); mail.value = 'tomoko@exemple.pt';
  mail.dispatchEvent(new Event('input', {bubbles:true}));
  var avant = E('fa-relire').textContent.indexOf('aucun envoi') >= 0;
  var coche = E('c-envoyer'); coche.checked = true;
  coche.dispatchEvent(new Event('change', {bubbles:true}));
  var apres = E('fa-relire').textContent.indexOf('tomoko@exemple.pt') >= 0;
  trace((avant && apres) ? 'EMAIL-EXPLICITE' : 'EMAIL-IMPLICITE');
  coche.checked = false; coche.dispatchEvent(new Event('change', {bubbles:true}));

  /* ⚠️ LE TYPE DÉCIDE DU CHAMP AFFICHÉ, ET `hidden` NE SUFFIT PAS À LE CACHER. Une FR est
     déjà payée : lui demander une échéance à trente jours est une question sans réponse.
     On regarde ce qui est VISIBLE, pas ce qui porte l'attribut. */
  /* ⚠️ ENTRÉE AJOUTE UNE LIGNE **ET** Y POSE LE FOCUS. Sans le focus, le geste n'a servi à
     rien : il faut retourner à la souris, ce qu'il était censé éviter. Une facture de trois
     prestations demandait d'aller chercher « + Ligne » entre chaque. */
  var compteChamps = function(){
    return document.querySelectorAll('#fa-corps .fa-cb-input').length; };
  var avantN = compteChamps();
  var mont = document.querySelector('#fa-corps input[inputmode=decimal]');
  mont.focus();
  mont.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
  var apresN = compteChamps();
  trace((apresN === avantN + 1 && document.activeElement === E('cba' + (apresN - 1) + '-input'))
        ? 'ENTREE-NOUVELLE-LIGNE'
        : 'ENTREE-MUETTE ' + avantN + '->' + apresN + ' focus='
          + (document.activeElement && document.activeElement.id));
  /* On retire la ligne vide : la suite du scénario émet, et une ligne sans montant bloquerait. */
  var poubelles = document.querySelectorAll('#fa-corps .fa-btn.icone');
  poubelles[poubelles.length - 1].click();

  var visible = function(id){ var e = E(id); return !!(e && e.offsetParent !== null); };
  trace((visible('f-box-paiement') && !visible('f-box-delai'))
        ? 'FR-SANS-ECHEANCE' : 'FR-AVEC-ECHEANCE');
  E('fa-seg-type').children[1].click();
  trace((!visible('f-box-paiement') && visible('f-box-delai'))
        ? 'FT-SANS-REGLEMENT' : 'FT-AVEC-REGLEMENT');
  E('fa-seg-type').children[0].click();

  var bouton = E('fa-emettre');
  if(bouton.disabled){ trace('PRET-NON ' + E('fa-check').textContent.replace(/\s+/g,' ')); return; }
  trace('PRET-OUI bouton=' + bouton.textContent);

  bouton.click();
  var conf = document.querySelector('#fa-confirme button');
  if(!conf){ trace('CONFIRM-ABSENT'); return; }
  trace('CONFIRM-OK');
  conf.click();

  (function apresEmission(k){
    var zone = E('fa-resultat');
    if((zone.textContent||'').indexOf('Facture émise') < 0 && k < 80)
      return setTimeout(function(){ apresEmission(k+1); }, 20);
    var nom = E('c-nom'); nom.value = 'TOMOKO HIRAOJI';
    nom.dispatchEvent(new Event('input', {bubbles:true}));
    trace(E('fa-emettre').disabled ? 'VERROU-OK' : 'VERROU-ROMPU');
    trace((zone.textContent.indexOf('FR 01P2026/2') >= 0) ? 'NUMERO-OK' : 'NUMERO-MUET');
    trace((zone.innerHTML.indexOf('/api/faturar/378400001/pdf') >= 0) ? 'PDF-OK' : 'PDF-ABSENT');
  })(0);
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
    "planning.html": {
        "reponses": {
            "/api/statut": {"ca": None, "ca_texte": "—", "tickets": None, "moyen_texte": "",
                            "ecarts": 0, "boissons_dues": 0, "caisse_ok": None},
            # Le bouchon ignore la fenêtre demandée : le scénario pose la date lui-même.
            "/api/shifts": {
                "bascule": "2026-10-01",
                "employees": [
                    {"person_id": "p-bar", "name": "Marco Silva", "type": "full_time",
                     "gross_monthly": 1200.0, "hourly_rate": 11.0,
                     "valid_from": "2026-05-01", "valid_to": None, "active": True},
                    {"person_id": "p-ana", "name": "Ana Dias", "type": "extra",
                     "gross_monthly": 0, "hourly_rate": 12.0,
                     "valid_from": "2026-05-01", "valid_to": None, "active": True},
                    # Version ANCIENNE de la même personne : une seule « Ana » doit être offerte.
                    {"person_id": "p-ana", "name": "Ana Dias", "type": "extra",
                     "gross_monthly": 0, "hourly_rate": 9.0,
                     "valid_from": "2026-01-01", "valid_to": "2026-05-01", "active": False},
                ],
                "regles": [
                    {"id": "r1", "person_id": "p-ana", "weekday": 5,
                     "start_time": "09:00:00", "end_time": "17:00:00",
                     "valid_from": "2026-10-01", "valid_to": None, "note": ""},
                ],
                "shifts": [
                    {"id": "s2", "person_id": "p-bar", "day": "2026-10-09",
                     "start_time": "08:00:00", "end_time": "16:00:00", "note": "",
                     "rule_id": None, "annule": False},
                ],
                # Déjà déplié par le serveur — c'est le contrat de la route.
                "services": {
                    "2026-10-09": [
                        {"id": "s2", "rule_id": None, "person_id": "p-bar",
                         "day": "2026-10-09", "start_time": "08:00:00",
                         "end_time": "16:00:00", "source": "ponctuel"},
                    ],
                    "2026-10-10": [
                        {"id": None, "rule_id": "r1", "person_id": "p-ana",
                         "day": "2026-10-10", "start_time": "09:00:00",
                         "end_time": "17:00:00", "source": "regle"},
                    ],
                },
                "couts": {
                    "2026-10-05": {"fixes": 30.43, "personnel": 76.52, "total": 106.95},
                    "2026-10-08": {"fixes": 30.43, "personnel": 76.52, "total": 106.95},
                    "2026-10-09": {"fixes": 30.43, "personnel": 76.52, "total": 106.95},
                    "2026-10-10": {"fixes": 30.43, "personnel": 172.52, "total": 202.95},
                    "2026-10-11": {"fixes": 30.43, "personnel": 76.52, "total": 106.95},
                },
            },
        },
        "attendu": [
            "Planning", "Qui travaille quel jour", "Récurrences",
            # La récurrence est lisible en clair, avec son jour et ses bornes.
            "chaque samedi", "Ana Dias",
            "FERME-DIT", "COUT-AFFICHE", "COUT-DU-SERVEUR",
            "PERMANENT-SANS-PRIX", "EXTRA-AVEC-PRIX", "UNE-SEULE-ANA",
            "LUNDI-JUSTE", "MODALE-OUVRE", "APERCU-EXTRA", "APERCU-PERMANENT",
            "REFUS-HORAIRE",
            # ⚠️ LES TROIS VUES, et la bascule entre elles.
            "VUE-SEMAINE", "VUE-MOIS", "VUE-JOUR", "MOIS-COMPLET", "MOIS-TOTAL",
            # ⚠️ UN SERVICE DE RÈGLE SE DISTINGUE, ET NE SE SUPPRIME PAS — il s'annule.
            "REGLE-MARQUEE", "REGLE-S-ANNULE", "PERSONNE-VERROUILLEE",
            # La récurrence s'édite, et l'aperçu annonce son coût mensuel.
            "REGLE-MODALE", "REGLE-APERCU",
        ],
        "interdit": [
            "FERME-MUET", "COUT-ABSENT", "COUT-RECALCULE",
            "PERMANENT-AVEC-PRIX", "EXTRA-SANS-PRIX", "ANA-EN-DOUBLE",
            "MODALE-FERMEE", "APERCU-MUET", "REFUS-ABSENT", "LUNDI-FAUX",
            "VUE-FIGEE", "MOIS-TRONQUE", "MOIS-SANS-TOTAL",
            "REGLE-NUE", "REGLE-SE-SUPPRIME", "PERSONNE-MODIFIABLE",
            "REGLE-MODALE-ABSENTE", "REGLE-APERCU-MUET",
            "NaN", "undefined", "Invalid Date", "service(s)",
        ],
        "scenario": r"""
(function attendre(n){
  var E = function(i){ return document.getElementById(i); };
  if((!E('pl-vue') || !E('pl-vue').children.length) && n < 80)
    return setTimeout(function(){ attendre(n+1); }, 20);
  var trace = function(t){ var d = document.createElement('div'); d.textContent = t;
                           document.body.appendChild(d); };

  /* ⚠️ `getDay()` DIT 0 POUR DIMANCHE. Sans le décalage, la semaine commençait la veille un
     dimanche sur deux — et le scénario ne le voyait pas, puisqu'il posait LUNDI à la main. */
  var dim = lundiDe(new Date(2026, 9, 11));
  var sam = lundiDe(new Date(2026, 9, 10));
  trace((iso(dim) === '2026-10-05' && iso(sam) === '2026-10-05')
        ? 'LUNDI-JUSTE' : 'LUNDI-FAUX dim=' + iso(dim) + ' sam=' + iso(sam));

  /* ── La semaine ───────────────────────────────────────────────────────── */
  LUNDI = new Date(2026, 9, 5); VUE = 'semaine'; rendre();
  var texte = E('pl-vue').textContent.replace(/\s+/g,' ');
  trace(texte.indexOf('fermé') >= 0 ? 'FERME-DIT' : 'FERME-MUET ' + texte.slice(0,80));
  trace(texte.indexOf('202,95') >= 0 ? 'COUT-AFFICHE' : 'COUT-ABSENT ' + texte.slice(0,120));
  trace((texte.indexOf('172,52') >= 0 && texte.indexOf('106,95') >= 0)
        ? 'COUT-DU-SERVEUR' : 'COUT-RECALCULE');
  trace(E('pl-vue').querySelector('.pl-semaine') ? 'VUE-SEMAINE' : 'VUE-FIGEE semaine');

  var cases = E('pl-vue').querySelectorAll('.pl-jour');
  var samedi = null, vendredi = null;
  for(var i=0;i<cases.length;i++){
    var t = cases[i].textContent;
    if(t.indexOf('202,95') >= 0) samedi = cases[i];
    if(t.indexOf('Marco') >= 0) vendredi = cases[i];
  }
  var marco = vendredi.querySelector('.pl-chip');
  var ana   = samedi.querySelector('.pl-chip');
  trace((marco && marco.textContent.indexOf('€') < 0)
        ? 'PERMANENT-SANS-PRIX' : 'PERMANENT-AVEC-PRIX ' + (marco && marco.textContent));
  trace((ana && ana.textContent.indexOf('96,00') >= 0)
        ? 'EXTRA-AVEC-PRIX' : 'EXTRA-SANS-PRIX ' + (ana && ana.textContent));
  /* ⚠️ UN SERVICE DE RÈGLE SE DISTINGUE À L'ŒIL : le supprimer ne fait pas la même chose. */
  trace(ana.textContent.indexOf('\u21bb') >= 0 ? 'REGLE-MARQUEE' : 'REGLE-NUE ' + ana.textContent);

  /* ── Le mois ──────────────────────────────────────────────────────────── */
  VUE = 'mois'; rendre();
  var mois = E('pl-vue').querySelector('.pl-mois');
  trace(mois ? 'VUE-MOIS' : 'VUE-FIGEE mois');
  /* Octobre 2026 : 31 jours, et la grille commence un lundi. */
  var num = mois.querySelectorAll('.pl-case');
  trace(num.length >= 31 ? 'MOIS-COMPLET' : 'MOIS-TRONQUE n=' + num.length);
  trace(E('pl-total').textContent.indexOf('mois') >= 0
        ? 'MOIS-TOTAL' : 'MOIS-SANS-TOTAL ' + E('pl-total').textContent);

  /* ── Le jour ──────────────────────────────────────────────────────────── */
  VUE = 'jour'; LUNDI = new Date(2026, 9, 10); rendre();
  trace(E('pl-vue').querySelector('.pl-jourseul') ? 'VUE-JOUR' : 'VUE-FIGEE jour');

  /* ── La modale d'un service de règle ──────────────────────────────────── */
  E('pl-vue').querySelector('.pl-chip').click();
  trace(E('pl-fond').classList.contains('ouvert') ? 'MODALE-OUVRE' : 'MODALE-FERMEE');
  trace(E('f-supprimer').textContent.indexOf('Annuler ce jour') >= 0
        ? 'REGLE-S-ANNULE' : 'REGLE-SE-SUPPRIME ' + E('f-supprimer').textContent);
  trace(E('f-personne').disabled
        ? 'PERSONNE-VERROUILLEE' : 'PERSONNE-MODIFIABLE');
  var opts = E('f-personne').options, nAna = 0;
  for(var o=0;o<opts.length;o++) if(opts[o].textContent.indexOf('Ana') >= 0) nAna++;
  trace(nAna === 1 ? 'UNE-SEULE-ANA' : 'ANA-EN-DOUBLE n=' + nAna);

  E('f-personne').disabled = false;
  E('f-personne').value = 'p-ana';
  E('f-personne').dispatchEvent(new Event('input', {bubbles:true}));
  trace(E('f-apercu').textContent.indexOf('96,00') >= 0
        ? 'APERCU-EXTRA' : 'APERCU-MUET extra=' + E('f-apercu').textContent);
  E('f-personne').value = 'p-bar';
  E('f-personne').dispatchEvent(new Event('input', {bubbles:true}));
  trace(E('f-apercu').textContent.indexOf('lissée') >= 0
        ? 'APERCU-PERMANENT' : 'APERCU-MUET perm=' + E('f-apercu').textContent);

  E('f-debut').value = '17:00'; E('f-fin').value = '09:00';
  E('f-ok').click();
  trace(!E('f-refus').hidden ? 'REFUS-HORAIRE' : 'REFUS-ABSENT');
  fermer();

  /* ── La récurrence ────────────────────────────────────────────────────── */
  ouvrirRegle('r1');
  trace(E('pl-fond-regle').classList.contains('ouvert')
        ? 'REGLE-MODALE' : 'REGLE-MODALE-ABSENTE');
  var ap = E('r-apercu').textContent;
  /* 8 h × 12 € = 96 € par service, et l'aperçu annonce aussi le coût mensuel. */
  trace((ap.indexOf('96,00') >= 0 && ap.indexOf('mois') >= 0)
        ? 'REGLE-APERCU' : 'REGLE-APERCU-MUET ' + ap);
  fermerRegle();
})(0);
""",
    },
    "charges.html": {
        "reponses": {
            "/api/statut": {"ca": None, "ca_texte": "—", "tickets": None, "moyen_texte": "",
                            "ecarts": 0, "boissons_dues": 0, "caisse_ok": None},
            "/api/charges": {
                # ⚠️ TROIS ONGLETS DEPUIS LE 04/10 : fixes, variables, personnel. Le bouchon
                # porte une charge de chaque sorte, sinon le troisième onglet n'est jamais rendu.
                # ⚠️ CE QUI MANQUE SE COMPTE EN JOURS. Une facture d'eau couvre 60 jours à
                # cheval sur trois mois civils : « le mois en attente » n'a plus de sens.
                "couverture": {"Électricité": {"jusqua": "2026-08-31", "jours": 34,
                                               "debut_suivant": "2026-09-01"},
                               "Eau": {"jusqua": "2026-09-30", "jours": 4,
                                       "debut_suivant": "2026-10-01"}},
                "aujourdhui": "2026-10-04",
                "mois_courant": "2026-10-01",
                "charges": [{"id": "c1", "name": "Loyer", "amount": 700.0,
                             "frequency": "monthly", "category": "local", "notes": "",
                             "mode": "stable", "mois": None,
                             "active": True, "valid_from": None, "valid_to": None},
                            {"id": "c2", "name": "Électricité", "amount": 77.10,
                             "frequency": "monthly", "category": "Energy & utilities",
                             "notes": "", "mode": "facture", "mois": "2026-08-01",
                             "active": True, "valid_from": "2026-08-01", "valid_to": None},
                            # ⚠️ UNE SECONDE CHARGE VARIABLE, À JOUR CELLE-LÀ. Avec une seule,
                            # « 1 en attente » et « 1 charge » sont indiscernables : le compteur
                            # pouvait compter n'importe lequel des deux et passer quand même.
                            {"id": "c3", "name": "Eau", "amount": 31.40,
                             "frequency": "monthly", "category": "Energy & utilities",
                             "notes": "", "mode": "facture", "mois": "2026-09-01",
                             "active": True, "valid_from": "2026-09-01", "valid_to": None}],
                "employees": [
                    {"id": "e1", "name": "Marco Silva", "type": "full_time",
                     "gross_monthly": 1200.0, "meal_card_daily": 10.20, "tsu_exempt": False,
                     "hourly_rate": None, "hours_week": 40, "days_per_month": 21.25,
                     "notes": "", "active": True, "valid_from": None, "valid_to": None},
                    {"id": "e2", "name": "Ana Dias", "type": "extra",
                     "gross_monthly": 0.0, "meal_card_daily": 0.0, "tsu_exempt": False,
                     "hourly_rate": 12.0, "hours_week": 12, "days_per_month": 4,
                     "notes": "", "active": True, "valid_from": None, "valid_to": None},
                ],
            },
        },
        "attendu": [
            "Loyer", "Marco Silva", "Ana Dias",
            # ⚠️ LE TAUX HORAIRE EST CE QUI CHIFFRE LE PLANNING : sans lui, un extra apparaît
            # au calendrier et sa journée ne coûte rien.
            "TROIS-ONGLETS", "COMPTEUR-DIT-LE-RETARD", "FIXES-SANS-LES-VARIABLES",
            "RESUME-DIT-LA-COMPOSITION", "RESUME-BIEN-NOMME", "ONGLET-BASCULE", "DATES-EN-CLAIR", "RETARD-EN-JOURS", "PAS-DE-LOYER-ICI",
            "PAS-DE-CHAMP-RAPIDE", "COUVERTURE-DITE", "DEUX-DATES",
            "DEBUT-AU-LENDEMAIN", "MENSUEL-ANNONCE", "SAISIE-NON-ECRASEE", "SANS-FIN-RIEN-NEST-ENVOYE", "REFUS-DIT-LES-DATES",
            "PERIODE-ENVOYEE",
            "VARIABLES-HORS-DES-FIXES", "COLONNES-ORDONNEES", "UN-POINT-SANS-GRAPHE",
            "GRAPHE-ANNONCE", "FENETRE-OUVRE", "CORRECTION-ANNONCEE",
            "CHAMP-TAUX", "TAUX-REPRIS", "OUVRIR-NE-MODIFIE-PAS",
            "TAUX-ENVOYE", "EXTRA-SANS-CARTE-REPAS", "EXTRA-SANS-MENSUEL-ACCEPTE",
            "CARTE-REPAS-MASQUEE", "REFUS-LISIBLE",
            "EXTRA-SANS-TAUX-REFUSE", "REFUS-DIT-QUOI",
            # ⚠️ ET LA FICHE D'UN PERMANENT S'OUVRE APRÈS CELLE D'UN EXTRA. La branche « extra »
            # remplaçait l'aperçu et détruisait les éléments que l'autre remplissait : la
            # seconde ouverture levait, en silence.
            "PERMANENT-APRES-EXTRA",
            "EXTRA-ANNONCE-LE-SERVICE", "EXTRA-SANS-TAUX-AVERTIT",
            "PERMANENT-TAUX-INDICATIF",
            # Changer un taux est un changement de coût : date d'effet et motif obligatoires.
            "TAUX-EXIGE-UN-MOTIF", "APERCU-PAR-SERVICE",
        ],
        "interdit": [
            "ONGLET-MANQUANT", "COMPTEUR-MUET", "FIXES-MELANGEES", "ONGLET-FIGE",
            "RESUME-TROMPEUR", "RESUME-MAL-NOMME", "poste(s)", "employee(s)",
            "DATES-EN-CODE", "RETARD-EN-MOIS", "LOYER-EN-DOUBLE", "CHAMP-RAPIDE-SURVIVANT",
            "COUVERTURE-TUE", "UNE-SEULE-DATE", "DEBUT-AILLEURS", "MENSUEL-TU", "SAISIE-ECRASEE", "SANS-FIN-ENVOYE-QUAND-MEME", "REFUS-DATES-MUET", "PERIODE-PERDUE",
            # ⚠️ PAS « GRAPHE-SUR-UN-POINT » : c'était une sous-chaîne du marqueur
            # attendu, donc le contrôle rougissait sur un rendu correct. Deuxième
            # fois de la session — un marqueur interdit ne doit jamais être contenu
            # dans celui qu'on espère.
            "COLONNES-AU-HASARD", "UN-POINT-AVEC-GRAPHE", "GRAPHE-MUET", "FENETRE-FERMEE",
            "CORRECTION-SILENCIEUSE", "VARIABLES-DANS-LES-FIXES",
            "CHAMP-ABSENT", "TAUX-PERDU", "OUVRIR-RECLAME-UN-MOTIF",
            "TAUX-PERDU-A-LENVOI", "EXTRA-AVEC-CARTE-REPAS", "EXTRA-REFUSE-SANS-MENSUEL",
            "CARTE-REPAS-VISIBLE", "REFUS-UNDEFINED",
            "EXTRA-SANS-TAUX-ENREGISTRE", "REFUS-MUET", "EXTRA-MUET", "EXTRA-SANS-TAUX-SILENCIEUX",
            "PERMANENT-TAUX-COMPTE", "TAUX-SANS-CEREMONIE", "PERMANENT-APRES-EXTRA-CASSE", "APERCU-TROMPEUR",
            "NaN", "undefined", "Invalid Date",
        ],
        "scenario": r"""
(function attendre(n){
  var E = function(i){ return document.getElementById(i); };
  if((!E('emp-cards') || !E('emp-cards').children.length) && n < 80)
    return setTimeout(function(){ attendre(n+1); }, 20);
  var trace = function(t){ var d = document.createElement('div'); d.textContent = t;
                           document.body.appendChild(d); };

  /* ══ LES TROIS ONGLETS ════════════════════════════════════════════════════════════════
   * ⚠️ UNE FACTURE EN ATTENTE DOIT SE VOIR SANS NAVIGUER. Dans un onglet séparé elle devient
   * invisible depuis l'onglet par défaut : le compteur de l'onglet est ce qui remplace cette
   * visibilité, et c'est le seul endroit de l'écran qui porte une couleur d'alerte. */
  trace(E('tab-variables') ? 'TROIS-ONGLETS' : 'ONGLET-MANQUANT');
  trace(E('badge-variables').textContent === '1'
        ? 'COMPTEUR-DIT-LE-RETARD' : 'COMPTEUR-MUET ' + E('badge-variables').textContent);
  trace(E('badge-charges').textContent === '1'
        ? 'FIXES-SANS-LES-VARIABLES' : 'FIXES-MELANGEES ' + E('badge-charges').textContent);
  /* ⚠️ LA CARTE DU HAUT ADDITIONNE TOUT, et ne doit donc plus s'appeler « Charges fixes » :
     l'écran affichait « Charges fixes · 3 postes » au-dessus d'un onglet « Charges fixes 1 ».
     Le montant est juste ; c'est le nom qui mentait. */
  var ks = E('sum-fixes-sub').textContent.replace(/\s+/g,' ');
  trace((ks.indexOf('3 postes') >= 0 && ks.indexOf('2 sur facture') >= 0)
        ? 'RESUME-DIT-LA-COMPOSITION' : 'RESUME-TROMPEUR ' + ks);
  /* Et le NOM de la carte doit avoir suivi : « Charges fixes » au-dessus d'un total qui
     contient l'électricité, c'est le libellé qui ment, pas le montant. */
  var titreKpi = E('sum-fixes').parentElement.querySelector('.db-l').textContent.trim();
  trace(titreKpi === 'Charges' ? 'RESUME-BIEN-NOMME' : 'RESUME-MAL-NOMME ' + titreKpi);

  switchTab('variables');
  var vv = E('view-variables');
  trace(vv.style.display !== 'none' ? 'ONGLET-BASCULE' : 'ONGLET-FIGE');
  var tv = vv.textContent.replace(/\s+/g,' ');
  /* Les dates s'affichent en toutes lettres, pas en 2026-08-31. */
  trace(tv.indexOf('2026-08') < 0 && tv.indexOf('août 2026') >= 0
        ? 'DATES-EN-CLAIR' : 'DATES-EN-CODE ' + tv.slice(0,110));
  /* ⚠️ « EN RETARD » SE DIT EN JOURS. 34 jours depuis la dernière facture d'électricité :
     dire « 1 mois » arrondirait une mesure qu'on a exacte. */
  trace(tv.indexOf('34 jours estimés') >= 0
        ? 'RETARD-EN-JOURS' : 'RETARD-EN-MOIS ' + tv.slice(0,110));
  trace(tv.indexOf('Loyer') < 0 ? 'PAS-DE-LOYER-ICI' : 'LOYER-EN-DOUBLE');
  /* ⚠️ ET L'INVERSE AUSSI : une charge variable ne doit pas rester dans le tableau des fixes.
     L'y laisser la montrerait deux fois, avec deux gestes différents pour la même ligne. */
  var tf = E('view-charges').textContent.replace(/\s+/g,' ');
  trace(tf.indexOf('Électricité') < 0 && tf.indexOf('Loyer') >= 0
        ? 'VARIABLES-HORS-DES-FIXES' : 'VARIABLES-DANS-LES-FIXES ' + tf.slice(0,90));
  /* ⚠️ LE CHAMP RAPIDE « UN MOIS, UN MONTANT » A DISPARU, et c'est voulu : il ne pouvait pas
     deviner la fin de période, et sans elle il n'y a pas de taux journalier. Ce qui reste à
     sa place dit jusqu'où on mesure. */
  trace(!E('fact-Électricité') ? 'PAS-DE-CHAMP-RAPIDE' : 'CHAMP-RAPIDE-SURVIVANT');
  trace(tv.indexOf('Mesuré jusqu') >= 0 ? 'COUVERTURE-DITE' : 'COUVERTURE-TUE ' + tv.slice(0,110));

  /* ⚠️ MOINS DE DEUX FACTURES NE FONT PAS UNE ÉVOLUTION. Le bouchon n'en donne qu'une par
     charge : une barre unique occuperait toute la largeur et se lirait comme un maximum, alors
     qu'elle n'est comparée à rien. Même règle que `miniCourbe`. */
  /* ⚠️ L'ORDRE DES COLONNES NE SUIT PAS LA BASE. Le bouchon renvoie Électricité avant Eau ;
     à l'écran, Eau passe devant — sinon deux chargements donnent deux dispositions. */
  var titres = [...vv.querySelectorAll('.var-nom')].map(function(t){ return t.textContent.trim(); });
  trace(JSON.stringify(titres) === '["Eau","Électricité"]'
        ? 'COLONNES-ORDONNEES' : 'COLONNES-AU-HASARD ' + JSON.stringify(titres));

  trace(vv.querySelectorAll('.var-barres').length === 0
        ? 'UN-POINT-SANS-GRAPHE' : 'UN-POINT-AVEC-GRAPHE');
  trace(tv.indexOf('deuxième facture') >= 0 ? 'GRAPHE-ANNONCE' : 'GRAPHE-MUET');

  /* La fenêtre « + Facture » : choisir un mois, et corriger par le même chemin. */
  ouvrirFacture('Électricité');
  trace(E('fact-modal').classList.contains('open') ? 'FENETRE-OUVRE' : 'FENETRE-FERMEE');
  /* ⚠️ DEUX DATES, PAS UN MOIS. Un sélecteur de mois ne peut pas décrire une facture du
     21/07 au 18/09 — et la lire comme un montant mensuel gonflait l'eau de 86,78 €/mois. */
  trace((E('fact-mois').type === 'date' && E('fact-fin') && E('fact-fin').type === 'date')
        ? 'DEUX-DATES' : 'UNE-SEULE-DATE');
  /* ⚠️ LE DÉBUT PROPOSÉ EST LE LENDEMAIN DE LA DERNIÈRE FACTURE : c'est ce que fait le
     fournisseur, et c'est ce qui garantit qu'aucun jour ne reste non facturé. */
  trace(E('fact-mois').value === '2026-09-01'
        ? 'DEBUT-AU-LENDEMAIN' : 'DEBUT-AILLEURS ' + E('fact-mois').value);
  /* ⚠️ L'ÉCRAN CHIFFRE LE COÛT MENSUEL AVANT D'ENREGISTRER. C'est lui qui entrera dans le
     point mort, et c'est en le voyant qu'on sait si on s'est trompé de case. */
  E('fact-fin').value = '2026-10-30';
  E('fact-fin').dispatchEvent(new Event('change', {bubbles:true}));
  E('fact-montant').value = '176.14';
  E('fact-montant').dispatchEvent(new Event('input', {bubbles:true}));
  var ap = E('fact-avis').textContent.replace(/\s+/g,' ');
  trace((ap.indexOf('60 jours') >= 0 && ap.indexOf('89.3') >= 0)
        ? 'MENSUEL-ANNONCE' : 'MENSUEL-TU ' + ap.slice(0,80));
  /* ⚠️ RESAISIR UNE PÉRIODE DÉJÀ CONNUE N'EST PAS UNE ERREUR : la fenêtre le dit et change
     de verbe. La facture du bouchon commence le 1er août. */
  /* ⚠️ UNE DATE TAPÉE N'EST PAS RÉÉCRITE. Le rythme propose tant qu'on n'a rien saisi ; dès
     qu'on a corrigé la fin à la main, elle est à nous. Une date qu'on vient de taper et que
     l'écran remplace tout seul, c'est la saisie qu'on cesse de relire. */
  E('fact-mois').value = '2026-09-02';
  E('fact-mois').dispatchEvent(new Event('change', {bubbles:true}));
  trace(E('fact-fin').value === '2026-10-30'
        ? 'SAISIE-NON-ECRASEE' : 'SAISIE-ECRASEE ' + E('fact-fin').value);

  E('fact-mois').value = '2026-08-01';
  E('fact-mois').dispatchEvent(new Event('change', {bubbles:true}));
  var av = E('fact-avis').textContent.replace(/\s+/g,' ');
  trace((av.indexOf('commence déjà') >= 0 && E('fact-ok').textContent === 'Corriger')
        ? 'CORRECTION-ANNONCEE' : 'CORRECTION-SILENCIEUSE ' + av.slice(0,70));

  /* ⚠️ LA FIN DE PÉRIODE DOIT PARTIR DANS LA REQUÊTE. Un champ ajouté à l'écran et absent du
     corps envoyé est décoratif : la facture s'enregistrerait sans sa fin, donc sans taux
     journalier, et on retomberait sur « une facture = un mois ». C'est exactement la faute du
     taux horaire, deux écrans plus loin, qui avait passé une relecture. */
  var envoye = null;
  var vraiFetch = window.fetch;
  window.fetch = function(u, o){
    if(String(u).indexOf('/api/charges/facture') === 0 && o && o.body) envoye = JSON.parse(o.body);
    return vraiFetch(u, o);
  };
  /* ⚠️ SANS LA FIN, ON N'ENVOIE RIEN. Le champ portait une étoile et rien ne l'imposait :
     le serveur aurait relu le montant comme un mensuel — l'erreur d'un facteur deux qu'on
     venait de corriger, en silence. L'écran doit s'arrêter avant, et dire pourquoi. */
  E('fact-mois').value = '2026-09-01';
  E('fact-fin').value = '';
  E('fact-montant').value = '176.14';
  validerFacture();
  trace(envoye === null ? 'SANS-FIN-RIEN-NEST-ENVOYE' : 'SANS-FIN-ENVOYE-QUAND-MEME');
  trace(E('toast').textContent.indexOf('deux dates') >= 0
        ? 'REFUS-DIT-LES-DATES' : 'REFUS-DATES-MUET ' + E('toast').textContent.slice(0,50));

  E('fact-fin').value = '2026-10-30';
  validerFacture();
  window.fetch = vraiFetch;
  trace((envoye && envoye.fin === '2026-10-30' && envoye.mois === '2026-09-01')
        ? 'PERIODE-ENVOYEE' : 'PERIODE-PERDUE ' + JSON.stringify(envoye));
  fermerFacture();
  switchTab('personnel');

  trace(E('emp-rate') ? 'CHAMP-TAUX' : 'CHAMP-ABSENT');

  /* La fiche d'Ana porte 12 €/h : ouvrir sa fiche doit le reprendre. */
  editEmployee('e2');
  trace(E('emp-rate').value === '12' ? 'TAUX-REPRIS' : 'TAUX-PERDU v=' + E('emp-rate').value);

  /* ⚠️ OUVRIR UNE FICHE N'EST PAS LA MODIFIER. `resetVer` oubliait `hourly_rate` : l'écran
     croyait à un changement dès l'ouverture, ouvrait le bloc « date d'effet » et réclamait un
     motif pour n'avoir rien touché. Et mon marqueur suivant passait POUR CETTE RAISON — le
     bloc était déjà ouvert avant que je change quoi que ce soit. Un test qui ne peut pas
     échouer ne garde rien. */
  trace(E('emp-ver').hidden
        ? 'OUVRIR-NE-MODIFIE-PAS'
        : 'OUVRIR-RECLAME-UN-MOTIF ' + E('emp-apercu').textContent.slice(0,80));

  /* ⚠️ L'ÉCRAN DOIT DIRE CE QUE LE TAUX PRODUIT, pas seulement l'accepter. */
  var ap = E('emp-preview').textContent.replace(/\s+/g,' ');
  /* Cette page formate en en-IE : « €96.00 », pas « 96,00 ». Mon premier marqueur exigeait
     le format de /faturar et rougissait sur un affichage parfaitement correct. */
  trace(ap.indexOf('96.00') >= 0
        ? 'EXTRA-ANNONCE-LE-SERVICE' : 'EXTRA-MUET ' + ap.slice(0,90));

  /* Un extra SANS taux doit être averti : ses journées ne coûteront rien. */
  E('emp-rate').value = '';
  E('emp-rate').dispatchEvent(new Event('input', {bubbles:true}));
  var ind = E('emp-rate-hint').textContent;
  trace(ind.indexOf('ne coûtent rien') >= 0
        ? 'EXTRA-SANS-TAUX-AVERTIT' : 'EXTRA-SANS-TAUX-SILENCIEUX ' + ind);

  /* ⚠️ POUR UN PERMANENT LE TAUX N'ENTRE DANS AUCUN CALCUL, et le taire serait pire. */
  editEmployee('e1');
  var pv = E('emp-preview').textContent.replace(/\s+/g,' ');
  trace(pv.indexOf('Total / month') >= 0
        ? 'PERMANENT-APRES-EXTRA' : 'PERMANENT-APRES-EXTRA-CASSE ' + pv.slice(0,80));
  E('emp-rate').value = '11';
  E('emp-rate').dispatchEvent(new Event('input', {bubbles:true}));
  var ind2 = E('emp-rate-hint').textContent;
  trace(ind2.indexOf('aucun calcul') >= 0
        ? 'PERMANENT-TAUX-INDICATIF' : 'PERMANENT-TAUX-COMPTE ' + ind2);

  /* ⚠️ ENREGISTRER DOIT ENVOYER LE TAUX. Il manquait au corps de la requête : saisir un taux
     ne l'envoyait nulle part, la fiche s'enregistrait sans lui, et les services du planning
     restaient à zéro. Le champ était décoratif. */
  var envoye = null;
  var vraiFetch = window.fetch;
  window.fetch = function(u, o){
    if(String(u).indexOf('/api/employees') === 0 && o && o.body) envoye = JSON.parse(o.body);
    return vraiFetch(u, o);
  };
  openEmpModal();
  E('emp-name').value = 'Carla';
  E('emp-type').value = 'extra';
  E('emp-type').dispatchEvent(new Event('change', {bubbles:true}));
  E('emp-rate').value = '14';
  E('emp-rate').dispatchEvent(new Event('input', {bubbles:true}));
  saveEmployee();
  trace((envoye && envoye.hourly_rate === 14)
        ? 'TAUX-ENVOYE' : 'TAUX-PERDU-A-LENVOI ' + JSON.stringify(envoye));
  /* ⚠️ UN EXTRA N'A PAS DE CARTE REPAS : lui en poser une invente une charge. */
  trace((envoye && envoye.meal_card_daily === 0)
        ? 'EXTRA-SANS-CARTE-REPAS' : 'EXTRA-AVEC-CARTE-REPAS ' + (envoye && envoye.meal_card_daily));
  /* ⚠️ ET SON FORFAIT MENSUEL N'EST PLUS OBLIGATOIRE : le laisser vide refusait une fiche
     parfaitement remplie, avec « Nom et salaire requis » pour seul message. */
  trace((envoye && envoye.name === 'Carla')
        ? 'EXTRA-SANS-MENSUEL-ACCEPTE' : 'EXTRA-REFUSE-SANS-MENSUEL');
  /* La carte repas est masquée, pas seulement ignorée. */
  trace(E('emp-meal-wrap').style.display === 'none'
        ? 'CARTE-REPAS-MASQUEE' : 'CARTE-REPAS-VISIBLE');
  /* ⚠️ UN REFUS SANS MESSAGE NE DOIT PAS AFFICHER « undefined ». Le bouchon répond {} : c'est
     exactement le cas d'un serveur qui refuse sans expliquer, et l'écran disait « Error:
     undefined » — ce qui se lit comme un bug du navigateur, pas comme un refus. */
  trace(E('toast').textContent.indexOf('undefined') < 0
        ? 'REFUS-LISIBLE' : 'REFUS-UNDEFINED ' + E('toast').textContent);

  /* ⚠️ UN EXTRA SANS TAUX NE DOIT PAS PASSER — et le message doit dire QUOI manque. Sa fiche
     s'enregistrerait sans rien pour chiffrer ses services : il apparaîtrait au planning et sa
     journée coûterait zéro, en silence. */
  envoye = null;
  openEmpModal();
  E('emp-name').value = 'Dora';
  E('emp-type').value = 'extra';
  E('emp-type').dispatchEvent(new Event('change', {bubbles:true}));
  E('emp-rate').value = '';
  saveEmployee();
  trace(envoye === null ? 'EXTRA-SANS-TAUX-REFUSE'
        : 'EXTRA-SANS-TAUX-ENREGISTRE ' + JSON.stringify(envoye));
  trace(E('toast').textContent.indexOf('taux horaire') >= 0
        ? 'REFUS-DIT-QUOI' : 'REFUS-MUET ' + E('toast').textContent);
  window.fetch = vraiFetch;

  /* Changer un taux ouvre le bloc date d'effet + motif, comme une augmentation. */
  editEmployee('e2');
  E('emp-rate').value = '15';
  E('emp-rate').dispatchEvent(new Event('input', {bubbles:true}));
  var bloc = E('emp-ver');
  trace((bloc && !bloc.hidden)
        ? 'TAUX-EXIGE-UN-MOTIF' : 'TAUX-SANS-CEREMONIE');

  /* ⚠️ ET L'APERÇU DOIT DIRE CE QUI CHANGE VRAIMENT. Le coût d'un extra ne vient plus de son
     forfait mensuel : montrer « 0,00 € → 0,00 € » sur une hausse de taux dirait que rien ne
     bouge, au moment précis où l'on demande un motif pour un changement de coût. */
  var ap2 = E('emp-apercu').textContent.replace(/\s+/g,' ');
  trace(ap2.indexOf('service') >= 0
        ? 'APERCU-PAR-SERVICE' : 'APERCU-TROMPEUR ' + ap2.slice(0,110));
})(0);
""",
    },
    "index.html": {
        "reponses": {
            "/api/statut": {"ca": None, "ca_texte": "—", "tickets": None, "moyen_texte": "",
                            "ecarts": 0, "boissons_dues": 0, "caisse_ok": None},
            # ⚠️ UNE CHARGE UTILE RÉALISTE, PAS UN DICTIONNAIRE VIDE. Avec `{}`, le rendu
            # du tableau de bord part en vrille et le harnais ne voit plus que ses propres
            # dégâts — il ne garde alors plus rien de la page.
            "/api/data": {
                "preset": "custom", "period_label": "1 sept – 30 sept",
                "from_date": "2026-09-01", "to_date": "2026-09-30", "n_days": 30,
                "periode": {"jours_ouverts": 22, "jours_calendaires": 30, "en_cours": False},
                "is_single_day": False,
                "has_items": True, "date": "2026-09-30",
                "updated_at": "2026-09-30 18:00:00", "is_today": False,
                "comp_label": "vs les 30 jours précédents", "comp_sofar": False,
                "today": {"ca": 12400.0, "ca_ht": 11000.0, "nb": 2100, "ticket": 5.90,
                          "ticket_ht": 5.24},
                "yesterday": {"ca": 11000.0, "ca_ht": 9800.0, "nb": 1950, "ticket": 5.64,
                              "ticket_ht": 5.03},
                "seuil": 120,
                "daily": [{"date": f"2026-09-{j:02d}", "ca_ttc": 400 + j, "ca_ht": 360 + j,
                           "nb": 70} for j in (1, 3, 4, 5, 7)],
                "daily_comp": [{"date": f"2026-08-{j:02d}", "ca_ttc": 380 + j,
                                "ca_ht": 340 + j, "nb": 66} for j in (3, 4, 6, 7, 10)],
                "payments": [], "tva": [], "week": [], "weekdays": [], "median": 5.40,
                "upsell": {}, "ticket_dist": [], "recent": [],
                "today_lastweek": None, "wow": None, "warnings": [],
                "economics": {
                    "ca_ttc": 12400.0, "ca_ht": 11000.0, "open_days": 22,
                    "cogs_ht": 3200.0, "cogs_coverage_pct": 97.0,
                    "marge_brute_ht": 7800.0, "marge_brute_ht_pct": 70.9,
                    "marge_hors_ventes_ht": 0.0, "marge_totale_ht": 7800.0,
                    "marge_is_estimated": False,
                    "cout_fixe_periode": 1200.0, "cout_perso_periode": 2400.0,
                    "cout_total_periode": 3600.0, "cout_jour": 163.6,
                    "cout_fixe_jour": 1200.0, "cout_perso_jour": 2400.0,
                    "cout_total_jour": 3600.0, "amort_jour": 596.0,
                    "ebitda_ht": 4200.0,
                    "seuil_ca_ttc": 5740.0, "seuil_ca_ttc_jour": 260.9,
                    "seuil_ca_ttc_par_jour": {}, "seuil_ca_ht": 5080.0,
                    "manque_seuil": 0.0, "pct_seuil": 216,
                    "charges_estimees": ["Électricité"],
                    "charges_source": "supabase", "seuil_margin_src": "reelle",
                    "seuil_tva_src": "mesure", "seuil_tva_pct": 13.0,
                    "seuil_margin_pct": 70.9, "excludes_today": False,
                    "periode": {"jours_ouverts": 22, "jours_calendaires": 30,
                                "en_cours": False},
                    "commissions_ht": 0.0, "popup_commission_ht": 0.0,
                },
            },
            "/api/popup-flag": {},
            "/api/returning": {
                "enabled": True, "empty": False,
                "period": {"visits": 142, "returning": 58, "returning_pct": 40.8,
                           "cards": 97, "known_cards": 31, "new_cards": 66,
                           "regulars": 9, "regulars_visit_pct": 18.3},
                "all": {"visits": 1200, "cards": 640, "repeat_cards": 220,
                        "repeat_cards_pct": 34.4},
            },
        },
        "attendu": [
            "Clients qui reviennent", "Analyse complète",
            # ⚠️ LE BLOC SUIT LA PÉRIODE AFFICHÉE. Les anciennes tuiles portaient toujours
            # l'historique complet : changer de période ne les faisait pas bouger d'un chiffre.
            "FENETRE-SUIVIE", "BLOC-VISIBLE",
            "PART-AFFICHEE", "CARTES-NEUVES-ET-CONNUES", "HABITUES",
            # ⚠️ ET CE QUE LE CHIFFRE NE DIT PAS EST ÉCRIT À CÔTÉ.
            "ESPECES-DITES",
            # Aucun passage ≠ 0 % de retours.
            "VIDE-SE-TAIT",
            # ⚠️ LE GRAPHIQUE DE LA CARTE PRINCIPALE A ÉTÉ RETIRÉ, et la carte se referme.
            "PAS-DE-GRAPHE", "PAS-DE-LEGENDE", "TROIS-CHIFFRES", "CARTE-REFERMEE",
            "MINIS-INTACTES",
            # ⚠️ ET LE POINT MORT DIT QUAND IL SUPPOSE. Octobre tourne sur la facture
            # d'électricité de septembre : le chiffre reste le meilleur disponible, mais
            # l'écran le présentait comme mesuré.
            "SEUIL-QUALIFIE", "FACTURE-NOMMEE", "LIEN-VERS-LA-SAISIE",
        ],
        "interdit": [
            "FENETRE-FIGEE", "BLOC-CACHE", "PART-ABSENTE", "CARTES-MUETTES", "HABITUES-MUETS",
            "ESPECES-TUES", "VIDE-AFFIRME-ZERO",
            "GRAPHE-REVENU", "LEGENDE-REVENUE", "CHIFFRES-PERDUS", "CARTE-TROUEE",
            "MINIS-PERDUES",
            "SEUIL-SANS-RESERVE", "FACTURE-TUE", "SAISIE-SANS-LIEN",
            "NaN", "undefined", "Invalid Date", "passage(s)",
        ],
        "scenario": r"""
(function attendre(n){
  var E = function(i){ return document.getElementById(i); };
  if(!E('ret-bloc') && n < 80) return setTimeout(function(){ attendre(n+1); }, 20);
  var trace = function(t){ var d = document.createElement('div'); d.textContent = t;
                           document.body.appendChild(d); };

  var vues = [];
  var vrai = window.fetch;
  window.fetch = function(u, o){ vues.push(String(u)); return vrai(u, o); };

  /* ⚠️ ON NE PEUT PAS APPELER `chargerRetours` SOI-MÊME. Mon premier scénario le faisait, et
     ne prouvait donc rien de ce qui est demandé : que le bloc suive la période AFFICHÉE.
     Changer la fenêtre dans `render` passait inaperçu. On repasse par `render`, qui est le
     chemin réel. */
  render(window._lastData);
  setTimeout(function(){
    var url = vues.join(' ');
    trace((url.indexOf('2026-09-01') >= 0 && url.indexOf('2026-09-30') >= 0)
          ? 'FENETRE-SUIVIE' : 'FENETRE-FIGEE ' + url);
    /* Le bloc doit être VISIBLE, pas seulement présent dans le document. */
    trace(E('ret-bloc').style.display !== 'none'
          ? 'BLOC-VISIBLE' : 'BLOC-CACHE');

    trace(E('ret-pct').textContent.indexOf('40.8') >= 0
          ? 'PART-AFFICHEE' : 'PART-ABSENTE ' + E('ret-pct').textContent);
    var sc = E('ret-cartes-sub').textContent;
    trace((sc.indexOf('66 nouvelles') >= 0 && sc.indexOf('31 déjà connues') >= 0)
          ? 'CARTES-NEUVES-ET-CONNUES' : 'CARTES-MUETTES ' + sc);
    trace(E('ret-reg').textContent === '9'
          ? 'HABITUES' : 'HABITUES-MUETS ' + E('ret-reg').textContent);
    trace(E('ret-note').textContent.indexOf('espèces') >= 0
          ? 'ESPECES-DITES' : 'ESPECES-TUES ' + E('ret-note').textContent);

    /* ⚠️ AUCUN PASSAGE N'EST PAS « 0 % DE RETOURS ». Sur une journée sans paiement par carte,
       un 0 % affirmerait que personne n'est revenu — alors qu'on n'a vu personne. */
    rendreRetours({enabled:true, empty:false, period:{visits:0, returning:0,
      returning_pct:null, cards:0, known_cards:0, new_cards:0, regulars:0,
      regulars_visit_pct:null}});
    /* ⚠️ « — » SEUL NE PROUVE RIEN : le chemin ordinaire affiche aussi « — » quand le
       pourcentage est nul. Ce qui distingue, c'est de DIRE pourquoi. */
    trace((E('ret-pct').textContent === '\u2014'
           && E('ret-pct-sub').textContent.indexOf('aucun paiement par carte') >= 0
           && E('ret-cartes').textContent === '\u2014')
          ? 'VIDE-SE-TAIT'
          : 'VIDE-AFFIRME-ZERO ' + E('ret-pct').textContent + ' / '
            + E('ret-pct-sub').textContent);
    window.fetch = vrai;

    /* ══ PLUS DE GRAPHIQUE DANS LA CARTE PRINCIPALE ══════════════════════════════════════
     *
     * ⚠️ RETIRÉ LE 04/10/2026, À LA DEMANDE DE QUENTIN. Le canvas et sa légende sont partis
     * avec `renderCourbe` : ce qui est gardé ici, c'est qu'ils ne reviennent pas par un
     * copier-coller, et que la carte se referme sous ses trois chiffres sans vide.
     */
    trace(!document.getElementById('chart-daily')
          ? 'PAS-DE-GRAPHE' : 'GRAPHE-REVENU');
    trace(!document.getElementById('db-legende-comp')
          ? 'PAS-DE-LEGENDE' : 'LEGENDE-REVENUE');
    /* Les trois chiffres, eux, sont bien là. */
    trace((E('db-ca').textContent.indexOf('12,400') >= 0
           && E('db-res').textContent.indexOf('4,200') >= 0
           && E('db-seuil').textContent.indexOf('5,740') >= 0)
          ? 'TROIS-CHIFFRES' : 'CHIFFRES-PERDUS ' + E('db-ca').textContent);
    /* ⚠️ ET LA CARTE SE REFERME SOUS EUX. Un reste de hauteur se verrait ici : on mesure le
       rectangle, on ne le relit pas. */
    var carte = E('db-ca').closest('.db-card');
    var bas = E('db-seuil-sub').getBoundingClientRect().bottom;
    var filsBas = carte.getBoundingClientRect().bottom;
    trace((filsBas - bas) < 60
          ? 'CARTE-REFERMEE' : 'CARTE-TROUEE ' + Math.round(filsBas - bas) + 'px');
    /* Les mini-courbes des autres cartes n'ont pas été emportées. */
    trace(document.getElementById('mini-tickets') ? 'MINIS-INTACTES' : 'MINIS-PERDUES');

  /* ⚠️ LE POINT MORT DIT QUAND IL SUPPOSE. Le bouchon porte une facture d'électricité non
     arrivée : le seuil doit être qualifié à côté du chiffre, la charge nommée sous la carte,
     et le geste accessible — un avertissement sans chemin de correction fait relire deux fois
     et agir zéro. */
  var sub = document.getElementById('db-seuil-sub').textContent;
  trace(sub.indexOf('estimé') >= 0 ? 'SEUIL-QUALIFIE' : 'SEUIL-SANS-RESERVE ' + sub);
  var nt = document.getElementById('db-note');
  trace((nt.style.display !== 'none' && nt.textContent.indexOf('Électricité') >= 0)
        ? 'FACTURE-NOMMEE' : 'FACTURE-TUE ' + nt.textContent.slice(0, 70));
  trace(nt.querySelector('a[href="/charges"]') ? 'LIEN-VERS-LA-SAISIE' : 'SAISIE-SANS-LIEN');
  }, 150);
})(0);
""",
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


# ⚠️ TROIS FACTURES EPAL TELLES QUE LA ROUTE LES ÉCRIT. `valid_to` est le début de la SUIVANTE,
# pas la fin de la période : entre le 21 et le 31 juillet, personne ne facture, mais la ligne de
# juillet reste en vigueur et porte ces jours à son taux. Fermer au dernier jour facturé
# laisserait l'eau absente du point mort pendant onze jours — un trou ment plus qu'une
# estimation annoncée. Le graphe, lui, montre le trou de FACTURATION.
def _epal(i, deb, fin, montant, jusqua):
    return {"id": f"w{i}", "name": "Eau", "amount": montant, "frequency": "monthly",
            "category": "Energy & utilities", "notes": "", "mode": "facture",
            "mois": deb[:7] + "-01", "periode_debut": deb, "periode_fin": fin,
            "active": jusqua is None, "valid_from": deb, "valid_to": jusqua}


EPAL_1 = _epal(1, "2026-03-23", "2026-05-21", 160.0, "2026-05-22")
EPAL_2 = _epal(2, "2026-05-22", "2026-07-20", 170.0, "2026-08-01")
EPAL_3 = _epal(3, "2026-08-01", "2026-09-29", 220.0, None)


LIGNE_JUIN = {"id": "e06", "name": "Électricité", "amount": 70.0, "frequency": "monthly", "category": "Energy & utilities", "notes": "", "mode": "facture", "mois": "2026-06-01", "active": True, "valid_from": "2026-06-01", "valid_to": None}
LIGNE_AOUT = {"id": "e08", "name": "Électricité", "amount": 75.0, "frequency": "monthly", "category": "Energy & utilities", "notes": "", "mode": "facture", "mois": "2026-08-01", "active": True, "valid_from": "2026-08-01", "valid_to": None}
LIGNE_SEPT = {"id": "e09", "name": "Électricité", "amount": 120.0, "frequency": "monthly", "category": "Energy & utilities", "notes": "", "mode": "facture", "mois": "2026-09-01", "active": True, "valid_from": "2026-09-01", "valid_to": None}


def _rendre(nom, reponses, tmp_path, scenario=None):
    env = Environment(loader=FileSystemLoader(os.path.join(RACINE, "templates")))
    html = env.get_template(nom).render(v="test", role="admin")
    # ⚠️ LES CHEMINS ABSOLUS NE RÉSOLVENT PAS EN `file://`. Tant qu'on ne les réécrivait pas,
    # `/static/dashboard.js` n'était jamais chargé : le gabarit du tableau de bord s'affichait
    # sans UNE SEULE de ses fonctions, et le harnais ne voyait qu'une coquille. Les pages déjà
    # couvertes portent leur script en ligne, ce qui a masqué le trou — jusqu'à index.html.
    html = re.sub(r'(href|src)="/static/',
                  lambda m: f'{m.group(1)}="{os.path.join(RACINE, "static")}/', html)

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


# ══ LA PAGE NE DOIT GLISSER À AUCUNE LARGEUR ════════════════════════════════════════════════
#
# ⚠️ CE CONTRÔLE EXISTE PARCE QUE `1fr` NE DESCEND JAMAIS SOUS SON CONTENU. `1fr` vaut
# `minmax(auto, 1fr)`, et `auto` a pour plancher la largeur minimale du contenu : trois cartes
# dont les sous-titres refusent de se réduire additionnent leurs planchers, et la grille dépasse
# son conteneur. Mesuré le 04/10/2026 : à 1024 px — un iPad en PAYSAGE — le tableau de bord
# s'étalait sur 1111 px et la page entière glissait sous le doigt, menu compris.
#
# ⚠️ ET LE PORTRAIT ALLAIT BIEN. C'est ce qui rend ce défaut invisible à la relecture : on
# vérifie « est-ce que ça tient sur mobile », la réponse est oui, et la taille qui casse est
# celle du milieu — entre le point de rupture à 900 px et la largeur confortable à 1100.
#
# ⚠️ ON MESURE `scrollWidth`, PAS LA FEUILLE DE STYLE. Une règle peut être juste et un contenu
# la déborder quand même ; seul le rectangle rendu le dit.

LARGEURS = [390, 768, 900, 1024, 1100, 1280]


@SANS
@pytest.mark.parametrize("largeur", LARGEURS)
def test_le_tableau_de_bord_ne_glisse_a_aucune_largeur(largeur, tmp_path):
    binaire, env = NAVIGATEUR
    cas = CAS["index.html"]
    chemin = _rendre("index.html", cas["reponses"], tmp_path, """
setTimeout(function(){
  var d = document.createElement('div'); d.id = 'LARGEUR';
  d.textContent = document.documentElement.scrollWidth;
  document.body.appendChild(d);
}, 600);
""")
    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         f"--window-size={largeur},900", "--virtual-time-budget=3000",
         "file://" + str(chemin)], capture_output=True, text=True, timeout=90, env=env)
    m = re.search(r'<div id="LARGEUR">(\d+)</div>', r.stdout)
    assert m, f"{largeur} px : la mesure n'a pas été rendue\n{r.stderr[:300]}"
    mesure = int(m.group(1))
    # ⚠️ ON TOLÈRE LA BARRE DE DÉFILEMENT VERTICALE, qui retire une quinzaine de pixels à la
    # zone utile — jamais plus. Au-delà, c'est le contenu qui pousse.
    assert mesure <= largeur, (
        f"à {largeur} px, la page s'étale sur {mesure} px : elle glisse horizontalement, "
        "menu compris")


# ══ AUCUNE COLONNE N'EST INATTEIGNABLE SUR TÉLÉPHONE ════════════════════════════════════════
#
# ⚠️ TROIS PAGES PERDAIENT LEURS COLONNES DE DROITE, et la règle qui devait l'empêcher était
# DÉJÀ ÉCRITE. `style.css` donne `overflow-x:auto` aux `.table-wrap` sous 768 px ; chaque page
# redéclarait ensuite `.table-wrap { … overflow:hidden }` dans son propre `<style>` — même
# spécificité, la dernière déclarée gagne, et la feuille de page vient après la feuille globale.
# Le correctif existait, avait l'air juste, et ne faisait rien.
#
# ⚠️ ET « ÇA DÉFILE » N'EST PAS « ÇA SE LIT ». Huit colonnes atteintes par un geste que personne
# ne découvre valent à peine mieux qu'invisibles. `/reconciliation` est donc passée en CARTES —
# c'est la page que Quentin consulte en mobilité, celle où un écart de caisse se rattrape. Les
# deux autres se consultent au bureau : le défilement y suffit, et c'est un choix, pas un reste.

TABLEAUX_MOBILES = ["reconciliation.html", "holidays.html", "cashflow.html"]


@SANS
@pytest.mark.parametrize("nom", TABLEAUX_MOBILES)
def test_aucune_colonne_nest_hors_datteinte_sur_telephone(nom, tmp_path):
    binaire, env = NAVIGATEUR
    chemin = _rendre(nom, CAS.get(nom, {}).get("reponses", {}), tmp_path, """
setTimeout(function(){
  var out = {scroll: document.documentElement.scrollWidth, bloques: []};
  document.querySelectorAll('table').forEach(function(t){
    var r = t.getBoundingClientRect();
    if (r.width <= 391) return;            // le tableau tient : rien à atteindre
    var p = t.parentElement, ok = false;
    for (var k = 0; k < 4 && p; k++) {
      var ov = getComputedStyle(p).overflowX;
      if (ov === 'auto' || ov === 'scroll') { ok = true; break; }
      p = p.parentElement;
    }
    if (!ok) out.bloques.push(Math.round(r.width));
  });
  var d = document.createElement('div'); d.id = 'MOB';
  d.textContent = JSON.stringify(out); document.body.appendChild(d);
}, 800);
""")
    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--window-size=390,900", "--virtual-time-budget=3000", "file://" + str(chemin)],
        capture_output=True, text=True, timeout=90, env=env)
    m = re.search(r'<div id="MOB">(.*?)</div>', r.stdout, re.S)
    assert m, f"{nom} : la mesure n'a pas été rendue\n{r.stderr[:300]}"
    d = json.loads(m.group(1))

    assert not d["bloques"], (
        f"{nom} : {len(d['bloques'])} tableau(x) plus larges que l'écran "
        f"({d['bloques']} px) sans conteneur défilant — leurs colonnes de droite sont "
        "inatteignables, sans le moindre indice à l'écran")
    assert d["scroll"] <= 391, (
        f"{nom} : la page entière glisse ({d['scroll']} px pour 390), menu compris")


@SANS
def test_LES_TROIS_ONGLETS_DES_COUTS_TIENNENT_SUR_UN_TELEPHONE(tmp_path):
    """
    ⚠️ UN ONGLET HORS DU CADRE EST UN ONGLET QUI N'EXISTE PAS. Mesuré avant correction : les
    trois libellés occupaient 453 px pour 390 px d'écran, donc « Personnel » commençait hors
    champ. `.nav-seg` défile, ce qui sauvait l'accès mais pas la découverte : rien à l'écran ne
    disait qu'il y avait un troisième onglet. Ce contrôle mesure les boutons, pas la feuille de
    style — une règle qui cesserait de s'appliquer (cascade, point de bascule déplacé) le fait
    rougir, un simple `grep` sur le CSS ne l'aurait pas vu.
    """
    binaire, env = NAVIGATEUR
    chemin = _rendre("charges.html", CAS["charges.html"]["reponses"], tmp_path, r"""
setTimeout(function(){
  var large = document.documentElement.clientWidth;
  var out = {large: large, hors: []};
  document.querySelectorAll('.nav-seg [role=tab]').forEach(function(b){
    var r = b.getBoundingClientRect();
    if (r.right > large + 1) out.hors.push(b.textContent.trim().replace(/\s+/g,' ')
                                           + ' → ' + Math.round(r.right) + 'px');
  });
  var d = document.createElement('div'); d.id = 'ONG';
  d.textContent = JSON.stringify(out); document.body.appendChild(d);
}, 800);
""")
    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--window-size=390,900", "--virtual-time-budget=3000", "file://" + str(chemin)],
        capture_output=True, text=True, timeout=90, env=env)
    m = re.search(r'<div id="ONG">(.*?)</div>', r.stdout, re.S)
    assert m, f"la mesure n'a pas été rendue\n{r.stderr[:300]}"
    d = json.loads(m.group(1))
    assert d["large"] <= 391, f"l'écran mesuré fait {d['large']} px, pas 390"
    assert not d["hors"], (
        f"{len(d['hors'])} onglet(s) hors de l'écran de {d['large']} px : {d['hors']} — "
        "la barre défile, donc rien ne signale à l'écran qu'ils existent")


@SANS
def test_LE_GRAPHE_DES_CHARGES_VARIABLES_SE_LIT_ET_SE_CORRIGE(tmp_path):
    """
    ⚠️ UNE FACTURE COUVRE UNE PÉRIODE, PAS UN MOIS. L'EPAL facture 60 jours à cheval sur trois
    mois civils. Le graphe empilait des mois ; il empile désormais des factures, à la hauteur de
    leur TAUX JOURNALIER — seule grandeur comparable entre une facture de 30 jours et une de 60,
    dont les totaux diffèrent du simple au double sans rien dire de la consommation.

    ⚠️ ET UN TROU SE COMPTE EN JOURS. Entre la facture qui finit le 20/07 et celle qui commence
    le 01/08, onze jours ne sont facturés par personne. Les barres se touchaient : personne ne
    les voyait.

    Les montants sont choisis pour que la troisième facture dépasse de plus de 30 % la moyenne
    des taux précédents, et la deuxième non : le repère doit apparaître sur l'une et pas l'autre.
    """
    binaire, env = NAVIGATEUR
    reponses = {
        "/api/statut": {"ca": None, "ca_texte": "—", "tickets": None, "moyen_texte": "",
                        "ecarts": 0, "boissons_dues": 0, "caisse_ok": None},
        "/api/charges": {
            "couverture": {"Eau": {"jusqua": "2026-09-29", "jours": 5,
                                   "debut_suivant": "2026-09-30"}},
            "aujourdhui": "2026-10-04", "mois_courant": "2026-10-01",
            "charges": [EPAL_1, EPAL_2, EPAL_3],
            "employees": [],
        },
    }
    chemin = _rendre("charges.html", reponses, tmp_path, r"""
setTimeout(function(){
  var trace = function(t){ var d = document.createElement('div'); d.textContent = t;
                           document.body.appendChild(d); };
  switchTab('variables');
  var carte = document.querySelector('.var-carte');
  var barres = carte.querySelectorAll('.var-barres > button');

  /* Quatre emplacements pour trois factures : les onze jours non facturés occupent le leur. */
  trace(barres.length === 4 ? 'QUATRE-EMPLACEMENTS' : 'FACTURES-COLLEES ' + barres.length);
  var creux = carte.querySelectorAll('.var-barres > button.creux');
  trace((creux.length === 1 && creux[0].dataset.jours === '11')
        ? 'TROU-COMPTE-EN-JOURS'
        : 'TROU-MASQUE ' + creux.length + '/' + (creux[0] || {dataset:{}}).dataset.jours);

  /* ⚠️ LA HAUTEUR EST LE TAUX, PAS LE TOTAL. Les trois factures durent 60 jours chacune ici ;
     la plus chère au total est aussi la plus chère au taux, mais c'est le taux qui est stocké
     et c'est lui qu'on compare. */
  var b3 = carte.querySelector('[data-mois="2026-08-01"]');
  trace(Math.abs(parseFloat(b3.dataset.taux) - 220 / 60) < 0.001
        ? 'HAUTEUR-SUR-LE-TAUX' : 'HAUTEUR-SUR-LE-TOTAL ' + b3.dataset.taux);

  /* ⚠️ UNE FACTURE D'AVANT LA MIGRATION N'A PAS DE PÉRIODE. Elle est lue comme couvrant son
     mois — ce qu'elle prétendait être, et ce que le serveur en fait déjà. Sans ce repli, son
     taux était nul : le graphe la dessinait à hauteur minimale et l'historique se lisait comme
     une consommation nulle. */
  chargesData.push({id:'v9', name:'Eau', amount:90.0, frequency:'monthly', mode:'facture',
                    mois:'2026-11-01', periode_debut:null, periode_fin:null,
                    valid_from:'2026-11-01', valid_to:null, active:true});
  renderVariables();
  var vieille = document.querySelector('[data-mois="2026-11-01"]');
  trace((vieille && Math.abs(parseFloat(vieille.dataset.taux) - 90 / 30) < 0.001)
        ? 'SANS-PERIODE-LUE-SUR-SON-MOIS'
        : 'SANS-PERIODE-SANS-TAUX ' + (vieille || {dataset:{}}).dataset.taux);
  chargesData.pop();
  renderVariables();
  carte = document.querySelector('.var-carte');
  creux = carte.querySelectorAll('.var-barres > button.creux');
  b3 = carte.querySelector('[data-mois="2026-08-01"]');

  /* Le repère d'anomalie : la troisième oui, la deuxième non. */
  var alertes = [].slice.call(carte.querySelectorAll('.var-barres > button.alerte'))
                  .map(function(b){ return b.dataset.mois; });
  trace(JSON.stringify(alertes) === '["2026-08-01"]'
        ? 'ANORMAL-SIGNALE' : 'ANORMAL-MUET ' + JSON.stringify(alertes));

  /* Le survol réécrit le grand chiffre de la carte, et dit la PÉRIODE, pas un mois. */
  var avant = carte.querySelector('.var-montant').textContent;
  var b2 = carte.querySelector('[data-mois="2026-05-22"]');
  b2.dispatchEvent(new MouseEvent('mouseenter', {bubbles:false}));
  var sous = carte.querySelector('.var-sous').textContent.replace(/\s+/g,' ');
  trace(carte.querySelector('.var-montant').textContent.indexOf('170') >= 0
        ? 'SURVOL-DIT-LE-MONTANT' : 'SURVOL-MUET');
  trace((sous.indexOf('22 mai 2026') >= 0 && sous.indexOf('20 juil 2026') >= 0)
        ? 'SURVOL-DIT-LA-PERIODE' : 'SURVOL-SANS-PERIODE ' + sous);
  /* ⚠️ ET LE COÛT MENSUEL À CÔTÉ : 170 € sur 60 jours font 86 €/mois, et c'est ce chiffre-là
     qui entre dans le point mort. Montrer le total seul le faisait lire comme un mensuel. */
  trace(sous.indexOf('86.2') >= 0 ? 'SURVOL-DIT-LE-MENSUEL' : 'SURVOL-SANS-MENSUEL ' + sous);

  carte.querySelector('.var-barres').dispatchEvent(new MouseEvent('mouseleave', {bubbles:false}));
  trace(carte.querySelector('.var-montant').textContent === avant
        ? 'SURVOL-REND-LA-CARTE' : 'SURVOL-COLLE');

  /* Survoler le trou doit dire combien de jours, pas afficher un zéro. */
  creux[0].dispatchEvent(new MouseEvent('mouseenter', {bubbles:false}));
  var st = carte.querySelector('.var-sous').textContent;
  trace((carte.querySelector('.var-montant').textContent === '—'
         && st.indexOf('11 jours non facturés') >= 0)
        ? 'TROU-SE-DIT' : 'TROU-CHIFFRE ' + st.slice(0,60));

  /* Le clavier atteint les valeurs. */
  var et = b2.getAttribute('aria-label') || '';
  trace((et.indexOf('22 mai 2026') >= 0 && et.indexOf('170') >= 0)
        ? 'CLAVIER-ENTEND-LA-VALEUR' : 'CLAVIER-SOURD ' + et);

  /* Cliquer une barre ouvre la fenêtre SUR CETTE FACTURE, en mode correction. */
  b2.click();
  trace((document.getElementById('fact-mois').value === '2026-05-22'
         && document.getElementById('fact-ok').textContent === 'Corriger')
        ? 'BARRE-CORRIGE-SA-FACTURE' : 'BARRE-OUVRE-AUTRE-CHOSE ' +
          document.getElementById('fact-mois').value);
  fermerFacture();

  /* Cliquer le trou ouvre la même fenêtre au premier jour non facturé. */
  creux[0].click();
  trace((document.getElementById('fact-mois').value === '2026-07-21'
         && document.getElementById('fact-ok').textContent === 'Enregistrer')
        ? 'TROU-SE-SAISIT' : 'TROU-INERTE ' + document.getElementById('fact-mois').value);
  fermerFacture();

  /* Le total dit combien de factures, et combien de jours manquent. */
  var stats = (carte.querySelector('.var-stats') || {}).textContent || '';
  stats = stats.replace(/\s+/g,' ');
  trace(stats.indexOf('3 factures') >= 0 ? 'TOTAL-DIT-SA-PORTEE' : 'TOTAL-SANS-PORTEE ' + stats);
  trace(stats.indexOf('550') >= 0 ? 'TOTAL-JUSTE' : 'TOTAL-FAUX ' + stats);
  trace(stats.indexOf('11 jours non facturés') >= 0
        ? 'TOTAL-AVOUE-LE-TROU' : 'TOTAL-TAIT-LE-TROU ' + stats);
}, 400);
""")
    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--virtual-time-budget=4000", "file://" + str(chemin)],
        capture_output=True, text=True, timeout=90, env=env)
    rendu = re.sub(r"<script[\s\S]*?</script>", " ", r.stdout, flags=re.I)

    for m in ["QUATRE-EMPLACEMENTS", "TROU-COMPTE-EN-JOURS", "HAUTEUR-SUR-LE-TAUX", "SANS-PERIODE-LUE-SUR-SON-MOIS",
              "ANORMAL-SIGNALE", "SURVOL-DIT-LE-MONTANT", "SURVOL-DIT-LA-PERIODE",
              "SURVOL-DIT-LE-MENSUEL", "SURVOL-REND-LA-CARTE", "TROU-SE-DIT",
              "CLAVIER-ENTEND-LA-VALEUR", "BARRE-CORRIGE-SA-FACTURE", "TROU-SE-SAISIT",
              "TOTAL-DIT-SA-PORTEE", "TOTAL-JUSTE", "TOTAL-AVOUE-LE-TROU"]:
        assert m in rendu, f"« {m} » absent — {rendu[-900:]}"
    for m in ["FACTURES-COLLEES", "TROU-MASQUE", "HAUTEUR-SUR-LE-TOTAL", "SANS-PERIODE-SANS-TAUX", "ANORMAL-MUET",
              "SURVOL-MUET", "SURVOL-SANS-PERIODE", "SURVOL-SANS-MENSUEL", "SURVOL-COLLE",
              "TROU-CHIFFRE", "CLAVIER-SOURD", "BARRE-OUVRE-AUTRE-CHOSE", "TROU-INERTE",
              "TOTAL-SANS-PORTEE", "TOTAL-FAUX", "TOTAL-TAIT-LE-TROU",
              "NaN", "undefined", "Invalid Date"]:
        assert m not in rendu, f"« {m} » apparaît à l'écran"


@SANS
def test_LA_RECONCILIATION_PASSE_EN_CARTES_SUR_TELEPHONE(tmp_path):
    """
    ⚠️ C'EST LA PAGE QU'ON CONSULTE EN MOBILITÉ, et huit colonnes derrière un geste latéral n'y
    sont pas utilisables. Chaque journée devient une carte : tout se lit sans geste à découvrir.

    ⚠️ ET LE PLANCHER DE `style.css` DOIT ÊTRE NEUTRALISÉ. `.table-wrap table { min-width:560px }`
    y est posé pour autoriser le défilement : en cartes, il forçait la page à 560 px dans un
    écran de 390 — le défaut qu'on corrige, produit par la règle censée le corriger.
    """
    binaire, env = NAVIGATEUR
    chemin = _rendre("reconciliation.html", {}, tmp_path, """
setTimeout(function(){
  var tb = document.getElementById('tbody');
  tb.innerHTML = '<tr><td class="date" data-libelle="Jour">lun 28/09</td>'
    + '<td class="num" data-libelle="Ventes terminal">412,30 &euro;</td>'
    + '<td class="num" data-libelle="\\u00c9cart">0,00 &euro;</td></tr>';
  tb.offsetHeight;
  var t = document.querySelector('.table-wrap table'), tr = tb.querySelector('tr');
  var td = tr.querySelectorAll('td')[1];
  var d = document.createElement('div'); d.id = 'CARTES';
  d.textContent = JSON.stringify({
    tr: getComputedStyle(tr).display,
    thead: getComputedStyle(t.querySelector('thead')).display,
    libelle: getComputedStyle(td, '::before').content,
    largeur: Math.round(t.getBoundingClientRect().width)
  });
  document.body.appendChild(d);
}, 800);
""")
    r = subprocess.run(
        [binaire, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom",
         "--window-size=390,900", "--virtual-time-budget=3000", "file://" + str(chemin)],
        capture_output=True, text=True, timeout=90, env=env)
    m = re.search(r'<div id="CARTES">(.*?)</div>', r.stdout, re.S)
    assert m, f"la mesure n'a pas été rendue\n{r.stderr[:300]}"
    d = json.loads(m.group(1))

    assert d["tr"] == "block", "les lignes n'ont pas pris la forme de cartes"
    assert d["thead"] == "none", "l'en-tête de colonnes reste affiché au-dessus des cartes"
    assert "Ventes terminal" in d["libelle"], (
        "la carte n'affiche pas le nom de la donnée : un montant seul ne se lit pas")
    assert d["largeur"] <= 391, (
        f"la table fait {d['largeur']} px — le `min-width` de style.css n'est pas neutralisé")
