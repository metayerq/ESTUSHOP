-- Commissions reçues (popup inversé) : le chef encaisse lui-même et reverse
-- une commission par virement — revenu absent de Vendus, marge pure.
create table if not exists commissions_received (
  id         uuid primary key default gen_random_uuid(),
  date       date not null,
  label      text not null default '',
  amount     numeric not null check (amount > 0),
  created_at timestamptz not null default now()
);
alter table commissions_received disable row level security;
