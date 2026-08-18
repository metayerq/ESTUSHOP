-- Enregistrer TOUTES les visites, boisson ou pas, avec le montant.
--
-- ⚠️ CE QUI MANQUAIT. Un ticket sans boisson ne laissait AUCUNE trace : ni visite, ni date de
-- dernier passage, ni montant. Quelqu'un qui vient acheter un livre chaque semaine était
-- invisible dans la fidélité — et cet historique ne se reconstruit pas : chaque jour passé est
-- perdu définitivement.
--
-- ⚠️ EN CENTIMES, PAS EN EUROS. Un montant en virgule flottante dérive à l'addition : sur des
-- centaines de tickets, un cumul finit par ne plus tomber juste, et la dérive est invisible
-- jusqu'au jour où l'on compare avec la comptabilité. Les entiers ne dérivent pas.
alter table public.loyalty_events  add column if not exists amount_cents integer;
alter table public.loyalty_members add column if not exists spent_cents  integer;
