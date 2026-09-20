-- L'ENCAISSEMENT TERMINAL DU JOUR, EN SOURCE COMPTABLE.
--
-- ⚠️ POURQUOI PAS `card_visits`. Cette table-là sert la FIDÉLITÉ : elle écarte les paiements
-- sans derniers chiffres (Tap to Pay n'en rattache aucun) et n'enregistre jamais les
-- remboursements. Mesuré sur juillet 2026 : 605 lignes pour 606 paiements réglés, 13,44 €
-- manquants. Sommer `card_visits` et appeler ça « encaissé » sous-compte en silence.
--
-- ⚠️ ET LES POURBOIRES SONT UNE COLONNE À PART, parce qu'ils ne sont PAS dans le montant des
-- ventes : `payment.amount` exclut `tip_amount` — vérifié sur juillet 2026 (6 078,11 € côté API
-- contre 6 091,55 € de ventes et 99,35 € de pourboires au relevé). Les additionner ferait
-- offrir des points sur les pourboires le jour où quelqu'un réutilisera cette table.

create table if not exists public.terminal_days (
  day          date primary key,
  -- Ventes, pourboires exclus. En CENTIMES entiers, comme `card_visits.amount`.
  gross_cents  integer not null default 0,
  tips_cents   integer not null default 0,
  -- ⚠️ NULL TANT QUE LE RELEVÉ N'EST PAS ARRIVÉ, jamais 0 : « pas encore connu » et
  -- « aucun frais » mènent à deux lectures opposées du même écran. Cette colonne reste vide
  -- trois semaines par mois, et c'est voulu.
  fees_cents   integer,
  tx           integer not null default 0,
  refunds_cents integer not null default 0,
  updated_at   timestamptz not null default now()
);

-- ⚠️ SANS CETTE LIGNE, LA LECTURE RENVOIE ZÉRO LIGNE SANS ERREUR. Supabase active RLS par
-- défaut : la page afficherait « aucun encaissement » sur une table correctement remplie.
alter table public.terminal_days disable row level security;
