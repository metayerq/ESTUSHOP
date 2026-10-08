# ESTUSHOP — backoffice du café Estudantina (Lisbonne)

Flask + Jinja2, un `app.py` de ~9 300 lignes, Supabase, déployé sur Vercel (`estushop`).
~2 050 tests pytest, dont des tests de rendu au navigateur.

## Déploiement

⚠️ **NE FILTRE JAMAIS LA SORTIE DU DÉPLOIEMENT.** Faute commise trois fois : on affiche la
sortie entière, pas un extrait qui rassure.

Le café ouvre jeudi → lundi et ferme à 18 h ; il est fermé mardi et mercredi.

## Discipline de test

Chaque assertion neuve doit avoir été vue **ROUGE** par mutation. Respecte les gardes
existantes : si l'une d'elles bloque un changement, dis-le plutôt que de l'exempter en silence.

Le harnais navigateur a besoin de `CHROME_BIN` et `CHROME_LIB_PATH` ; sans eux les tests de
rendu sont **silencieusement sautés**, et la suite paraît verte.

⚠️ Lancer `pytest tests/`, pas `pytest` : `scripts/` contient un fichier qui exige un `.env`.

## Langue

Interface en anglais, commentaires et messages de commit en français.

## Ce qui mord le plus souvent

Un jeton CSS employé sans être défini — la règle est ignorée EN SILENCE. Une page qui existe
sans figurer au menu. Une valeur estimée affichée comme une mesure. Une première valeur traitée
comme un changement, donc repoussée au mois suivant par la date d'effet.
