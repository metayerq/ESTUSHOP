-- Les réglages du programme de fidélité, et le journal de leurs changements.
--
-- ⚠️ POURQUOI EN BASE ET NON DANS LE CODE. Le barème est lu par DEUX applications : le
-- backoffice ESTUSHOP et la caisse Mesa. Deux constantes en dur, c'est la garantie qu'un jour
-- l'une sera modifiée et pas l'autre — et le client entendrait deux chiffres différents selon
-- qu'on regarde l'écran du comptoir ou celui du bureau. Une seule ligne, lue par les deux.
--
-- ⚠️ ET LA DATE DE LANCEMENT EST LE RÉGLAGE LE PLUS IMPORTANT DE CETTE TABLE. `card_visits`
-- enregistre depuis mai 2026, le programme date de septembre : sans elle, un habitué se présente
-- avec 1 400 points, soit vingt-neuf boissons dues, sur un programme dont il n'a jamais entendu
-- parler. Ce n'est pas une dette, c'est un accident de comptage.

create table if not exists public.card_settings (
  -- Une seule ligne, pour toujours. La contrainte est ce qui l'empêche de se dédoubler : deux
  -- lignes de réglages, et personne ne saurait laquelle fait foi.
  id                    smallint primary key default 1,

  -- Jour de lancement. Les paiements antérieurs ne donnent plus de points directement ; ils
  -- alimentent le crédit d'ancienneté. NULL = tout l'historique compte (l'état d'avant).
  start_date            date,

  -- Le crédit d'ancienneté : une part de ce qui a été dépensé AVANT le lancement, plafonnée.
  -- ⚠️ LE PLAFOND EST CE QUI REND LA RÈGLE TENABLE. À 10 % sans plafond, le client à 1 400 €
  -- d'historique reçoit encore trois boissons. Plafonné à 50 points, il en reçoit une — et la
  -- phrase au comptoir reste vraie pour tout le monde.
  legacy_rate_pct       integer not null default 0,
  legacy_cap_points     integer not null default 0,

  -- Le barème courant.
  threshold_points      integer not null default 50,
  expiry_months         integer not null default 12,

  -- Points offerts au moment où quelqu'un donne son numéro. ⚠️ C'EST LE RÉGLAGE À PLUS FORT
  -- LEVIER : à 8 € de ticket médian, 50 points demandent six ou sept visites, ce qui est long
  -- avant la première gratification. Un bonus de bienvenue paie le geste de donner son numéro.
  welcome_bonus_points  integer not null default 0,

  updated_at            timestamptz not null default now(),
  updated_by            text,

  constraint card_settings_une_seule_ligne check (id = 1)
);

insert into public.card_settings (id) values (1) on conflict (id) do nothing;

-- Le journal des changements.
--
-- ⚠️ CERTAINS DE CES RÉGLAGES TOUCHENT DES GENS QUI ONT DÉJÀ PAYÉ. Relever le seuil de 50 à 100
-- fait reculer tous les soldes d'un coup ; raccourcir l'expiration tue des points acquis. Ces
-- décisions doivent laisser une trace datée — pas pour surveiller qui que ce soit, mais pour
-- pouvoir répondre à « depuis quand ? » autrement que de mémoire.
create table if not exists public.card_settings_log (
  id         bigserial primary key,
  at         timestamptz not null default now(),
  by         text,
  -- L'état AVANT et APRÈS, en entier. Stocker seulement le champ modifié obligerait à rejouer
  -- tout le journal pour reconstituer un état — et un journal qu'on ne sait pas lire ne sert
  -- qu'à se donner bonne conscience.
  before     jsonb,
  after      jsonb,
  -- Motif libre. Obligatoire côté application : un changement sans raison écrite est un
  -- changement que personne ne saura expliquer dans six mois.
  reason     text
);

create index if not exists card_settings_log_at_idx on public.card_settings_log (at desc);
