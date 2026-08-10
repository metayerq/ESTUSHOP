-- Le cache journalier — table absente depuis toujours.
--
-- CE QUI S'EST PASSÉ
-- `daily_summary` n'existe dans AUCUN schéma du projet (vérifié via pg_class : zéro ligne).
-- Le code l'écrit et la lit depuis l'origine ; `_supa_get` renvoyant `[]` aussi bien pour
-- « table absente » que pour « aucune ligne », rien ne l'a jamais signalé.
--
-- Conséquence, invisible mais coûteuse : à chaque chargement, l'app conclut que le cache est
-- vide, rappelle Vendus sur toute la plage — un appel de détail PAR DOCUMENT, ~1250 à ce jour —
-- puis échoue à écrire le résultat. Les chiffres affichés restent JUSTES (ils viennent de
-- Vendus en direct), mais chaque page coûte ce qu'une journée entière devrait coûter une fois.
--
-- Rien de saisi à la main n'est en jeu : ce n'est qu'un cache, reconstructible intégralement.
--
-- ⚠️ `day` EST LA CLÉ PRIMAIRE, ce n'est pas cosmétique. Les écritures passent par un upsert
-- PostgREST en `merge-duplicates`, qui résout le conflit sur la clé primaire ou une contrainte
-- unique. Sans elle, chaque reconstruction EMPILERAIT des doublons au lieu de remplacer, et
-- les totaux doubleraient silencieusement.
--
-- ⚠️ AUCUN `DEFAULT` sur les colonnes de mesure. NULL doit rester distinguable de zéro : une
-- journée non instrumentée n'a pas « zéro personne » ni « zéro ticket à chaque heure », elle
-- n'a pas la mesure. Le code écarte ces jours ; un DEFAULT les ferait passer pour mesurés.

create table if not exists public.daily_summary (
  day            date primary key,

  -- Totaux du jour, avoirs déduits (voir _summarize_docs_items dans app.py).
  nb             integer,        -- tickets de VENTE : les avoirs ne comptent pas
  ca_ttc         numeric(12,2),
  ca_ht          numeric(12,2),

  -- COGS mesuré sur la seule part des ventes dont le prix d'achat est connu.
  -- `covered_ht` est le CA HT correspondant : leur rapport donne le taux de couverture,
  -- et c'est lui qui décide si la marge est mesurée ou extrapolée (seuil à 95 %).
  cogs_ht        numeric(12,2),
  covered_ht     numeric(12,2),
  items_ht       numeric(12,2),  -- CA HT de toutes les lignes, couvertes ou non

  multi_count    integer,        -- tickets à ≥ 2 LIGNES distinctes (≠ 2 articles)
  products       jsonb,          -- {"Cappuccino": {"qty": 12, "rev_ttc": .., "rev_ht": ..}}

  hours          jsonb,          -- {"9": 12, "20": 6} — heure locale, avoirs exclus
  covers         integer,        -- personnes ESTIMÉES : 1 boisson = 1 personne, plancher 1
  covers_capped  integer         -- tickets ramenés au plafond de 8 — à afficher, pas à masquer
);

comment on table public.daily_summary is
  'Cache journalier reconstruit depuis Vendus. Aucune saisie manuelle : '
  'POST /api/summary/rebuild le régénère intégralement.';

comment on column public.daily_summary.covers is
  'Personnes ESTIMÉES (1 boisson = 1 personne, plancher 1, plafond 8). '
  'Estimation haute, jamais un décompte. NULL = journée non instrumentée.';

-- ── RLS : ALIGNEZ-VOUS SUR VOS AUTRES TABLES ────────────────────────────────
-- Cette table est créée SANS RLS. Vos 16 autres tables fonctionnent déjà avec la clé que
-- l'app utilise ; alignez celle-ci sur elles plutôt que sur une supposition de ma part.
-- Pour voir ce qu'elles font :
--
--   select relname, relrowsecurity
--   from pg_class c join pg_namespace n on n.oid = c.relnamespace
--   where n.nspname = 'public' and relkind = 'r' order by relname;
--
-- Si les autres ont `relrowsecurity = true`, activez-la ici et recopiez leurs politiques :
--   alter table public.daily_summary enable row level security;
--
-- APRÈS CETTE MIGRATION
--   POST /api/summary/rebuild  {"from": "2026-05-27", "to": "<hier>"}
-- puis GET /api/summary/audit, qui doit revenir à zéro écart. Cette fois il aura un cache
-- à comparer — jusqu'ici il en comparait un qui n'existait pas.
