-- Le NIF sur la carte : donné une fois, proposé à chaque facture.
--
-- C'est le seul champ qui fait gagner du temps à CHAQUE visite et non seulement à l'inscription :
-- neuf chiffres que le client n'a plus à réciter et que l'opérateur n'a plus à taper.
--
-- ⚠️ IL PART SUR UN DOCUMENT OPPOSABLE. Un NIF stocké faux se retrouverait sur toutes les
-- factures suivantes sans que personne ne le retape — d'où la clé de contrôle vérifiée à la
-- saisie, ici comme dans la caisse.
alter table public.loyalty_members add column if not exists fiscal_id text;
