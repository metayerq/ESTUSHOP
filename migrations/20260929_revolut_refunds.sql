-- Les devoluções du terminal, qui manquaient.
--
-- L'import du Merchant reconciliation statement ne retenait que les lignes
-- `Type = Settlement`. Le même fichier contient aussi des `Refund` — 41 sur
-- septembre 2026, soit 230,90 € — qui ne sont jamais entrés nulle part.
-- Conséquence : `gross` surestimait les ventes carte du montant exact des
-- remboursements, et la réconciliation Vendus ↔ Revolut ne pouvait pas tomber
-- juste. La comptable voyait l'écart sans pouvoir le nommer.
--
-- ⚠️ STOCKÉ EN VALEUR POSITIVE, comme `fees`. Le CSV les donne en négatif ;
-- l'import prend la valeur absolue. Les formules soustraient, elles
-- n'additionnent pas un négatif — c'est plus dur à lire de travers.
--
-- ⚠️ ET SUR LA DATE DE RÈGLEMENT, pas de capture : un remboursement n'a PAS
-- de date de capture dans le fichier Revolut (vérifié : 0 sur 41 lignes).
-- C'est aussi la date juste comptablement — un remboursement est un événement
-- de son propre jour, pas de celui de la vente qu'il annule.

alter table public.revolut_days
  add column if not exists refunds numeric not null default 0;

comment on column public.revolut_days.refunds is
  'Devolucoes reglees ce jour, en valeur POSITIVE. Base date de REGLEMENT '
  '(un remboursement n''a pas de date de capture). Ventas cartao = gross - tips - refunds.';
