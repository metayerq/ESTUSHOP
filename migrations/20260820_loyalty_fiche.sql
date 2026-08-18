-- Fiche client : e-mail, et suppression qui n'efface pas le numéro.
--
-- ⚠️ POURQUOI `status` ET NON UN VRAI DELETE. Le prochain numéro est calculé comme « le plus
-- grand déjà attribué, plus un ». Supprimer le DERNIER membre libérerait donc son numéro pour
-- le suivant : deux personnes réciteraient le même au comptoir, à des mois d'intervalle, et les
-- points de la première iraient à la seconde. Un trou au milieu ne pose pas ce problème — ce qui
-- explique qu'il soit passé inaperçu.
--
-- La suppression ANONYMISE : prénom, téléphone et e-mail sont effacés (c'est ce qu'exige une
-- demande d'effacement), la ligne reste pour réserver le numéro, et l'historique demeure sans
-- plus identifier personne.
alter table public.loyalty_members add column if not exists email  text;
alter table public.loyalty_members add column if not exists status text;
alter table public.loyalty_members add column if not exists notes  text;
alter table public.loyalty_members add column if not exists birth_day   integer;
alter table public.loyalty_members add column if not exists birth_month integer;
