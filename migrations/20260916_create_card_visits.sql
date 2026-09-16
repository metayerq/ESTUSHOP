-- Visites carte du terminal Revolut, pseudonymisées (revolut_merchant.py).
-- fp = SHA-256 salé de (4 derniers chiffres + libellé puce) — jamais de
-- numéro de carte en clair, jamais de nom. pid = identifiant du paiement
-- Revolut : la reconstruction est rejouable sans doublon.
create table if not exists card_visits (
  pid     text primary key,
  day     date not null,
  ts      timestamptz not null,
  amount  integer not null,          -- centimes
  fp      text not null,
  label   text not null default ''
);
create index if not exists card_visits_day_idx on card_visits (day);
create index if not exists card_visits_fp_idx  on card_visits (fp);
alter table card_visits disable row level security;
