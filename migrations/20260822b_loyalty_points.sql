-- Points dépensés, pour la piste « 1 point par euro ».
--
-- ⚠️ LES POINTS NE SONT PAS STOCKÉS : ils se DÉDUISENT de `spent_cents`, déjà cumulé à chaque
-- vente. Un second compteur qu'il faudrait tenir en parallèle finirait par diverger du premier,
-- et personne ne saurait lequel croire. Points = euros dépensés − points déjà consommés.
--
-- Seule la CONSOMMATION mérite sa colonne, parce qu'elle ne se déduit de rien.
alter table public.loyalty_members add column if not exists points_spent integer;
