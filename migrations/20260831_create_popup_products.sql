-- Produits popup (chef partenaire) : la commission sur le TTC est la marge
-- brute de Quentin ; le chef facture le restant HT. Voir
-- docs/superpowers/specs/2026-08-31-popup-products-design.md
create table if not exists popup_products (
  product_name   text primary key,
  commission_pct numeric not null check (commission_pct >= 0 and commission_pct < 100),
  updated_at     timestamptz not null default now()
);
alter table popup_products disable row level security;
