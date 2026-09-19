# POS Layer sur Vendus — Faisabilité & Plan d'implémentation

> Recherche du 2026-07-27 sur la doc API Vendus v1.1. Objectif : construire notre propre POS
> par-dessus Vendus (moteur fiscal), avec une UX supérieure pour la création produit, la TVA,
> les catégories, les tables, l'ouverture/fermeture de caisse et l'export SAF-T mensuel.
> Ce POS layer est le socle naturel du produit SaaS **Mesa**.

## Verdict : ✅ largement faisable, avec 2 zones grises

| Feature visée | API Vendus | Verdict |
|---|---|---|
| Création produit | `/products/` — CRUD complet (GET/POST/PATCH/DELETE), prix, variantes, stock multi-magasin, images base64, produits composés, modificateurs | ✅ Total |
| Gestion TVA | `tax_id` produits (NOR/INT/RED/ISE/OUT/NS) + `/taxes/` + codes d'exemption | ✅ Total |
| Catégories | `/products/categories/` | ✅ Total |
| Vente / encaissement | `/documents/` — POST de FT, FS, FR, NC, GT avec lignes, paiements multiples, création auto du client. **La conformité fiscale (ATCUD, QR code, signature) reste chez Vendus** | ✅ Total |
| SAF-T fin de mois | `GET /taxauthority/saft/?year=&month=` → XML en base64 dans la réponse JSON | ✅ Trivial |
| Tables / salles | `/tables/` et `/rooms/` en **lecture seule** — pas d'assignation de commandes ni d'ouverture/fermeture de table via API | ⚠️ Zone grise |
| Ouverture/fermeture de caisse | `/registers/` expose statut open/close + `balance`/`movements`, mais **pas d'action documentée pour ouvrir/fermer une session** | ⚠️ Zone grise |

### Résolution des zones grises : on les gère nous-mêmes

C'est même une opportunité — c'est là où l'UX Vendus est la plus faible.

- **Tables** : notre propre modèle tables/commandes en cours dans notre DB. Une "table ouverte"
  = un panier persistant chez nous. À l'encaissement, on POST le document chez Vendus.
  Vendus ne voit que la vente finale — fiscalement suffisant.
- **Caisse** : notre propre notion de session (fond de caisse, comptage, écart théorique/réel
  recoupé via `/registers/balance` et les documents du jour). Le Z Vendus reste dispo en backoffice.

### Point à valider en pratique

Les documents créés via API sont rattachés à un register de type "API" — vérifier que ça
n'interfère pas avec le register POS existant côté numérotation de séries. Test facile avec
la clé API (env Vercel, jamais dans le code).

## Concept

Vendus = moteur fiscal (documents certifiés AT, SAF-T, séries).
Nous = 100 % de l'expérience : UI de vente, tables, produits, caisse.
Même architecture qu'ESTUSHOP côté lecture — on ajoute l'écriture.

### Idées différenciantes

- **Création produit en 10 secondes** : un seul formulaire (nom, prix TTC, catégorie, TVA en
  3 boutons), photo optionnelle, dispo immédiatement dans la grille de vente.
- **Grille de vente tactile** type Square : catégories en onglets, produits en tuiles colorées,
  panier à droite, encaissement en 2 taps (FS + méthode de paiement).
- **Vue salle visuelle** : plan de salle drag & drop, tables colorées par état
  (libre / occupée / addition demandée), durée d'occupation, split par personne ou par ligne.
- **Clôture guidée** : wizard de fin de journée — comptage du tiroir, écart calculé, résumé
  CA/TVA par taux ; le 1er du mois, bouton "Télécharger le SAF-T" (voire envoi auto par cron).
- **Mode hors-ligne (PWA)** : file d'attente des ventes, sync au retour du réseau.
  Gros différenciateur mais à garder pour plus tard (risque sur les séquences de facturation).

## Plan d'implémentation

### Phase 1 — Moteur de vente (le risque technique d'abord)
1. Wrapper API Vendus côté serveur (routes Next.js, clé en env Vercel) : POST documents,
   CRUD produits, taxes.
2. **Spike go/no-go** : créer une FS de test via API sur un register de test, vérifier
   ATCUD/QR/série, puis l'annuler (NC). Valide la chaîne fiscale de bout en bout.
3. Grille de vente + panier + encaissement (FS, CASH/carte), affichage/impression du ticket.

### Phase 2 — Produits & TVA
4. CRUD produits avec notre UX rapide, catégories, taux TVA. Sync bidirectionnelle :
   Vendus source de vérité, notre DB en cache.

### Phase 3 — Tables
5. Modèle commandes ouvertes dans notre DB, plan de salle, ajout d'articles, transfert,
   split, encaissement → document Vendus.

### Phase 4 — Caisse & clôture
6. Sessions ouverture/fermeture maison, comptage, rapport journalier (recoupé avec les
   documents API du jour), export SAF-T mensuel en un clic.

### Phase 5 — Polish Mesa
7. Multi-tenant, onboarding (saisie de la clé API Vendus du client), facturation 29 €/mois.

## Sources (doc API Vendus v1.1)

- Documents : https://www.vendus.pt/ws/v1.1/documents.doc
- Products : https://www.vendus.pt/ws/v1.1/products.doc
- Tables : https://www.vendus.pt/ws/v1.1/tables.doc
- Registers : https://www.vendus.pt/ws/v1.1/registers.doc
- SAF-T : https://www.vendus.pt/ws/v1.1/taxauthority/saft.doc
- Index endpoints : https://www.vendus.pt/ws/
