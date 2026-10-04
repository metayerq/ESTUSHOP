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
