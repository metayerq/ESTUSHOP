-- LES RÉGLAGES DE LA PLATEFORME, EN BASE.
--
-- ⚠️ PREMIER USAGE : L'ORGANISATION DU MENU. Le rangement était écrit en dur, et il avait tort —
-- « Dépenses » vivait sous « Caisse » alors que ce sont des achats datés qui pèsent sur le mois,
-- pas sur le tiroir. Corriger demandait un déploiement ; le prochain désaccord aussi.
--
-- ⚠️ UNE LIGNE PAR RÉGLAGE, ET LA VALEUR EN JSON. Une colonne par réglage voudrait dire une
-- migration à chaque idée. Le prix est qu'aucune contrainte de base ne valide le contenu : c'est
-- `menu.py` qui le fait, et il traite toute valeur abîmée comme une absence.
--
-- ⚠️ ET UN RÉGLAGE ABSENT N'EST JAMAIS UNE PANNE. Table vide = comportement par défaut, celui du
-- code. C'est ce qui permet de déployer ceci sans rien changer à l'écran le jour même, et de
-- réparer une configuration cassée en effaçant simplement sa ligne.

create table if not exists public.reglages (
  cle       text primary key,
  valeur    jsonb not null,
  maj_le    timestamptz not null default now(),
  maj_par   text
);

comment on table public.reglages is
  'Réglages de la plateforme. Une ligne par clé, valeur en JSON. Absence = valeur par défaut du code.';

-- ⚠️ SANS CETTE LIGNE, LA LECTURE RENVOIE ZÉRO LIGNE SANS ERREUR. Supabase active RLS par
-- défaut : le menu retomberait silencieusement sur ses valeurs d'usine, et on chercherait le
-- bogue dans l'écran de réglage — qui enregistrerait pourtant correctement.
alter table public.reglages disable row level security;
