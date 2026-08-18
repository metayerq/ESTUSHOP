-- Corrections de solde : le motif est OBLIGATOIRE.
--
-- Un crédit attribué au mauvais client arrivera — un numéro mal tapé, une récompense donnée
-- deux fois. Sans écran de correction, la seule issue serait de modifier la base à la main.
-- Et sans MOTIF, une correction devient indiscernable d'une erreur de plus : six mois plus tard,
-- personne ne saura pourquoi un solde a bougé de −10.
alter table public.loyalty_events add column if not exists reason text;
