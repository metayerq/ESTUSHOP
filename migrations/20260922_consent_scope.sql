-- À QUOI LA PERSONNE A DIT OUI.
--
-- ⚠️ LE CONSENTEMENT EST ORAL, ET C'EST VALABLE. La loi ne demande pas un écrit : elle demande
-- qu'il soit libre, précis, éclairé — et que le commerçant puisse DÉMONTRER ce à quoi la
-- personne a consenti. On enregistrait `consent_at` et `consent_source` : quand, et où. Pas à
-- quoi.
--
-- ⚠️ ET « LES POINTS PAR SMS » NE COUVRE PAS « VENEZ À NOTRE ÉVÉNEMENT ». Ce sont deux
-- finalités distinctes. Sans cette colonne, la seule façon de lancer une campagne marketing
-- serait de se fier à son souvenir de ce qui a été dit au comptoir, il y a des mois, par
-- quelqu'un d'autre.

alter table public.card_customers
  add column if not exists consent_scope text not null default 'points';

comment on column public.card_customers.consent_scope is
  'A quoi cette personne a dit oui au comptoir : points | points+news. '
  'FIGE a l''inscription — changer la phrase du comptoir ne reecrit pas le passe.';

-- La phrase actuellement prononcée au comptoir. ⚠️ C'EST UN RÉGLAGE, PAS UNE CONSTANTE : le
-- jour où elle change, les nouveaux inscrits sont couverts pour davantage, et les anciens
-- gardent le leur. Aucune campagne de re-consentement, le problème s'éteint tout seul.
alter table public.card_settings
  add column if not exists consent_scope text not null default 'points';
