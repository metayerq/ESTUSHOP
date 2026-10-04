-- Une facture couvre une PÉRIODE, pas un mois.
--
-- ⚠️ L'HYPOTHÈSE S'EST CASSÉE SUR LA PREMIÈRE VRAIE FACTURE D'EAU. L'EPAL facture 60 jours :
-- du 21/07/2026 au 18/09/2026, 176,14 €, à cheval sur TROIS mois civils. Lue comme un montant
-- mensuel, elle pesait 176,14 €/mois au lieu de 89,36 € — 86,78 € de trop chaque mois dans le
-- point mort. Les factures d'électricité portent une période elles aussi.
--
-- Les deux colonnes sont NULL sur les lignes existantes. Les charges STABLES les gardent à NULL
-- et ne bougent pas d'un centime. Les factures déjà saisies au mois reçoivent la période
-- qu'elles prétendaient couvrir : le taux × les jours du mois redonne exactement leur montant,
-- donc aucun chiffre ne change — on inscrit seulement ce qui était implicite.

alter table charges_fixes
  add column if not exists periode_debut date,
  add column if not exists periode_fin   date;

-- Les factures déjà saisies au mois : on INSCRIT ce qu'elles prétendaient couvrir, pour que la
-- règle soit la même pour toutes et qu'il n'y ait plus de ligne « sans période » à interpréter.
update charges_fixes
   set periode_debut = date_trunc('month', mois::date)::date,
       periode_fin   = (date_trunc('month', mois::date) + interval '1 month - 1 day')::date
 where mode = 'facture'
   and mois is not null
   and periode_debut is null;

-- Vérification : chaque facture doit porter une période cohérente.
select name,
       to_char(periode_debut, 'YYYY-MM-DD') as debut,
       to_char(periode_fin,   'YYYY-MM-DD') as fin,
       (periode_fin - periode_debut) + 1    as jours,
       amount,
       round((amount / ((periode_fin - periode_debut) + 1) * 30.44)::numeric, 2) as par_mois
  from charges_fixes
 where mode = 'facture'
 order by name, periode_debut;

-- ── Le rythme de facturation ───────────────────────────────────────────────────────────────
--
-- ⚠️ IL NE DÉCIDE RIEN DU CALCUL. Il sert uniquement à PROPOSER la date de fin dans la fenêtre
-- de saisie, pour ne pas retaper une date connue d'avance. Ce qui est stocké et ce qui compte
-- reste la période imprimée sur la facture, que l'écran laisse corriger.
alter table charges_fixes add column if not exists rythme text;
