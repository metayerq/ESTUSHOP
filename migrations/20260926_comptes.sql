-- LES COMPTES NOMINATIFS.
--
-- ⚠️ JUSQU'ICI, L'ACCÈS ÉTAIT UN MOT DE PASSE PARTAGÉ PAR RÔLE, dans une variable
-- d'environnement. Quatre conséquences, toutes silencieuses :
--   · on ne sait pas QUI s'est connecté — les journaux d'action ne portent qu'un rôle ;
--   · retirer l'accès à une personne oblige à changer le mot de passe de TOUTES celles qui
--     partagent son rôle, et à le leur redonner ;
--   · un mot de passe partagé se transmet par message et ne se reprend jamais ;
--   · ajouter la comptable demandait un déploiement, puisque le mot de passe vit dans
--     l'environnement.
--
-- ⚠️ LE MOT DE PASSE N'EST JAMAIS STOCKÉ. Seule son empreinte l'est (PBKDF2-HMAC-SHA256,
-- 200 000 tours, sel par compte). Une base lue par un tiers ne lui donne aucun accès — et
-- personne, pas même l'admin, ne peut retrouver le mot de passe de quelqu'un : il est montré
-- UNE fois à la création, puis perdu.

create table if not exists public.comptes (
  -- L'adresse sert d'identifiant. ⚠️ EN MINUSCULES À L'ÉCRITURE : « Ana@x.pt » et « ana@x.pt »
  -- sont la même personne, et deux lignes pour une personne, c'est un accès qu'on croit avoir
  -- retiré.
  email        text primary key,
  nom          text,
  -- 'admin' | 'accountant' | 'investor' | 'staff'
  role         text not null,
  -- PBKDF2-HMAC-SHA256. Format : « pbkdf2$<tours>$<sel_hex>$<empreinte_hex> ».
  empreinte    text not null,
  -- ⚠️ DÉSACTIVER PLUTÔT QUE SUPPRIMER. Un compte effacé emporte la trace de ce qu'il a fait ;
  -- un compte désactivé garde l'historique et ferme la porte, ce qui est la seule chose qu'on
  -- veut vraiment.
  actif        boolean not null default true,
  cree_le      timestamptz not null default now(),
  cree_par     text,
  derniere_connexion timestamptz
);

create index if not exists comptes_role_idx on public.comptes (role) where actif;

-- ⚠️ SANS CETTE LIGNE, LA LECTURE RENVOIE ZÉRO LIGNE SANS ERREUR. Supabase active RLS par
-- défaut : personne ne pourrait se connecter, et l'écran dirait « mot de passe incorrect » sur
-- un mot de passe juste — le pire message possible, puisqu'il envoie chercher au mauvais endroit.
alter table public.comptes disable row level security;
