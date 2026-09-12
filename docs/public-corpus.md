# Corpus réglementaire public

Le fichier `datasets/public_sources.json` est une liste blanche versionnée de cinq
textes primaires publiés par EUR-Lex : DORA, RGPD, AI Act, MiCA et CRR. Chaque
entrée contient son identifiant CELEX, son identifiant ELI, sa page EUR-Lex et
son endpoint d'acquisition Cellar. Cellar est le dépôt de l'Office des
publications utilisé par EUR-Lex pour diffuser les fichiers officiels. Aucun
extrait juridique généré ou recopié manuellement n'entre dans ce corpus.
Le mécanisme suit la
[documentation officielle de l'API Cellar](https://op.europa.eu/en/web/cellar/cellar-data/publications).

## Acquisition reproductible

```bash
uv run python scripts/fetch_public_corpus.py
```

Les pages HTML sont enregistrées sous `artifacts/public-corpus/raw/`, avec un
fichier `provenance.json` qui consigne pour chaque téléchargement :

- l'URL demandée et l'URL finale après redirection ;
- l'identifiant CELEX et l'identifiant ELI ;
- l'heure de récupération en UTC ;
- le type et la taille du contenu ;
- le SHA-256 exact des octets téléchargés.

Le téléchargeur refuse les redirections hors du domaine officiel
`publications.europa.eu`, les types de contenu inattendus, les documents vides,
les contenus non structurés et les réponses dépassant 25 Mio. L'API Cellar
annonce actuellement certaines destinations en HTTP ; le client les réécrit en
HTTPS avant de les suivre. Les snapshots ne sont pas versionnés : le manifeste
de provenance suffit à identifier exactement le contenu utilisé lors d'une
expérience.

## Frontière d'évaluation

Ce pipeline acquiert des sources authentiques ; il ne fabrique pas de vérité
terrain. Les questions, passages pertinents et changements issus de ces textes
doivent ensuite être annotés et relus humainement avant de publier une métrique
de qualité. Les sorties éventuelles de Gemini peuvent accélérer la création de
candidats, mais ne doivent pas être présentées comme des labels humains.

La réutilisation des documents reste soumise à la
[notice juridique EUR-Lex](https://eur-lex.europa.eu/content/legal-notice/legal-notice.html).
