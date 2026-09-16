# Clients récurrents — empreintes de cartes du terminal Revolut

**Date** : 2026-09-16 · **Statut** : validé par Quentin en session (« fais la tuile »)

## Besoin

Mesurer la part de clients qui reviennent, sans programme de fidélité ni
identité. Seule source disponible à l'échelle de toutes les ventes : les
paiements du terminal Revolut.

## Ce que le terminal donne, et ne donne pas

Un paiement en personne (`payment_method.type = "terminal"`) expose
`card_last_four` et `application_name` (libellé inscrit sur la puce, stable
par carte). Ni nom, ni BIN, ni expiration — la puce ne les transmet pas ;
`tags` ne contient que la réponse de l'émetteur. Les champs riches de l'API
Merchant n'existent que pour les paiements en ligne.

L'empreinte est donc `hash(last4 + libellé)`. Collisions estimées à 5–9 % des
cartes aux volumes du café (simulation), qui gonflent le taux ; Apple Pay
(numéro virtuel ≠ carte physique), renouvellements et cash le déflatent.
Résultat lu comme un ordre de grandeur à ±5 points.

## Design

- `revolut_merchant.py` : `fetch_day(day)` liste les commandes du jour
  (fenêtre Lisbonne → UTC) puis un appel `/orders/{id}/payments` par
  commande, 4 en parallèle, retry exponentiel sur 5xx/limite de débit. Ne
  retourne que `{pid, day, ts, amount, fp, label}`.
- Empreinte : SHA-256 salé par `sha256("estushop-card-visits|" + clé
  Merchant)`. Sans sel, les 60 000 combinaisons s'énumèrent en une seconde.
  Changer la clé impose de reconstruire l'historique.
- Table `card_visits` (pid pk, day, ts, amount, fp, label). RLS off.
- `POST /api/card-visits/sync {from,to}` — admin, 10 jours max par appel ;
  le bouton « Rebuild history » enchaîne les plages depuis l'ouverture.
- `/api/cron/refresh` synchronise hier + aujourd'hui (idempotent).
- `GET /api/returning?from&to` : visites récurrentes de la période (carte
  déjà vue avant CE ticket, sur tout l'historique), cartes connues / nouvelles,
  habitués (≥ 4 visites) et leur poids, part des cartes revenues ≥ 2 fois
  depuis l'ouverture, série mensuelle.
- Tuile « Returning customers » sous Economics, chargée à part de `/api/data`.

## RGPD

Donnée pseudonyme, intérêt légitime, finalité statistique interne. Rien en
clair nulle part, aucun croisement avec une identité. Relevés et extractions
brutes restent hors du repo.

## Hors périmètre

Identification nominative, programme de fidélité, croisement avec les NIF des
factures Vendus.

## P1 — page /clientes (validé le 16/09, « go P1 »)

Le dashboard garde la bande de quatre tuiles (pouls, suit la période) ; la
quatrième devient « At risk », en ambre — le seul chiffre qui appelle une
action. Chaque tuile mène à `/clientes`, sur le modèle Transactions →
/transactions. La page détaillée n'a pas de sélecteur de période : cohortes,
Pareto et rythme n'ont de sens que depuis l'ouverture, et sa base est
affichée en tête.

Trois panneaux (`/api/customers`) : nouveaux vs récurrents par semaine ISO
(12 dernières, semaine en cours en retrait) ; CA carte par tranche de
fréquence avec ticket et part des 20 % les plus assidus ; histogramme des
intervalles entre visites avec médiane et quartiles.

« À risque » (décision Quentin) : habitué (≥ 4 visites) absent depuis plus de
3 × son intervalle médian personnel, plancher 7 jours (le café ferme deux
jours par semaine). La carte à 71 visites est un client, pas le staff —
aucune exclusion.

Couleurs propres à la page : bleu des nouvelles cartes et rampe verte
ordinale, validées CVD clair/sombre (ΔE 24 / 20) ; `--spec` ne convenait pas,
il vaut le même vert que `--green` en mode sombre.

## P2 — cohortes et profil (« go P2 », 16/09)

Deux panneaux de plus sur `/clientes`, mêmes données.

Cohortes : mois de première visite → % de la cohorte revue en M+1…M+4. Un
mois pas encore commencé vaut null, le mois en cours est marqué partiel et
affiché en retrait. Le mois d'ouverture se lit à part (amis, curieux) ; la
phrase de lecture moyenne M+1 sur les autres mois — c'est la pente qui
dira si une action fidélité a un effet.

Profil : « première visite » = le premier ticket de CHAQUE carte (y compris
celles devenues habituées), « habitués » = toutes les visites des cartes
≥ 4. Répartition par jour ouvré et par créneau (matin < 12 h, midi < 15 h,
après-midi < 18 h, soir), en heure de Lisbonne. La lecture nomme le jour
des habitués, le jour des nouveaux, et leurs créneaux.

## P3 — d'où viennent les habitués (« go P3 », 16/09)

Sources lues dans la table `events` (statut ≠ annulé, date ≤ aujourd'hui,
plage date → end_date). Une nouvelle carte « d'un événement » = première
visite un jour de l'événement, à partir de son heure de début quand elle est
renseignée — sinon un popup du soir hérite des nouveaux de la matinée.
Mesure comparable : revenu sous 14 jours ; immature tant que 14 jours ne se
sont pas écoulés, et l'écran le dit. Référence : nouveaux des jours sans
événement. Canal implicite « soirées » : premières visites après 19 h, avec
la part de leurs visites suivantes faites en journée.

Correction d'une lecture de la maquette : « seulement 17 % des clients du
soir reviennent en journée » rapportait les revenus-en-journée à TOUTES les
cartes du soir. Rapportés à celles qui reviennent, c'est plus de la moitié,
et 63 % de leurs visites suivantes ont lieu avant 18 h : les soirées
nourrissent le café de jour, ce n'est pas une clientèle à part.

La « liste à reconquérir » du plan initial n'existe pas : sans identité, une
liste d'empreintes ne sert à personne. La reconquête se fait au terminal,
quand la carte repasse — c'est la boucle fidélité de Mesa.
