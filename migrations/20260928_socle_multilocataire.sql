-- ══════════════════════════════════════════════════════════════════════════════════════════
-- LE SOCLE MULTI-LOCATAIRE, POSÉ DANS LA BASE D'ESTUDANTINA
--
-- Décidé le 28/09/2026 : un seul projet Supabase pour tous les cafés, plutôt qu'un projet par
-- client. À quarante cafés, un projet chacun coûterait 400 à 480 $/mois de compute pour des
-- bases quasi vides, contre 25 $ à plat — et chaque migration deviendrait quarante exécutions
-- à orchestrer, avec quarante états de schéma possiblement divergents.
--
-- ⚠️ ET C'EST CE PROJET-CI, PAS UN NEUF. Les données d'Estudantina y sont déjà : recettes,
-- ingrédients, factures scannées, comptages. Le locataire n°1 n'a donc rien à migrer — ce qui
-- supprime l'étape la plus fragile de tout le chantier.
--
-- ⚠️ CE FICHIER NE TOUCHE À AUCUNE TABLE EXISTANTE. Il crée. Les noms ont été vérifiés contre
-- les migrations d'ESTUSHOP : `establishments`, `memberships`, `is_member`, `set_updated_at`,
-- `create_establishment` et `establishment_by_slug` n'y existent nulle part. Rien n'est écrasé.
--
-- À coller dans l'éditeur SQL de Supabase, projet ESTUSHOP.
-- ══════════════════════════════════════════════════════════════════════════════════════════

-- ── Les établissements ─────────────────────────────────────────────────────────────────────
create table if not exists public.establishments (
  id                        uuid primary key default gen_random_uuid(),
  name                      text not null,
  slug                      text,
  plan                      text not null default 'free' check (plan in ('free', 'pro')),

  business_type             text,
  country                   text not null default 'PT',
  city                      text,
  seats                     int,
  referral_source           text,

  -- ⚠️ LA CLÉ VENDUS NE VIT ICI QUE CHIFFRÉE (AES-256-GCM). La clé maître est dans
  -- `MESA_ENCRYPTION_KEY`, côté Vercel — jamais en base. Deux magasins indépendants : une
  -- fuite de cette table ne donne que des ciphertexts. C'est aussi pourquoi on n'utilise pas
  -- Supabase Vault, où la clé vivrait à côté des données qu'elle protège.
  --
  -- Cette clé donne le droit d'ÉMETTRE DES FACTURES au nom du café. Une fuite en clair n'est
  -- pas un bogue, c'est un incident fiscal chez un tiers.
  vendus_api_key_enc        text,
  vendus_key_last4          text,
  vendus_connected_at       timestamptz,

  -- ⚠️ ÉMETTRE ET LIRE SONT DEUX CHOSES DIFFÉRENTES. On n'émet que sur UNE caisse : c'est elle
  -- qui porte la série fiscale courante. On peut vouloir en LIRE plusieurs, le jour où l'on
  -- change de caisse et que l'historique ne doit pas disparaître de l'écran. Deux colonnes
  -- plutôt qu'une liste ordonnée : dans une liste, réordonner changerait silencieusement la
  -- caisse d'émission, donc la numérotation légale.
  vendus_register_id        bigint,
  vendus_extra_register_ids bigint[] not null default '{}',

  -- ⚠️ LE DÉFAUT EST `tests`, ET IL NE PEUT PAS EN ÊTRE AUTREMENT. Un café fraîchement inscrit
  -- n'a rien prouvé : sa clé marche peut-être en lecture seule, sa caisse est peut-être la
  -- mauvaise. Démarrer en `normal` ferait émettre de VRAIS documents fiscaux — dans sa série,
  -- sous son NIF — au premier essai d'un écran qu'il découvre.
  vendus_mode               text not null default 'tests' check (vendus_mode in ('tests','normal')),
  payment_method_ids        jsonb not null default '{}'::jsonb,

  -- ⚠️ LA CAISSE N'AUTHENTIFIE PAS UNE PERSONNE, ELLE AUTHENTIFIE UN ÉTABLISSEMENT. Un compte
  -- nominatif par serveur n'a aucun sens sur un iPad partagé : on le contournerait en laissant
  -- la session ouverte. Le patron se connecte au backoffice avec son compte ; le staff tape le
  -- PIN. Haché, jamais en clair — un PIN lisible finit dans un export ou une capture d'écran.
  pos_pin_hash              text,

  -- ⚠️ TOUT EST ÉTEINT PAR DÉFAUT. La fidélité est soudée aux empreintes du webhook Revolut ;
  -- les terminaux supposent un contrat ; le SMS suppose Twilio. Un café qui s'inscrit seul n'a
  -- rien de tout ça, et un drapeau allumé serait un écran qui promet ce que personne n'a
  -- branché. Clés : loyalty, terminal, mbway, sms, backoffice.
  features                  jsonb not null default '{}'::jsonb,

  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

-- ⚠️ LE SLUG EST CONTRAINT, ET PAS PAR COQUETTERIE. Il entre dans la charge signée du cookie de
-- session (`apps/pos/lib/auth.ts`), séparée par un point. Autoriser un point ou une majuscule
-- rendrait deux locataires capables de produire la même charge — donc le cookie de l'un valide
-- chez l'autre. La contrainte EST une mesure de sécurité.
create unique index if not exists idx_establishments_slug on public.establishments(slug);

alter table public.establishments drop constraint if exists establishments_slug_format;
alter table public.establishments add constraint establishments_slug_format
  check (slug is null or slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$');

-- ⚠️ PAS DE SECRET DE COOKIE PAR ÉTABLISSEMENT, DÉLIBÉRÉMENT. Le stocker ici donnerait, le jour
-- d'une fuite, le pouvoir de forger la session de n'importe quelle caisse. Le secret reste
-- unique dans l'env Vercel ; c'est la CHARGE signée qui porte le slug.

-- ── Les membres ────────────────────────────────────────────────────────────────────────────
create table if not exists public.memberships (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  establishment_id uuid not null references public.establishments(id) on delete cascade,
  -- `accountant` existe déjà côté ESTUSHOP (mot de passe dédié, accès comptable en lecture).
  -- Le porter ici évite qu'un comptable finisse avec un compte `manager` « en attendant ».
  role             text not null default 'owner'
                   check (role in ('owner','manager','investor','accountant','staff')),
  created_at       timestamptz not null default now(),
  unique (user_id, establishment_id)
);

create index if not exists idx_memberships_user  on public.memberships(user_id);
create index if not exists idx_memberships_estab on public.memberships(establishment_id);

-- ── updated_at ─────────────────────────────────────────────────────────────────────────────
-- ⚠️ PRÉFIXÉ `mesa_`. Un `set_updated_at` générique écraserait sans bruit une fonction du même
-- nom dans un projet qu'on ne connaît pas entièrement. Vérifié absent, préfixé quand même.
create or replace function public.mesa_set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_establishments_updated_at on public.establishments;
create trigger trg_establishments_updated_at
  before update on public.establishments
  for each row execute function public.mesa_set_updated_at();

-- ── RLS ────────────────────────────────────────────────────────────────────────────────────
-- SECURITY DEFINER pour éviter la récursion quand les policies l'appellent.
create or replace function public.is_member(p_establishment uuid)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from public.memberships m
    where m.establishment_id = p_establishment and m.user_id = auth.uid()
  );
$$;

grant select, update on public.establishments to authenticated;
grant select          on public.memberships   to authenticated;

alter table public.establishments enable row level security;
alter table public.memberships   enable row level security;

drop policy if exists "establishments_select_members" on public.establishments;
create policy "establishments_select_members"
  on public.establishments for select using (public.is_member(id));

drop policy if exists "establishments_update_members" on public.establishments;
create policy "establishments_update_members"
  on public.establishments for update
  using (public.is_member(id)) with check (public.is_member(id));

drop policy if exists "memberships_select_own" on public.memberships;
create policy "memberships_select_own"
  on public.memberships for select using (user_id = auth.uid());

-- ⚠️ AUCUNE POLICY NE LAISSE LIRE `vendus_api_key_enc` DEPUIS LE CLIENT. La colonne est dans la
-- table lisible par ses membres : c'est la route serveur qui ne la sélectionne jamais, et le
-- client admin qui la déchiffre. Une policy par colonne n'existe pas en Postgres — la
-- discipline est dans le code, et c'est une faiblesse à connaître.

-- ── Créer un établissement ─────────────────────────────────────────────────────────────────
create or replace function public.create_establishment(
  p_name text, p_business_type text default null, p_country text default 'PT',
  p_city text default null, p_seats int default null, p_referral_source text default null
) returns uuid language plpgsql security definer set search_path = public as $$
declare v_id uuid;
begin
  if auth.uid() is null then raise exception 'not authenticated'; end if;
  insert into public.establishments (name, business_type, country, city, seats, referral_source)
  values (p_name, p_business_type, p_country, p_city, p_seats, p_referral_source)
  returning id into v_id;
  insert into public.memberships (user_id, establishment_id, role)
  values (auth.uid(), v_id, 'owner');
  return v_id;
end;
$$;

revoke all     on function public.create_establishment(text,text,text,text,int,text) from public;
grant  execute on function public.create_establishment(text,text,text,text,int,text) to authenticated;

-- ── Résoudre une adresse ───────────────────────────────────────────────────────────────────
-- ⚠️ APPELÉE PAR LA CAISSE AVANT TOUTE SESSION. Elle ne rend donc QUE ce qui n'est pas secret :
-- ni la clé chiffrée, ni le hachage du PIN. Ceux-là se lisent avec le client admin, dans une
-- route serveur, une fois qu'on sait à qui l'on parle.
create or replace function public.establishment_by_slug(p_slug text)
returns table (
  id uuid, name text, slug text, plan text,
  vendus_register_id bigint, vendus_extra_register_ids bigint[],
  vendus_mode text, payment_method_ids jsonb, features jsonb
) language sql security definer stable set search_path = public as $$
  select e.id, e.name, e.slug, e.plan, e.vendus_register_id, e.vendus_extra_register_ids,
         e.vendus_mode, e.payment_method_ids, e.features
  from public.establishments e where e.slug = p_slug
$$;

revoke all     on function public.establishment_by_slug(text) from public;
grant  execute on function public.establishment_by_slug(text) to service_role;

-- ── Estudantina, locataire n°1 ─────────────────────────────────────────────────────────────
-- ⚠️ SANS CLÉ VENDUS NI PIN, ET C'EST VOULU. La caisse d'Estudantina continue de lire sa
-- configuration dans l'environnement Vercel — rien ne change pour elle aujourd'hui. Cette
-- ligne existe pour que son slug soit réservé et que les tables métier puissent s'y rattacher
-- quand on ajoutera `establishment_id`. Y recopier la clé maintenant créerait un second endroit
-- où elle vit, sans que personne l'utilise.
insert into public.establishments (name, slug, country, city, vendus_mode, features)
values ('Estudantina', 'estudantina', 'PT', 'Lisboa', 'normal',
        '{"loyalty":true,"terminal":true,"mbway":true,"sms":true,"backoffice":true}'::jsonb)
on conflict do nothing;

-- ── Ce qu'on n'a PAS fait ──────────────────────────────────────────────────────────────────
-- Pas de colonne `establishment_id` sur les tables métier (card_visits, ingredients, recipes,
-- fatura_invoices…). Elles appartiennent aujourd'hui à Estudantina et à elle seule ; les
-- rattacher demande de décider, table par table, ce qui se partage et ce qui ne se partage pas
-- — et surtout d'écrire les filtres AVANT que la colonne existe, faute de quoi on aurait une
-- colonne que personne ne lit et l'illusion d'une isolation.
