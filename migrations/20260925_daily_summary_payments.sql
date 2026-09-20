-- LA RÉPARTITION PAR MOYEN DE PAIEMENT, DANS LE CACHE DU JOUR.
--
-- ⚠️ SANS ELLE, COMPARER L'ENCAISSEMENT TERMINAL AU FACTURÉ VENDUS EXIGE DE RECHARGER TOUT LE
-- MOIS depuis l'API Vendus, document par document — la rafale qui dépasse le timeout serverless
-- et rend la page à zéro. C'est ce que fait la page actuelle, et c'est pourquoi elle demande un
-- mois à la fois.
--
-- ⚠️ NULL = JOUR PAS ENCORE RECONSTRUIT, distinct d'un jour sans paiement carte. Comme toutes
-- les colonnes de mesure de cette table, aucun DEFAULT : une journée non instrumentée n'a pas
-- « zéro euro en carte », elle n'a pas la mesure.
alter table public.daily_summary
  add column if not exists payments jsonb;

comment on column public.daily_summary.payments is
  'Reparti par moyen de paiement Vendus : {"Cartao": 123.40, "Dinheiro": 45.00}. En EUROS '
  'decimaux, contrairement a terminal_days qui est en centimes entiers — chaque table garde '
  'l''unite de sa source, la conversion se fait a UN seul endroit, dans l''endpoint.';
