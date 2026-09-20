-- Le registre des messages envoyés d'office.
--
-- ⚠️ SANS LUI, UN CRON REJOUÉ ÉCRIT DEUX FOIS À TOUT LE MONDE. Un délai dépassé, une relance de
-- Vercel, un clic de trop sur « lancer maintenant » : la fonction repart du début, recalcule la
-- même liste, et renvoie les mêmes SMS. Personne ne s'en plaint à la première fois — on s'en
-- plaint à la troisième, et il est trop tard pour les rappeler.
--
-- C'est la pièce la moins visible de cette fonctionnalité et la plus importante.

create table if not exists public.card_notices (
  id          bigserial primary key,
  -- Le destinataire. ⚠️ LE NUMÉRO ET NON L'EMPREINTE : un client a plusieurs cartes, il n'a
  -- qu'un téléphone, et c'est le téléphone qui reçoit.
  phone       text not null,
  -- 'expiry' aujourd'hui ; d'autres campagnes viendront, et elles doivent se compter à part.
  kind        text not null,
  /*
   * ⚠️ LA CLÉ NATURELLE DE L'IDEMPOTENCE. Un avertissement porte sur un LOT de points qui meurt
   * à une date précise : « prévenu que ses points du 22/09 expirent » est un fait qui ne se
   * répète pas. Utiliser seulement le jour d'envoi laisserait passer un second message le
   * lendemain ; utiliser seulement le numéro empêcherait de le prévenir l'année suivante.
   */
  expires_on  date not null,
  -- Combien de points étaient annoncés. Sert à relire une campagne sans la rejouer.
  points      integer,
  sent_at     timestamptz not null default now(),

  -- ⚠️ LA GARANTIE EST DANS LA BASE, PAS DANS LE CODE. Une vérification applicative laisse
  -- passer deux exécutions simultanées — et un cron qui traîne est exactement ce qui se fait
  -- relancer pendant qu'il tourne encore.
  constraint card_notices_une_fois unique (phone, kind, expires_on)
);

create index if not exists card_notices_phone_idx on public.card_notices (phone, sent_at desc);

alter table public.card_notices disable row level security;
