-- Origine des couverts : mesurés (note du POS) ou estimés (boissons).
--
-- Le POS demande le nombre de personnes à chaque ouverture de table et l'écrit sur la note du
-- document (`pax:N`). Le dashboard préfère cette MESURE quand elle existe, et retombe sur son
-- estimation par les boissons sinon. Sans ces deux compteurs, un total à 90 % estimé se lirait
-- comme un comptage — ce qui annulerait le bénéfice de la remontée.
--
-- Sans DEFAULT, délibérément : une ligne écrite avant cette migration n'a pas « zéro document
-- mesuré », elle n'en sait rien. Le code lit NULL comme 0 pour un COMPTE, mais aucune part n'est
-- calculée sans dénominateur.
alter table public.daily_summary add column if not exists covers_measured  integer;
alter table public.daily_summary add column if not exists covers_estimated integer;
