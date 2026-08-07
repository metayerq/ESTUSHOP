-- Heures de passage en caisse, conservées jour par jour.
--
-- POURQUOI
-- L'heure est sur chaque document Vendus (`local_time`), mais le cache journalier ne la
-- gardait pas : l'affluence horaire n'était visible que sur la journée en cours, et redemander
-- l'historique à Vendus coûte un appel par document (~1250 aujourd'hui).
--
-- Les données du café montrent DEUX pics distincts — 50 % des tickets entre 5h et 12h, puis
-- deux blocs de 25 % l'après-midi et le soir. Ce sont deux clientèles, pas une seule étalée,
-- et c'est le seul signal client riche qui ne demande AUCUNE saisie supplémentaire en caisse.
--
-- FORME
-- {"9": 12, "11": 8, "20": 6} — clé = heure locale de Lisbonne en base 10 sans zéro initial,
-- valeur = nombre de tickets. Les avoirs sont exclus : une annulation n'est pas une visite.
--
-- ⚠️ NULL N'EST PAS UN OBJET VIDE. Une ligne écrite avant cette migration n'a pas « zéro
-- ticket à chaque heure », elle n'a pas la mesure. Le code écarte ces jours et annonce sur
-- combien de journées la répartition porte (`days_measured`) — sans quoi un historique à
-- moitié instrumenté se lirait comme un historique complet. Ne pas mettre de DEFAULT '{}'.
--
-- APRÈS AVOIR EXÉCUTÉ CECI
-- Les nouvelles journées se remplissent seules. Pour l'historique, un passage unique :
--   POST /api/summary/rebuild   {"from": "2026-05-27", "to": "<hier>"}
-- Il rappelle Vendus document par document — comptez quelques minutes, et faites-le hors
-- service. Puis GET /api/summary/audit doit rester à zéro écart : le rebuild ne change ni le
-- CA ni le nombre de tickets, il ne fait qu'ajouter les heures.
--
-- Le code sait vivre SANS cette colonne : _upsert_summary réessaie sans le champ si Supabase
-- le refuse (même repli que supplier, waste_pct et category). Déployer avant d'exécuter ce
-- fichier ne casse donc rien — on perd seulement les heures.

alter table public.daily_summary
  add column if not exists hours jsonb;

comment on column public.daily_summary.hours is
  'Tickets par heure locale de Lisbonne, avoirs exclus : {"9": 12, "20": 6}. '
  'NULL = journée non instrumentée (antérieure à la migration), ce qui est différent '
  'd''une journée sans vente.';
