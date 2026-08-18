-- Nationalité, facultative.
--
-- ⚠️ TEXTE LIBRE, PAS UNE LISTE FERMÉE. Une liste de pays serait plus propre à traiter, mais
-- elle obligerait à choisir « le » pays de quelqu'un qui en a deux, et à faire défiler deux cents
-- entrées au comptoir. Un champ libre se remplit en trois lettres et n'exclut personne.
--
-- La LANGUE, elle, est déjà collectée à l'ouverture de chaque table (PT/EN/FR/autre) et sans
-- friction : pour connaître la part de locaux, elle reste la mesure la plus fiable, parce qu'elle
-- couvre TOUS les clients assis et pas seulement les porteurs de carte.
alter table public.loyalty_members add column if not exists country text;
