-- Le bonus de bienvenue, et le journal des gestes manuels sur un client.
--
-- ⚠️ DEUX MANQUES QUI SE RESSEMBLENT : dans les deux cas, quelque chose qu'on croyait possible ne
-- l'était pas. Le bonus de bienvenue était réglable depuis une semaine et n'était branché nulle
-- part. Et un numéro mal tapé au comptoir n'avait aucune issue : la carte restait rattachée à
-- l'inconnu dont on avait saisi le numéro, qui recevait ses SMS et le lien vers sa page.

-- ── Le bonus de bienvenue ────────────────────────────────────────────────────────────────────
--
-- ⚠️ FIGÉ À LA VALEUR DU JOUR, PAS RECALCULÉ. Le relever de 20 à 50 le mois prochain ne doit pas
-- créditer rétroactivement ceux qui se sont inscrits avant : c'est la même règle que
-- `points_spent` sur une récompense. On ne réécrit pas l'histoire de quelqu'un qui a déjà été
-- servi — dans un sens comme dans l'autre.
--
-- ⚠️ ET IL EST PORTÉ PAR LE NUMÉRO, PAS PAR LA CARTE. Une seule fois par personne : celui qui
-- rattache ensuite son Apple Pay ne le touche pas deux fois.
alter table public.card_customers
  add column if not exists welcome_points integer not null default 0;

-- ── Le journal des gestes manuels ────────────────────────────────────────────────────────────
--
-- ⚠️ CES GESTES TOUCHENT LES POINTS DE QUELQU'UN. Délier une carte retire à un client tout ce
-- qu'elle portait ; effacer une fiche supprime un compte. Ce ne sont pas des consultations, ce
-- sont des décisions — et il faut pouvoir répondre à « qui, quand, pourquoi ? » autrement que de
-- mémoire, six mois plus tard, devant la personne concernée.
create table if not exists public.card_actions_log (
  id      bigserial primary key,
  at      timestamptz not null default now(),
  by      text,
  -- 'unlink' | 'relink' — un verbe, pas une phrase : c'est ce qui permet de compter.
  action  text not null,
  -- ⚠️ L'EMPREINTE, PAS LE NUMÉRO. Un journal d'incidents qui recopie les numéros de téléphone
  -- devient lui-même un fichier de contacts, conservé plus longtemps que le reste et que
  -- personne ne pense à purger. L'empreinte suffit à retrouver le compte.
  fp      text,
  -- L'état avant et après, en entier, SANS les numéros : quatre derniers chiffres seulement.
  before  jsonb,
  after   jsonb,
  -- Motif libre, obligatoire côté application.
  reason  text
);

create index if not exists card_actions_log_at_idx on public.card_actions_log (at desc);
create index if not exists card_actions_log_fp_idx on public.card_actions_log (fp);

-- ⚠️ SANS CES LIGNES, LA TABLE EST INUTILISABLE — ET ELLE ÉCHOUE EN SILENCE À LA LECTURE. Voir
-- le 19/09/2026 : RLS active sans politique renvoie zéro ligne au lieu d'une erreur, et
-- l'écriture ne casse que bien plus tard, avec un message que rien ne relie à la cause.
alter table public.card_actions_log disable row level security;
