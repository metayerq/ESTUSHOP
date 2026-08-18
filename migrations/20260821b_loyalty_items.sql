-- Ce que les membres achètent réellement.
--
-- ⚠️ LES ARTICLES REMONTAIENT DÉJÀ À CHAQUE ENCAISSEMENT — on comptait les boissons et on JETAIT
-- le reste. Or c'est la seule donnée neuve qui vaille : savoir que les fidèles prennent
-- systématiquement le flat white et jamais le batch brew change une carte, un réassort, un prix.
--
-- Et comme les montants, ELLE NE SE RECONSTRUIT PAS : chaque jour sans elle est perdu.
alter table public.loyalty_events add column if not exists items jsonb;
