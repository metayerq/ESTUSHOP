-- Couverts estimés, jour par jour.
--
-- À EXÉCUTER EN MÊME TEMPS QUE 20260807_daily_summary_hours.sql, avant le rebuild : les deux
-- colonnes se remplissent au même passage. Les séparer coûterait un second aller-retour
-- complet sur l'API Vendus (~1250 documents).
--
-- POURQUOI
-- Vendus ne dit pas combien de personnes il y avait derrière un ticket : le champ n'existe ni
-- sur le document ni sur les lignes (vérifié sur 80 documents répartis sur tout l'historique),
-- et 59 tickets sur 60 portent le NIF vide « --------- ». L'heuristique retenue est celle du
-- propriétaire : UNE BOISSON = UNE PERSONNE.
--
-- Mesurée sur ses données du 1er juillet au 6 août : 734 tickets, 1031 personnes, 1,40 par
-- ticket. Distribution sans queue aberrante — 0 boisson : 18 %, 1 : 48 %, 2 : 29 %, 3 : 4 %,
-- maximum 5. Aucun ticket écrêté sur cette période.
--
-- LES DEUX GARDES
-- · PLANCHER À 1. 18 % des tickets ne portent aucune boisson — un livre, une pâtisserie à
--   emporter. Sans plancher, 133 clients réels compteraient pour zéro.
-- · PLAFOND À 8, qui compte ce qu'il coupe (`covers_capped`). Juin porte des tickets à 29, 43
--   et 55 boissons : des commandes de groupe, pas 55 personnes assises. L'écran annonce le
--   nombre de tickets écrêtés au lieu de lisser en silence.
--
-- ⚠️ C'EST UNE ESTIMATION HAUTE, ET L'ÉCRAN DOIT LE DIRE. Une personne qui prend deux boissons
-- compte pour deux ; un café emporté pour trois collègues compte pour trois. Elle ne
-- sous-estime jamais. D'où « personnes estimées » partout, et jamais « clients ».
--
-- ⚠️ NULL N'EST PAS ZÉRO. Une ligne écrite avant cette migration n'a pas « zéro personne »,
-- elle n'a pas la mesure. Le code écarte ces jours des médianes. Pas de DEFAULT.
--
-- FRAGILITÉ CONNUE : la liste des catégories boissons est figée dans vendus.py
-- (DRINK_CAT_IDS, 33 produits sur 104). Une nouvelle catégorie de boissons créée dans Vendus
-- ne serait pas comptée, et rien ne le signalerait. À revoir si la carte évolue.

alter table public.daily_summary
  add column if not exists covers        integer,
  add column if not exists covers_capped integer;

comment on column public.daily_summary.covers is
  'Personnes ESTIMÉES : 1 boisson = 1 personne, plancher 1 par ticket, plafond 8. '
  'Estimation haute, jamais un décompte. NULL = journée non instrumentée.';

comment on column public.daily_summary.covers_capped is
  'Nombre de tickets ramenés au plafond ce jour-là — à afficher, pas à masquer.';
