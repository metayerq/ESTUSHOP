-- LES CHARGES ONT DÉSORMAIS UNE PÉRIODE DE VALIDITÉ.
--
-- ⚠️ SANS ELLE, CHANGER UN MONTANT RÉÉCRIVAIT LE PASSÉ. `daily_economics` relit les charges en
-- direct à chaque calcul : augmenter le loyer en septembre changeait l'EBITDA de juin, partout,
-- sans que rien ne le signale. Et supprimer un poste le retirait de TOUS les mois passés —
-- trois mois qui devenaient soudain rentables.
--
-- ⚠️ `NULL` VEUT DIRE « PAS DE BORNE », PAS « ZÉRO ». `valid_from` nul = depuis toujours ;
-- `valid_to` nul = encore en vigueur. Les lignes existantes n'ont donc aucune borne et
-- continuent de s'appliquer partout — exactement leur comportement d'avant cette migration.
-- C'est la seule façon de déployer ça sans changer un seul chiffre affiché le jour même.
--
-- ⚠️ ET LA BORNE HAUTE EST EXCLUE. « Valide jusqu'au 1er octobre » veut dire que le
-- 30 septembre est le dernier jour couvert : c'est ainsi qu'on clôt une ligne et qu'on en ouvre
-- une autre le même jour sans compter le loyer deux fois.

alter table public.charges_fixes
  add column if not exists valid_from date,
  add column if not exists valid_to   date;

alter table public.employees
  add column if not exists valid_from date,
  add column if not exists valid_to   date;

comment on column public.charges_fixes.valid_to is
  'Premier jour NON couvert (borne exclue). NULL = encore en vigueur.';
comment on column public.employees.valid_to is
  'Premier jour NON couvert (borne exclue). NULL = encore en poste.';

-- ⚠️ `active` SURVIT, ET C'EST TEMPORAIRE. La caisse Mesa lit encore `active=eq.true`
-- (`lib/server/estushopCharges.ts`) : tant qu'elle n'est pas redéployée, une ligne clôturée
-- doit aussi devenir inactive, sinon le comptoir continuerait d'imputer un loyer qui n'existe
-- plus. ESTUSHOP maintient les deux en écriture. La colonne partira quand Mesa saura lire les
-- dates — un mardi ou un mercredi, café fermé.

-- Les index servent la résolution jour par jour, qui interroge ces bornes à chaque calcul.
create index if not exists charges_fixes_validite_idx on public.charges_fixes (valid_from, valid_to);
create index if not exists employees_validite_idx     on public.employees     (valid_from, valid_to);
