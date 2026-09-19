# Produits popup (chef partenaire) — commission comme marge brute

**Date** : 2026-08-31 · **Statut** : validé par Quentin en session

## Besoin

Certains produits vendus au café sont fournis par un chef partenaire lors de
popups. Quentin encaisse la vente TTC dans son Vendus, garde une commission
sur le TTC (10/15/20 % ou taux libre), et le chef lui facture le restant hors
TVA (13 %). La marge brute de Quentin sur ces produits est donc sa commission,
pas `prix − coût recette`.

## Design

### Données
- Table Supabase `popup_products` : `product_name text primary key`,
  `commission_pct numeric not null`, `updated_at timestamptz default now()`.
  RLS désactivée (comme toutes les tables du projet).

### Backend (app.py)
- `_load_popup_flags()` : lit la table, micro-cache TTL 60 s.
- `_catalog()` : remplace tous les appels `get_catalog()` d'app.py ; applique
  l'overlay : pour chaque produit flaggé, `cost = net × (1 − pct/100)`
  (`net` = prix HT, nouveau champ exposé par `_fetch_catalog`), plus
  `popup: True` et `commission_pct`. Marge % affichée = pct exactement,
  coût € = facture attendue du chef.
- `POST /api/popup-flag` (admin) : `{name, popup, commission_pct}` → upsert ou
  delete ; invalide les caches (catalogue Vendus + flags).
- `_products_list` et `top_products` (vendus.py) exposent `popup` et
  `commission_pct` dans chaque ligne produit.

### Frontend (dashboard, static/dashboard.js + templates/index.html)
- Lignes « Products sold » cliquables → modal produit (style des drawers
  existants) : nom, prix, marge actuelle ; case « Produit popup (chef
  partenaire) » ; si cochée, dropdown 10 % / 15 % / 20 % / Custom (champ
  libre) ; bouton Save → POST puis rechargement des données.
- Badge `popup` violet à côté du nom dans la liste.

### Hors périmètre
- Entité « chef » (multi-partenaires) : un simple % par produit suffit.
- Réécriture de l'historique `daily_summary` : le flag joue sur les calculs
  live ; `/api/summary/rebuild` existe déjà si besoin de recalculer le passé.
