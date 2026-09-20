-- LE NUMÉRO D'ESSAI — celui du patron, pour se relire avant d'écrire à tout le monde.
--
-- ⚠️ POURQUOI UN RÉGLAGE ET NON UN CHAMP DE SAISIE. Le bouton d'essai pourrait demander un
-- numéro à chaque fois : ce serait un chiffre de travers et un message publicitaire expédié à un
-- inconnu, au nom du café. Ici le numéro est posé UNE fois, dans un écran d'administration, et
-- le bouton d'essai n'a pas d'autre destination possible.
--
-- ⚠️ ET C'EST LE SEUL NUMÉRO QUE L'ENVOI D'ESSAI PEUT ATTEINDRE. La route de campagne ignore
-- délibérément tout numéro qu'on lui transmettrait : sans ça, quiconque obtiendrait le secret
-- pourrait s'en servir pour écrire à n'importe qui, un message à la fois.

alter table public.card_settings
  add column if not exists test_phone text;

comment on column public.card_settings.test_phone is
  'Numero E.164 qui recoit les envois d''essai. La SEULE destination possible du bouton Test — '
  'un envoi d''essai n''ecrit ni au registre ni au journal des campagnes.';
