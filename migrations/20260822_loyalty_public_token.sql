-- Adresse personnelle d'un client pour consulter sa carte.
--
-- ⚠️ UN JETON, PAS LE NUMÉRO. Une adresse en /carte/47 laisserait n'importe qui lire le prénom
-- et le solde de tous les membres en énumérant 1, 2, 3… Le numéro est fait pour être RÉCITÉ au
-- comptoir ; il ne peut donc pas servir de secret.
--
-- Le jeton est long, aléatoire, et ne donne accès qu'à une seule fiche — en lecture, et
-- seulement au prénom, au numéro et au solde.
alter table public.loyalty_members add column if not exists public_token text;
create unique index if not exists loyalty_members_public_token_idx
  on public.loyalty_members (public_token) where public_token is not null;
