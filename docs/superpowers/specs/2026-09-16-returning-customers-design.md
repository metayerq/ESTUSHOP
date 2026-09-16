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

P2 (cohortes, profil jour × créneau) et P3 (sources, liste à reconquérir,
boucle Mesa) restent à faire.
