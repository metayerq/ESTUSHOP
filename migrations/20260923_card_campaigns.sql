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
  -- L'empreinte du texte, qui relie cette ligne au registre `card_notices` (genre
  -- « campaign:<slug> »). ⚠️ DÉRIVÉE DU TEXTE ET NON TIRÉE AU HASARD : un identifiant neuf à
  -- chaque ouverture de page ferait repartir la campagne entière au second clic, après un
  -- rechargement ou un retour en arrière.
  slug        text not null,
  -- Le message EXACT tel qu'il est parti, préfixe et mention de désabonnement compris. Pas le
  -- brouillon tapé par le patron : ce que le client a lu.
  body        text not null,
  -- À qui : 'tous' | 'habitues' | 'absents' | 'depense' | 'solde'. Et le seuil du critère,
  -- s'il en a un — en EUROS pour 'depense', en points pour 'solde', en jours pour les autres.
  audience    text not null,
  audience_arg integer,
  -- ⚠️ LA PORTÉE EXIGÉE AU MOMENT DE L'ENVOI. Elle vaut 'points+news' pour toute campagne
  -- commerciale. L'écrire ici permet de répondre à « sur quelle base l'avez-vous contacté ? »
  -- des mois plus tard, sans reconstituer l'état du code de l'époque.
  scope       text not null,
  recipients  integer not null default 0,
  segments    integer not null default 0,
  sent_at     timestamptz not null default now(),
  by_role     text
);

-- ⚠️ AUCUNE CONTRAINTE D'UNICITÉ ICI, ET C'EST DÉLIBÉRÉ. Une campagne arrêtée au plafond puis
-- relancée écrit DEUX lignes : « 120 » puis « 30 ». C'est la vérité. Une contrainte unique sur le
-- texte aurait forcé une fusion, et l'archive aurait annoncé 30 destinataires là où 150 avaient
-- reçu le message — le contraire exact de ce que cette table existe pour faire.
--
-- L'anti-doublon n'est pas ici. Il est dans `card_notices`, destinataire par destinataire, où
-- une contrainte unique empêche réellement d'écrire deux fois à la même personne.
create index if not exists card_campaigns_date_idx on public.card_campaigns (sent_at desc);
create index if not exists card_campaigns_slug_idx on public.card_campaigns (slug);

-- ⚠️ SANS CETTE LIGNE, LA LECTURE RENVOIE ZÉRO LIGNE SANS ERREUR. Supabase active RLS par
-- défaut : la page d'historique afficherait « aucune campagne » après un envoi réussi, et on
-- chercherait le bogue dans le code d'affichage.
alter table public.card_campaigns disable row level security;
