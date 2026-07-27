# Mesa POS — Phase 1 : Moteur de vente sur Vendus

> Spec validé le 2026-07-27. Portée : Phase 1 uniquement (spike fiscal go/no-go + grille de
> vente + encaissement). Les phases suivantes (produits, tables, caisse, multi-tenant) auront
> chacune leur propre spec. Basé sur la recherche API Vendus v1.1 du 2026-07-27.

## Contexte

Vendus sert de **moteur fiscal** (documents certifiés AT, ATCUD, QR code, séries, SAF-T).
Mesa fournit **100 % de l'expérience utilisateur** : grille de vente tactile, panier,
encaissement. Même philosophie qu'ESTUSHOP côté lecture — on ajoute l'écriture.

La recherche préalable a établi que l'API Vendus couvre : CRUD produits, taxes, catégories,
POST de documents (FS/NC/FT/FR/GT) avec paiements, export SAF-T. Zones grises (tables,
sessions de caisse) : hors périmètre Phase 1, elles seront gérées dans notre propre modèle
aux phases 3–4.

## Décisions de cadrage

| Sujet | Décision |
|---|---|
| Portée | Phase 1 seule : spike go/no-go + moteur de vente |
| Repo / stack | **Nouveau repo `mesa`** — Next.js 15 (App Router), TypeScript, Tailwind, Vercel |
| Environnement de test | **Compte Vendus séparé** dédié au dev (isolation totale, préfigure le multi-tenant) |
| Base de données | **Aucune en Phase 1** — Vendus est la source de vérité, panier côté client, cache mémoire court |
| Ticket | **Affichage écran seul** (ATCUD + QR). Impression thermique reportée |
| Appareil cible | **Tablette** (iPad/Android), paysage ~10–13" |
| Accès | **PIN partagé** (env var), cookie signé longue durée |
| Langue UI | **Anglais** |
| Critère de fin | **Prototype validé** sur le compte de test. Le passage en service réel à Estudantina est une décision séparée |

Hors périmètre Phase 1 (explicite) : remises, notes sur ligne, choix du client (tout part en
consommateur final), variantes/modificateurs, split de paiement, impression, mode hors-ligne,
tables, sessions de caisse, multi-tenant.

## Architecture

Approche retenue : **client Vendus typé + couche de vente** (vs proxy minimal, écarté car
chaque phase suivante devrait re-structurer ; vs local-first avec file d'attente, écarté car
risque sur les séquences de facturation et complexité injustifiée).

```
mesa/
├── lib/vendus/            # Client Vendus typé (cœur réutilisable)
│   ├── client.ts          # HTTP : auth basic (clé API), timeouts, erreurs normalisées
│   ├── products.ts        # listProducts, listCategories, createProduct (spike)
│   ├── taxes.ts           # listTaxes
│   ├── documents.ts       # createDocument (FS/NC), getDocument, listRecentDocuments
│   └── types.ts           # Types + schémas Zod des réponses Vendus
├── app/
│   ├── api/catalog/       # GET catalogue (produits + catégories + taxes, cache 60 s)
│   ├── api/checkout/      # POST panier → FS Vendus → {number, atcud, qrData, total}
│   ├── (pos)/             # UI : grille de vente, panier, écran de confirmation
│   └── login/             # Saisie du PIN
├── middleware.ts          # Garde PIN (cookie signé) sur tout sauf /login
└── scripts/spike.ts       # Go/no-go fiscal — utilise lib/vendus directement
```

Principes :

- **La clé API ne vit qu'en env Vercel** (`VENDUS_API_KEY`), jamais côté client. Tout passe
  par les routes API.
- **`lib/vendus` est agnostique de l'app** : `createVendusClient({ apiKey })` prend la clé en
  paramètre — c'est ce qui deviendra multi-tenant en Phase 5 sans réécriture. Le module
  n'importe rien de Next.js : testable en isolation, utilisable par le spike comme par les
  routes API.
- **Pas d'état serveur** : le panier vit dans le state React de la tablette ; Vendus détient
  les documents ; le seul cache est un cache mémoire court sur le catalogue.
- Compte Vendus **de test** dédié pendant toute la Phase 1.

## Client Vendus (`lib/vendus`)

### `client.ts`

`createVendusClient({ apiKey })` expose des `get`/`post` internes avec :

- Auth HTTP Basic (clé en username, mot de passe vide), base `https://www.vendus.pt/ws/v1.1`.
- Timeout explicite (10 s).
- **Politique de retry asymétrique** : les GET peuvent être retentés (2×, backoff court) ;
  les **POST de documents ne sont jamais rejoués automatiquement**. En cas de doute (timeout
  après envoi), le client remonte une erreur `possibly_created` et l'UI propose de vérifier
  les documents récents plutôt que de risquer une double facture.
- Erreurs normalisées en un type unique :
  `VendusError { kind: 'auth' | 'validation' | 'rate_limit' | 'network' | 'possibly_created' | 'unknown', status, messages[] }`
  — les messages d'erreur Vendus (codes + textes) sont conservés pour affichage.

### Modules métier

Fonctions fines, une par endpoint utilisé :

- `listProducts()` / `listCategories()` — pagination gérée en interne (itération jusqu'à la
  fin), retour à plat.
- `listTaxes()` — les taux (NOR/INT/RED/ISE) avec leurs valeurs.
- `createProduct(input)` — utilisé par le spike (valide le CRUD écriture pour la Phase 2).
- `createDocument(input)` — payload FS (lignes, `payments[]`, client optionnel) ou NC
  (référence au document d'origine). Retour parsé :
  `{ id, number, atcud, qrData, date, totals }`.
- `getDocument(id)` / `listRecentDocuments()` — écran de confirmation et cas `possibly_created`.

### `types.ts`

Schémas Zod sur **toutes** les réponses Vendus : si Vendus change ou renvoie une forme
inattendue, on échoue bruyamment côté serveur avec un log clair, jamais silencieusement dans
l'UI. Les types TS sont inférés des schémas (une seule source de vérité).

## UI de vente (tablette, paysage)

### Écran principal `/`

Une seule vue, pas de navigation pendant le service :

- **Gauche (~65 %)** : onglets de catégories en haut, grille de tuiles produits (nom, prix
  TTC, couleur par catégorie). Tuiles grandes (min ~110 px), cibles tactiles généreuses, pas
  d'UI dépendante du hover.
- **Droite (~35 %)** : le panier — lignes (nom, qté, prix), tap sur une ligne pour ± /
  supprimer, total TTC en gros, bouton **Charge** principal.
- Catalogue chargé au montage via `/api/catalog`, rafraîchi en arrière-plan. Si l'appel
  échoue au montage : écran d'erreur avec bouton Retry (pas de grille vide silencieuse).

### Flux d'encaissement (2 taps depuis le panier)

1. Tap **Charge** → volet de paiement : gros boutons **Cash** / **Card** (+ MB WAY si
   trivial — codes Vendus `NU` / `CC` / `MBWAY`). Paiement unique, pas de split.
2. Tap sur la méthode → POST `/api/checkout` → spinner bloquant (pas de double-tap
   possible) → **écran de confirmation** : montant, n° de document, ATCUD, QR code rendu
   localement à partir des données Vendus, bouton **New sale** qui vide le panier.

**Cas cash** : pavé optionnel « montant reçu » → rendu de monnaie affiché. Skippable (tap
direct sur Cash = montant exact).

### Login `/login`

Pavé PIN plein écran. PIN comparé à une env var, cookie signé httpOnly longue durée (30 j) —
on ne retape pas le PIN à chaque service. `middleware.ts` protège tout sauf `/login`.

## Flux de données & gestion d'erreurs

### Checkout — le chemin critique

1. Le client envoie **le minimum** :
   `{ items: [{ productId, qty }], payment: 'NU' | 'CC' | 'MBWAY', amountReceived? }`.
   Jamais de prix ni de taux de TVA depuis le client.
2. La route valide (Zod), vérifie que chaque `productId` existe dans le catalogue en cache,
   puis construit le payload FS en envoyant id + qté : **Vendus applique ses propres prix et
   TVA**. Un seul chiffre fait foi : le total renvoyé par Vendus, affiché à la confirmation.
   Si le catalogue de la tablette était périmé (prix changé entre-temps), l'écart est visible
   à la confirmation — acceptable en Phase 1.
3. Réponse normalisée à l'UI : `{ number, atcud, qrData, total, change? }`.

### Matrice d'erreurs (UI)

| Erreur | Comportement |
|---|---|
| `validation` (payload rejeté par Vendus) | Panier intact ; bandeau rouge avec les messages Vendus. Rien n'a été facturé. |
| `network` avant envoi confirmé | Panier intact, bandeau « Nothing was charged — retry ». |
| `possibly_created` (timeout post-envoi) | Écran dédié : « The sale may have been recorded » + bouton **Check** listant les documents des 5 dernières minutes avec montants — l'utilisateur tranche : « It's there » (→ confirmation) ou « It's not » (→ retour panier). Jamais de re-POST automatique. |
| `auth` / clé invalide | Écran bloquant « Configuration error » — inutile de réessayer. |
| `rate_limit` | Retry automatique unique après l'attente indiquée, sinon bandeau. |

### Catalogue

Cache serveur en mémoire 60 s (pattern `_ttl_get` d'ESTUSHOP, version TS — les échecs ne
sont jamais mis en cache). `GET /api/catalog?fresh=1` force le rechargement (bouton discret
dans l'UI : « je viens d'ajouter un produit dans Vendus »).

### Verrou anti double-vente côté UI

Le bouton de paiement passe en état `submitting` jusqu'à résolution complète ; un seul
checkout en vol à la fois.

## Spike go/no-go (première chose construite)

Script CLI `scripts/spike.ts` (lancé avec `tsx`, clé du **compte de test** en env locale),
qui déroule et logge chaque étape :

1. **Lecture** : `listTaxes`, `listProducts`, `/registers/` — vérifie l'accès et note l'id
   du register utilisé par l'API.
2. **Création produit** de test via API — valide le CRUD écriture pour la Phase 2.
3. **FS de test** : 1 × produit test, paiement `NU` → contrôle de la réponse : **numéro de
   série, ATCUD présent, données QR présentes**.
4. **Vérification croisée** : le document apparaît dans `GET /documents/` ; noter dans quel
   register/série il tombe — le point à valider identifié dans la recherche : la série
   « API » n'interfère pas avec un register POS.
5. **Annulation** : NC référençant la FS → vérifier son ATCUD et le lien au document
   d'origine.
6. **Verdict imprimé** : GO / NO-GO par critère, en table lisible.

**Critères de go** : chaque document créé a série + ATCUD + QR valides, la NC référence bien
la FS, et le comportement des séries est compris et documenté dans le README du repo. Si un
critère échoue → arrêt et réévaluation avant d'écrire la moindre UI.

Le spike n'est **pas jetable** : il n'appelle que `lib/vendus`, donc il sert ensuite de
smoke test permanent contre le compte de test (relançable avant chaque phase suivante).

## Tests

Trois niveaux, proportionnés à un prototype dont le vrai risque est fiscal :

1. **`lib/vendus` — le plus testé** (Vitest, HTTP mocké) : construction des payloads FS/NC,
   normalisation des erreurs (chaque `kind` de la matrice), politique no-retry sur POST,
   pagination du catalogue. Les schémas Zod sont validés contre des **fixtures réelles
   enregistrées pendant le spike** (réponses anonymisées du compte de test) — pas des
   fixtures inventées.
2. **Logique panier** — fonctions pures extraites (`addItem`, `changeQty`, `total`, rendu de
   monnaie) testées unitairement ; un test de composant sur le flux panier → volet paiement
   (verrou `submitting` inclus).
3. **Intégration réelle** — le spike lui-même, relançable à tout moment contre le compte de
   test. Pas de Playwright en Phase 1 (YAGNI) ; à la place, une **checklist manuelle
   tablette** en fin de phase : vente cash avec rendu, vente carte, erreur réseau simulée
   (mode avion), catalogue périmé, PIN.

## Ordre de construction

1. Repo `mesa` + `lib/vendus` (client + types + tests).
2. `scripts/spike.ts` → **go/no-go**. On ne continue que sur GO.
3. Routes `api/catalog` + `api/checkout` (+ tests).
4. UI : login PIN → grille + panier → volet paiement → confirmation.
5. Checklist manuelle tablette.

## Sources (doc API Vendus v1.1)

- Documents : https://www.vendus.pt/ws/v1.1/documents.doc
- Products : https://www.vendus.pt/ws/v1.1/products.doc
- Registers : https://www.vendus.pt/ws/v1.1/registers.doc
- SAF-T : https://www.vendus.pt/ws/v1.1/taxauthority/saft.doc
- Index endpoints : https://www.vendus.pt/ws/
