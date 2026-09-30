# -*- coding: utf-8 -*-
"""
FACTURER UN TIERS — CE QUI NE DOIT JAMAIS DÉRAPER.

Porté de `apps/pos/lib/invoice.test.ts` le 30/09/2026, avec l'écran qui quittait la caisse.
⚠️ CES TESTS SONT LA RAISON POUR LAQUELLE LE PORTAGE ÉTAIT ACCEPTABLE. Réécrire des règles
fiscales dans un autre langage sans elles aurait été un pari sur un document irréversible.

Le premier test rejoue la SEULE facture réellement émise — FR 01P2026/1, 136,50 € le
08/09/2026 — et exige les montants que Vendus a effectivement produits.
"""
import datetime
import pytest
from facturation import (TAX_IDS, ligne_ttc_unitaire, totaux, manques, emettable,
                         date_echeance, corps_facture)


CLIENT = {"nom": "TOMOKO HIRAOJI.", "nif": "332457389",
          "adresse": "Rua Heróis de Quionga 17", "code_postal": "1170-178", "ville": "Lisboa"}

def ligne(**kw):
    base = {"service_id": 372683324, "libelle": "Comissao sobre venda popup 15 agosto",
            "montant_cents": 13650, "ttc": True, "taux": 23, "qty": 1}
    base.update(kw)
    return base


# ── Le document réel ────────────────────────────────────────────────────────────────────────

def test_la_facture_reelle_du_8_septembre_se_reproduit():
    """
    ⚠️ 136,50 € TTC SAISIS DOIVENT PARTIR À 136,50 €. Vendus en a déduit 110,98 € HT — lequel,
    reconverti, redonnerait 136,51 €. Un centime de plus que ce qui a été reçu, sur un document
    qui ne se corrige pas.
    """
    corps = corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                          register_id=342853246, mode="normal", moyen_paiement_id=342853234)
    assert corps["items"][0]["gross_price"] == 136.50
    assert corps["items"][0]["tax_id"] == "NOR"
    assert corps["type"] == "FR" and corps["register_id"] == 342853246
    assert corps["payments"] == [{"id": 342853234}]
    t = totaux([ligne()])
    assert (t["ttc_cents"], t["net_cents"], t["tva_cents"]) == (13650, 11098, 2552)


def test_le_ht_retape_ne_revient_pas_au_ttc():
    # La démonstration du piège, gardée comme test : c'est POURQUOI on ne convertit pas.
    assert round(11098 * 1.23) == 13651


# ── Les montants ────────────────────────────────────────────────────────────────────────────

def test_un_montant_ttc_part_tel_quel():
    assert ligne_ttc_unitaire(ligne(montant_cents=13650, ttc=True)) == 13650

def test_un_montant_ht_est_converti_dans_le_seul_sens_sans_perte():
    assert ligne_ttc_unitaire(ligne(montant_cents=11098, ttc=False, taux=23)) == 13651
    assert ligne_ttc_unitaire(ligne(montant_cents=10000, ttc=False, taux=6)) == 10600

def test_la_tva_se_calcule_PAR_TAUX_et_jamais_sur_la_somme():
    """
    ⚠️ Une facture qui mélange 13 % et 23 % n'a pas « un » taux. Appliquer celui de la première
    ligne au total produirait une TVA fausse, déclarée telle quelle.
    """
    t = totaux([ligne(montant_cents=11300, taux=13), ligne(montant_cents=12300, taux=23)])
    assert [d["taux"] for d in t["par_taux"]] == [13, 23]
    assert t["par_taux"][0] == {"taux": 13, "net_cents": 10000, "tva_cents": 1300}
    assert t["par_taux"][1] == {"taux": 23, "net_cents": 10000, "tva_cents": 2300}
    assert t["ttc_cents"] == 23600

def test_base_plus_tva_retombe_toujours_sur_le_total():
    # ⚠️ La TVA est le RESTE, jamais un second arrondi : sinon la facture ne s'additionne pas
    # elle-même, et c'est le genre d'écart qu'un comptable voit avant nous.
    for cents in (1, 7, 99, 333, 1234, 13650, 99999, 1234567):
        for taux in (0, 6, 13, 23):
            t = totaux([ligne(montant_cents=cents, ttc=True, taux=taux)])
            assert t["net_cents"] + t["tva_cents"] == t["ttc_cents"] == cents

def test_la_quantite_multiplie_le_ttc_pas_le_ht():
    t = totaux([ligne(montant_cents=13650, qty=3)])
    assert t["ttc_cents"] == 40950

def test_le_taux_zero_ne_produit_aucune_tva():
    t = totaux([ligne(montant_cents=5000, taux=0)])
    assert t["par_taux"] == [{"taux": 0, "net_cents": 5000, "tva_cents": 0}]


# ── Ce qui interdit d'émettre ───────────────────────────────────────────────────────────────

def test_un_brouillon_complet_est_emettable():
    assert emettable({"type": "FR", "client": CLIENT, "lignes": [ligne()]})

def test_tous_les_manques_sont_rendus_pas_seulement_le_premier():
    # Un écran qui les révèle un par un fait remplir, refuse, fait remplir, refuse encore.
    m = manques({"type": "FT", "client": None, "lignes": []})
    assert "client" in m and "lignes" in m and "delai" in m

def test_un_nom_vide_bloque_meme_avec_un_nif_valide():
    """⚠️ Une vingtaine de fiches du compte portent un NIF et un nom VIDE, créées par les NIF
    tapés au comptoir. En reprendre une produirait une facture sans acquéreur nommé."""
    m = manques({"type": "FR", "client": {**CLIENT, "nom": "  "}, "lignes": [ligne()]})
    assert "client-nom" in m

@pytest.mark.parametrize("nif", ["", "12345678", "1234567890", "12345678A", "  "])
def test_un_nif_qui_n_a_pas_neuf_chiffres_bloque(nif):
    assert "client-nif" in manques({"type": "FR", "client": {**CLIENT, "nif": nif},
                                    "lignes": [ligne()]})

def test_une_adresse_incomplete_bloque():
    assert "client-adresse" in manques({"type": "FR", "client": {**CLIENT, "ville": ""},
                                        "lignes": [ligne()]})

def test_une_ligne_sans_fiche_de_prestation_bloque():
    """⚠️ Sans `service_id`, Vendus CRÉE un produit dans le catalogue de production. Quelques
    factures suffiraient à le remplir de fiches fantômes."""
    assert "ligne-prestation" in manques({"type": "FR", "client": CLIENT,
                                          "lignes": [ligne(service_id=0)]})

def test_un_montant_nul_ou_negatif_bloque():
    for c in (0, -1):
        assert "ligne-montant" in manques({"type": "FR", "client": CLIENT,
                                           "lignes": [ligne(montant_cents=c)]})

def test_une_seule_ligne_fautive_bloque_toute_la_facture():
    # Émettre les lignes valides et taire les autres produirait une facture d'un montant
    # inférieur à celui qui a été relu.
    m = manques({"type": "FR", "client": CLIENT, "lignes": [ligne(), ligne(libelle=" ")]})
    assert "ligne-libelle" in m

def test_un_taux_inconnu_bloque():
    assert "ligne-taux" in manques({"type": "FR", "client": CLIENT, "lignes": [ligne(taux=20)]})

def test_une_FT_sans_echeance_bloque():
    """⚠️ Une créance sans date n'apparaît jamais comme en retard, donc jamais dans une relance."""
    assert "delai" in manques({"type": "FT", "client": CLIENT, "lignes": [ligne()]})
    assert "delai" not in manques({"type": "FT", "client": CLIENT, "lignes": [ligne()],
                                   "delai_jours": 30})

def test_une_FR_n_a_pas_d_echeance():
    assert "delai" not in manques({"type": "FR", "client": CLIENT, "lignes": [ligne()]})

def test_un_type_inconnu_bloque():
    assert "type" in manques({"type": "FS", "client": CLIENT, "lignes": [ligne()]})


# ── Le corps envoyé ─────────────────────────────────────────────────────────────────────────

def test_une_FT_porte_une_DATE_d_echeance_pas_un_delai():
    """⚠️ `date_due: "+30 days"` est refusé par Vendus — « P006, valeur invalide pour date »."""
    corps = corps_facture({"type": "FT", "client": CLIENT, "lignes": [ligne()], "delai_jours": 30},
                          register_id=342853246, mode="normal",
                          aujourdhui=datetime.date(2026, 9, 30))
    assert corps["date_due"] == "2026-10-30"
    assert "payments" not in corps

def test_une_FR_porte_son_reglement_et_aucune_echeance():
    corps = corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                          register_id=342853246, mode="tests", moyen_paiement_id=7)
    assert corps["payments"] == [{"id": 7}] and "date_due" not in corps
    assert corps["mode"] == "tests"

def test_une_FR_sans_reglement_LEVE_avant_tout_appel_reseau():
    with pytest.raises(ValueError, match="moyen de règlement"):
        corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                      register_id=342853246, mode="normal")

def test_une_FT_sans_jour_d_emission_LEVE():
    with pytest.raises(ValueError, match="jour d'émission"):
        corps_facture({"type": "FT", "client": CLIENT, "lignes": [ligne()], "delai_jours": 30},
                      register_id=342853246, mode="normal")

def test_un_brouillon_incomplet_LEVE_plutot_que_d_emettre_au_mieux():
    with pytest.raises(ValueError, match="incomplète"):
        corps_facture({"type": "FR", "client": None, "lignes": []},
                      register_id=342853246, mode="normal", moyen_paiement_id=7)

def test_sans_caisse_d_emission_on_LEVE():
    # ⚠️ Laisser Vendus choisir la caisse émettrait sur une série qu'on ne croit pas.
    with pytest.raises(ValueError, match="caisse"):
        corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                      register_id=0, mode="normal", moyen_paiement_id=7)

def test_un_mode_fiscal_inconnu_LEVE():
    with pytest.raises(ValueError, match="mode fiscal"):
        corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                      register_id=342853246, mode="reel", moyen_paiement_id=7)

def test_sans_email_rien_n_est_transmis():
    sans = corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                         register_id=1, mode="tests", moyen_paiement_id=7)
    assert "email" not in sans["client"] and "send_email" not in sans["client"]


def test_un_email_rempli_ne_declenche_PAS_l_envoi_a_lui_seul():
    """
    ⚠️ L'ENVOI SE DEMANDE, IL NE SE DÉDUIT PAS. Remplir le champ posait `send_email: yes` : le
    client recevait la facture sans que rien à l'écran ne l'annonce — et reprendre une fiche
    connue qui portait un email suffisait à déclencher l'envoi. Un effet de bord invisible sur
    un document fiscal est une décision prise à la place de quelqu'un.
    """
    b = corps_facture({"type": "FR", "client": {**CLIENT, "email": " a@b.pt "},
                       "lignes": [ligne()]}, register_id=1, mode="tests", moyen_paiement_id=7)
    assert b["client"]["email"] == "a@b.pt"
    assert "send_email" not in b["client"], "l'envoi est parti sans qu'on le demande"


def test_l_envoi_demande_explicitement_part():
    b = corps_facture({"type": "FR", "client": {**CLIENT, "email": "a@b.pt"},
                       "lignes": [ligne()], "envoyer_email": True},
                      register_id=1, mode="tests", moyen_paiement_id=7)
    assert b["client"]["send_email"] == "yes"


def test_l_envoi_demande_sans_adresse_ne_part_pas():
    # Cocher la case sans adresse ne doit pas produire un `send_email` sans destinataire.
    b = corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()],
                       "envoyer_email": True},
                      register_id=1, mode="tests", moyen_paiement_id=7)
    assert "send_email" not in b["client"]

def test_le_qrcode_est_toujours_demande():
    corps = corps_facture({"type": "FR", "client": CLIENT, "lignes": [ligne()]},
                          register_id=1, mode="tests", moyen_paiement_id=7)
    assert corps["return_qrcode"] == 1

def test_les_identifiants_de_taux_sont_ceux_de_vendus():
    assert TAX_IDS == {0: "ISE", 6: "RED", 13: "INT", 23: "NOR"}

def test_l_echeance_se_calcule_sur_un_jour_donne_jamais_sur_l_horloge():
    assert date_echeance(datetime.date(2026, 12, 20), 30) == "2027-01-19"


# ── Reprendre la dernière facture ───────────────────────────────────────────────────────────

"""
⚠️ LA FONCTION LA PLUS UTILE DE L'ÉCRAN, ET ELLE VIENT DE L'USAGE. Une facture tous les deux
mois : entre deux, personne ne se souvient du client, du libellé, du taux ni du règlement. Les
retrouver à la main est exactement là où l'on se trompe — et se tromper produit un document
qu'on ne peut plus retirer.
"""
from facturation import derniere_facture, articles

DOC_REEL = {
    "type": "FR", "number": "FR 01P2026/1", "register_id": 342853246,
    "client": {"name": "TOMOKO HIRAOJI.", "fiscal_id": "332457389",
               "address": "Rua Heróis de Quionga 17", "postalcode": "1170-178", "city": "Lisboa"},
    "items": [{"id": 372683324, "qty": 1, "title": "Comissao sobre venda popup 15 agosto",
               "tax": {"id": "NOR", "rate": 23},
               "amounts": {"net_unit": "110.98", "gross_unit": "136.50"}}],
    "payments": [{"id": 342853234, "title": "Multibanco", "amount": "136.50"}],
}


def test_la_derniere_facture_se_reprend_a_l_identique():
    d = derniere_facture([{"day": "2026-09-08", "docs": [DOC_REEL]}])
    assert d["numero"] == "FR 01P2026/1" and d["type"] == "FR"
    assert d["client"]["nom"] == "TOMOKO HIRAOJI." and d["client"]["nif"] == "332457389"
    assert d["moyen_paiement"] == "Multibanco"
    assert d["lignes"][0]["libelle"] == "Comissao sobre venda popup 15 agosto"


def test_le_montant_est_repris_en_TTC_jamais_en_HT():
    """⚠️ Reprendre le HT (110,98) ferait une facture à 136,51 € — un centime de plus que la
    précédente, sur un document irréversible. On reprend ce qui avait été saisi."""
    d = derniere_facture([{"day": "2026-09-08", "docs": [DOC_REEL]}])
    assert d["lignes"][0]["montant_cents"] == 13650
    assert d["lignes"][0]["ttc"] is True


def test_l_article_n_est_PAS_repris():
    """⚠️ Le document ne porte que l'identifiant de la LIGNE, pas celui de la fiche catalogue.
    Le proposer ferait viser une fiche qui n'existe pas — l'écran le redemande, et le dit."""
    d = derniere_facture([{"day": "2026-09-08", "docs": [DOC_REEL]}])
    assert d["lignes"][0]["service_id"] == 0


def test_les_ventes_ordinaires_ne_sont_pas_des_factures_a_tiers():
    cache = [{"day": "2026-09-26", "docs": [{"type": "FS", "number": "FS 01P2026/1"}]}]
    assert derniere_facture(cache) is None
    assert derniere_facture([]) is None
    assert derniere_facture(None) is None


def test_la_plus_recente_gagne():
    vieux = {**DOC_REEL, "number": "FR 01P2026/0"}
    d = derniere_facture([{"day": "2026-09-08", "docs": [DOC_REEL]},
                          {"day": "2026-07-01", "docs": [vieux]}])
    assert d["numero"] == "FR 01P2026/1"


# ── Le catalogue, sans filtre deviné ────────────────────────────────────────────────────────

class _FauxReq:
    def __init__(self, produits): self.produits = produits
    def get(self, url, **kw):
        class R:
            status_code = 200
            ok = True
            def __init__(self, d): self._d = d
            def json(self): return self._d
            def raise_for_status(self): pass
        return R(self.produits if kw.get("params", {}).get("page", 1) == 1 else [])


def test_tout_le_catalogue_actif_est_rendu(monkeypatch):
    """
    ⚠️ LE MARQUEUR « SANS CATÉGORIE » ÉTAIT FAUX, ET C'EST L'ÉCRAN QUI L'A DIT. Il ne rendait
    qu'un seul article — « sticks » — et cachait la fiche de commission qui avait servi à la
    seule facture réelle. On ne remplace pas un marqueur faux par un autre : on rend tout.
    """
    monkeypatch.setenv("VENDUS_API_KEY", "k")
    req = _FauxReq([
        {"id": 1, "title": "Espresso", "category_id": 5, "tax_id": "INT", "status": "on"},
        {"id": 2, "title": "sticks", "category_id": None, "tax_id": "NOR", "status": "on"},
        {"id": 3, "title": "Comissao sobre vendas", "category_id": 9, "tax_id": "NOR", "status": "on"},
        {"id": 4, "title": "Retiré", "category_id": 5, "tax_id": "NOR", "status": "off"},
    ])
    a = articles(req)
    assert [x["id"] for x in a] == [2, 3, 1], "sans catégorie d'abord, puis par titre"
    assert all(x["id"] != 4 for x in a), "un article désactivé ne se facture pas"
    assert a[2]["taux"] == 13


# ── La clé de contrôle du NIF ───────────────────────────────────────────────────────────────

from facturation import nif_valide, montant_cents_strict


def test_les_deux_NIF_reels_du_dossier_passent():
    """L'acquéreur de la facture du 08/09/2026, et Quiet Frequency qui l'a émise."""
    assert nif_valide("332457389")
    assert nif_valide("519091647")


def test_une_transposition_de_chiffres_est_refusee():
    """
    ⚠️ NEUF CHIFFRES NE SUFFISENT PAS. 332457839 au lieu de 332457389 passe un contrôle de
    longueur, atterrit sur un document fiscal au nom de personne, et ne se répare que par note
    de crédit.
    """
    assert not nif_valide("332457839")
    assert "client-nif" in manques(
        {"type": "FR", "client": {**CLIENT, "nif": "332457839"}, "lignes": [ligne()]})


@pytest.mark.parametrize("n", ["", "12345678", "1234567890", "12345678A", "000000000",
                               "432457389", "332457380"])
def test_ce_qui_n_est_pas_un_NIF_est_refuse(n):
    assert not nif_valide(n)


# ── Le montant, lu strictement ──────────────────────────────────────────────────────────────

def test_le_format_portugais_avec_milliers_est_compris():
    """
    ⚠️ `parseFloat` LE MANGEAIT EN SILENCE : « 1.365,00 » devenait 1,37 € au lieu de
    1 365,00 €, sur un document irréversible.
    """
    assert montant_cents_strict("1.365,00") == 136500
    assert montant_cents_strict("136,50") == 13650
    assert montant_cents_strict("136.50") == 13650
    assert montant_cents_strict(" 136,5 ") == 13650
    assert montant_cents_strict("1000") == 100000


@pytest.mark.parametrize("t", ["13,650", "1a36", "1.365.00", "1,36,5", "", "  ", "abc",
                               "-136,50", "136,505"])
def test_un_montant_mal_forme_est_REFUSE_jamais_interprete(t):
    # Interpréter au mieux produit un montant que personne n'a voulu, et on ne le sait qu'après.
    assert montant_cents_strict(t) is None
