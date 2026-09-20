-- LE JOURNAL DES CAMPAGNES — ce qui a été écrit, à qui, et par qui.
--
-- ⚠️ UN ENVOI DE MASSE SANS TRACE EST INDÉFENDABLE. « Vous m'avez écrit le 3 octobre » n'a de
-- réponse que si l'on retrouve le texte exact, la date, le nombre de destinataires et le critère
-- qui les a désignés. Sans cette table, la seule preuve serait la facture Twilio — qui dit
-- combien, jamais quoi.
--
-- ⚠️ ET CE N'EST PAS LE REGISTRE ANTI-DOUBLON. Celui-là est `card_notices`, dont la contrainte
-- unique empêche d'écrire deux fois à la même personne. Ici on garde le compte rendu de la
-- campagne ; là-bas on garde qui l'a reçue. Les deux sont nécessaires et ne font pas le même
-- travail.

create table if not exists public.card_campaigns (
  id          bigserial primary key,
  -- La clé d'idempotence : dérivée du TEXTE. ⚠️ VOLONTAIREMENT PAS UN IDENTIFIANT TIRÉ AU
  -- HASARD. Un identifiant neuf à chaque ouverture de page ferait repartir la campagne entière
  -- au second clic, après un rechargement ou un retour en arrière. Le même texte le même jour
  -- est, en pratique, toujours un doublon.
  slug        text not null,
  -- Le message EXACT tel qu'il est parti, préfixe et mention de désabonnement compris. Pas le
  -- brouillon tapé par le patron : ce que le client a lu.
  body        text not null,
  -- À qui : 'tous' | 'habitues' | 'absents'. Le paramètre du critère, s'il en a un.
  audience    text not null,
  audience_arg integer,
  -- ⚠️ LA PORTÉE EXIGÉE AU MOMENT DE L'ENVOI. Elle vaut 'points+news' pour toute campagne
  -- commerciale. L'écrire ici permet de répondre à « sur quelle base l'avez-vous contacté ? »
  -- des mois plus tard, sans reconstituer l'état du code de l'époque.
  scope       text not null,
  recipients  integer not null default 0,
  segments    integer not null default 0,
  sent_at     timestamptz not null default now(),
  by_role     text,

  -- Deux envois du même texte le même jour sont un doublon, pas une campagne.
  constraint card_campaigns_une_fois unique (slug)
);

create index if not exists card_campaigns_date_idx on public.card_campaigns (sent_at desc);

-- ⚠️ SANS CETTE LIGNE, LA LECTURE RENVOIE ZÉRO LIGNE SANS ERREUR. Supabase active RLS par
-- défaut : la page d'historique afficherait « aucune campagne » après un envoi réussi, et on
-- chercherait le bogue dans le code d'affichage.
alter table public.card_campaigns disable row level security;
