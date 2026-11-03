-- Créneaux de PREP : un jour fermé aux clients peut quand même coûter des heures (prépa).
-- Un créneau coché « prep » signale qu'il ne sert pas les clients. Un jour dont TOUS les
-- créneaux sont « prep » est considéré fermé aux clients (hors jours ouverts / point mort),
-- mais ses heures sont comptées dans la masse du mois, réparties sur les jours ouverts.
--
-- Colonne rétro-compatible : `default false` → l'historique et le code d'avant se lisent
-- comme « pas de prep », donc aucun chiffre ne bouge tant que personne ne coche la case.
alter table shifts      add column if not exists prep boolean not null default false;
alter table shift_rules add column if not exists prep boolean not null default false;
