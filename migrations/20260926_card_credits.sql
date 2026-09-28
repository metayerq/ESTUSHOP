-- ══════════════════════════════════════════════════════════════════════════════════════════════
-- LES POINTS OFFERTS HORS DÉPENSE — BIENVENUE, PARRAINAGE, GESTES COMMERCIAUX.
--
-- ⚠️ CETTE TABLE EST ÉCRITE DEPUIS SEPTEMBRE ET N'A JAMAIS EU DE MIGRATION. Le commit qui l'a
-- introduite (« Parrainage, côté Mesa », 23/09) ne touche aucun fichier SQL. Elle a donc été
-- créée à la main, ou pas du tout — et personne ne peut le dire depuis les dépôts.
--
-- ⚠️ ET TOUTE LA PROTECTION CONTRE LE DOUBLE PAIEMENT REPOSE SUR SON UNICITÉ. `offrirPoints`
-- (apps/pos/lib/server/loyaltyStore.ts) fait un POST nu et attend un **409** : le commentaire du
-- code est explicite — « une vérification "ai-je déjà crédité ?" perdrait la course entre deux
-- livraisons simultanées ; la contrainte d'unicité, non ». Revolut redélivre ses webhooks toutes
-- les dix minutes. Sans index unique sur `ref`, deux livraisons simultanées du premier passage
-- d'un filleul créditent DEUX FOIS le filleul et DEUX FOIS le parrain — sans erreur, sans trace,
-- et `credites.length > 0` des deux côtés fait croire que tout s'est bien passé.
--
-- Ce fichier est rejouable : il crée ce qui manque et ne touche pas à ce qui existe.
-- ══════════════════════════════════════════════════════════════════════════════════════════════

create table if not exists public.card_credits (
  -- ⚠️ `ref` EST LA CLÉ D'IDEMPOTENCE, D'OÙ LA CLÉ PRIMAIRE. Les deux formes utilisées par le
  -- parrainage sont `referral:<numéro du filleul>` et `referral-host:<numéro du filleul>` : elles
  -- pendent au FILLEUL, qui n'est parrainé qu'une fois. Même régime que `card_rewards.ref`.
  ref        text primary key,
  phone      text not null,
  points     integer not null check (points > 0),
  reason     text not null default '',
  -- ⚠️ `default now()` EST OBLIGATOIRE, PAS DU CONFORT. `offrirPoints` n'écrit jamais `ts` — la
  -- lecture, elle, trie dessus (`select=ts,points,reason … order=ts.asc`) et c'est de cette date
  -- que court l'expiration à douze mois. Sans défaut, la colonne serait nulle et les crédits
  -- n'expireraient jamais, ou casseraient le calcul.
  ts         timestamptz not null default now(),
  created_at timestamptz not null default now()
);

-- Le compteur d'un client se lit par numéro, dans l'ordre d'acquisition : les points les plus
-- anciens se consomment d'abord.
create index if not exists card_credits_phone_idx on public.card_credits (phone, ts);

-- ⚠️ LE FILET POUR UNE TABLE DÉJÀ CRÉÉE À LA MAIN, SANS CONTRAINTE. `create table if not exists`
-- ne fait rien si la table est là — y compris si elle est là SANS unicité sur `ref`, qui est
-- précisément le cas dangereux. Cet index la pose alors, et ne fait rien si elle existe déjà.
-- S'il échoue sur des doublons préexistants, c'est l'information la plus utile de ce fichier :
-- des crédits ont déjà été payés deux fois, et il faut les nettoyer avant de poser la contrainte.
create unique index if not exists card_credits_ref_uniq on public.card_credits (ref);

-- Même régime que ses voisines `card_*` : accès par la clé de service, jamais par le navigateur.
alter table public.card_credits disable row level security;
