-- Fidélité : dix boissons, la onzième offerte.
--
-- POURQUOI ON COMPTE DES BOISSONS ET NON DES EUROS
-- Un livre à 25 € laisse 10 € de marge (40 %) ; un café à 4 € en laisse 3,30 (82 %). Avec
-- « 1 € = 1 point », un seul livre vaudrait la moitié d'une récompense sur des euros deux fois
-- moins margés : les cafés offerts seraient financés par la librairie. Compter les boissons
-- adosse la récompense à ce qui la finance — et « dix boissons, la onzième offerte » se comprend
-- sans explication au comptoir.

create table if not exists public.loyalty_members (
  -- Le numéro que le client récite. SÉQUENTIEL et court : le premier inscrit est le 1.
  -- ⚠️ JAMAIS RÉEMPLOYÉ, même après une suppression : recycler un numéro rattacherait les points
  -- d'hier à quelqu'un d'autre.
  number      integer primary key,
  -- Prénom seul. Il sert à CONFIRMER de visu que le bon numéro a été tapé — 47 au lieu de 74
  -- crédite la mauvaise personne. Pas de nom de famille, pas d'adresse : rien qui ne serve.
  first_name  text not null,
  -- Boissons accumulées depuis la dernière récompense. Jamais négatif.
  drinks      integer not null default 0,
  -- Récompenses déjà offertes, cumulées. Sert à mesurer le coût du programme.
  rewards     integer not null default 0,
  -- Téléphone : FACULTATIF et vide par défaut. Ajouté seulement si le client le propose et
  -- l'accepte. Tant qu'il est nul, il n'y a aucun fichier de contacts à protéger.
  phone       text,
  consent_at  timestamptz,
  created_at  timestamptz not null default now(),
  last_seen   timestamptz
);

-- Journal des mouvements. ⚠️ C'EST LUI QUI PERMET DE TRANCHER UN LITIGE : « j'avais neuf cafés »
-- ne se discute pas contre un solde nu. Chaque crédit et chaque récompense y laisse une ligne.
create table if not exists public.loyalty_events (
  id         bigserial primary key,
  number     integer not null references public.loyalty_members(number) on delete cascade,
  -- 'credit' (boissons ajoutées) ou 'reward' (récompense offerte).
  kind       text not null,
  drinks     integer not null,
  -- Numéro du document Vendus, quand il y en a un. Absent sur une correction manuelle.
  document   text,
  at         timestamptz not null default now()
);

create index if not exists loyalty_events_number_idx on public.loyalty_events (number, at desc);
