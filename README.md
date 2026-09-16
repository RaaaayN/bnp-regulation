# Regulatory Intelligence Assistant

API d'assistance à l'analyse des changements réglementaires. Le MVP ingère des
textes structurés, recherche des passages avec leurs citations, compare deux
versions d'une réglementation, estime les impacts internes potentiels et bloque
les conclusions dont les sources ne peuvent pas être vérifiées.

> L'application assiste l'analyse. Elle ne fournit pas de conseil juridique et
> ne prend aucune décision de conformité autonome.

Projet de portfolio indépendant construit sur des données synthétiques. Il n'est
ni affilié à BNP Paribas ni utilisé par le Groupe.

## Démonstration

```bash
make demo
```

- interface d'analyse : <http://localhost:8000/demo> ;
- contrats OpenAPI : <http://localhost:8000/docs> ;
- métriques Prometheus : <http://localhost:8000/metrics> ;
- serveur Prometheus : <http://localhost:9090>.

Le bouton **Run complete analysis** exécute réellement les cinq appels API :
ingestion, retrieval, comparaison, revue des citations et analyse d'impact.

## Évaluation reproductible

Le benchmark principal `v2.0.0` est un **challenge set synthétique**, versionné
et déterministe. Il contient 30 documents, 60 requêtes, 120 cas de changement et
60 claims à vérifier, répartis en `train` / `dev` / `test` sans chevauchement de
familles générées. Ces splits évitent la répétition littérale d'un thème, mais
pas la répétition des gabarits de génération.

Résultats du split de test, avec intervalle de confiance bootstrap à 95 % :

| Mesure | Résultat | IC 95 % | Échantillon |
|---|---:|---:|---:|
| Recall@5 | 50,00 % | 30,00–70,00 % | 20 requêtes |
| Mean Reciprocal Rank | 50,00 % | 30,00–70,00 % | 20 requêtes |

Le Recall@5 n'est publiable qu'avec son incertitude et son échantillon : sur
20 requêtes synthétiques, l'intervalle `[30 %–70 %]` est trop large pour en
tirer une estimation stable, et ne dit rien sur un corpus EUR-Lex réel.

Le benchmark utilise la même garde que l'API : au moins 60 % des termes
informatifs de la requête doivent apparaître dans le passage. Ce choix
fail-closed pénalise les paraphrases lexicalement éloignées, mais empêche le
meilleur résultat BM25 de se qualifier uniquement parce qu'il est normalisé par
rapport aux autres résultats de la requête.

Les 40 comparaisons de changement et les 20 cas du reviewer passent tous les
attendus. Ils sont désormais rapportés comme **tests de non-régression**, pas
comme F1 ou accuracy : les exemples sont dérivés des mêmes gabarits lexicaux que
les règles testées (`should` → `must`, nombre ou délai modifié, ajout/suppression)
et ne forment pas une évaluation indépendante.

```bash
make benchmark-v2
```

Cette commande évalue uniquement le split `test` et produit :

- `artifacts/evaluation-report-v2.json`, rapport canonique exploité par la démo ;
- `artifacts/evaluation-report-v2.md`, résumé lisible avec résultats par difficulté ;
- Recall@5 et MRR avec intervalles de confiance bootstrap à graine fixe ;
- nombre de fixtures de non-régression satisfaites pour le détecteur et le
  reviewer, sans les présenter comme des métriques de généralisation.

Le rapport inclut la version, le split, le SHA-256 du dataset et le nombre de cas.
Il faut publier ensemble le score **et** la taille du split évalué. Le petit
benchmark `v1.0.0` (6 requêtes, 6 changements et 3 claims) reste un test
d'acceptation historique ; ses fixtures satisfaites ne constituent pas une
preuve de généralisation.

> Toutes les clauses de `v2.0.0` sont fictives. Elles ne sont ni des citations,
> ni des résumés, ni des interprétations d'EUR-Lex, de l'EBA ou de la BCE. Une
> évaluation sur textes publics annotés par plusieurs humains reste nécessaire
> avant toute affirmation sur une qualité en conditions réelles.

### Évaluation Gemini optionnelle

Gemini intervient uniquement comme juge sémantique **consultatif**. Il ne modifie
jamais les métriques déterministes. Les réponses structurées sont validées par
Pydantic, les appels sont retentés avec un backoff borné et mis en cache par
empreinte SHA-256 afin de limiter coût et variabilité.

Ajoutez votre secret dans `.env` (ce fichier est ignoré par Git) :

```dotenv
GEMINI_API_KEY=votre-cle
```

Puis lancez :

```bash
make benchmark-gemini
```

Le rapport sépare explicitement `groundedness`, `correctness`, `completeness` et
le taux de passage Gemini des résultats déterministes. Aucun score Gemini n'est
publié dans le rapport canonique par défaut : il dépend d'un service externe et
doit être régénéré avec sa configuration de modèle. La configuration du modèle,
du cache et des tentatives est documentée dans `.env.example`. Références :
[gestion de la clé Gemini](https://ai.google.dev/gemini-api/docs/api-key) et
[sorties structurées](https://ai.google.dev/gemini-api/docs/structured-output).

### Corpus réglementaire officiel

Un pipeline séparé acquiert DORA, RGPD, AI Act, MiCA et CRR depuis le dépôt
Cellar de l'Office des publications, avec identifiants CELEX/ELI, URLs finales,
horodatages, tailles et SHA-256 :

```bash
make public-corpus
```

Les snapshots restent locaux et ne sont pas confondus avec la vérité terrain du
benchmark. Le protocole et la frontière d'annotation sont détaillés dans
[docs/public-corpus.md](docs/public-corpus.md).

## Fonctionnalités

- parsing texte/HTML et découpage par titres, articles et paragraphes ;
- recherche lexicale déterministe (BM25 + Jaccard) avec garde sur la couverture
  des termes informatifs de la requête ;
- comparaison `added` / `removed` / `modified` / `unchanged` ;
- détection de changements matériels, notamment `should` → `must` ;
- analyse prudente des politiques et contrôles potentiellement impactés ;
- reviewer fail-closed vérifiant chaque extrait cité dans sa source ;
- amorce de sanitisation par regex : masquage IBAN/e-mail et signalement
  consultatif de trois motifs d'injection ;
- benchmark split-aware, métriques hors ligne et intervalles bootstrap ;
- juge Gemini optionnel avec sorties structurées, cache et retries ;
- instrumentation HTTP et exposition Prometheus ;
- prototype de schéma/repositories PostgreSQL non branché au chemin HTTP ;
- image Docker non-root et stack Compose avec healthchecks.

## Démarrage avec Docker

```bash
cp .env.example .env
docker compose up --build --detach --wait
curl --fail http://localhost:8000/health
```

Compose démarre trois services avec healthchecks : API, PostgreSQL et Prometheus.

## Développement local

Python 3.12 et [uv](https://docs.astral.sh/uv/) sont recommandés.

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
```

## Parcours API minimal

Indexer un passage :

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'content-type: application/json' \
  -d '{
    "source": "EBA Guidelines 2026",
    "content": "# Model monitoring\n\nArticle 12.3\n\nInstitutions must review controls annually."
  }'
```

Puis rechercher la preuve :

```bash
curl -X POST http://localhost:8000/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"annual model monitoring review"}'
```

Une recherche sans passage suffisamment pertinent renvoie explicitement
`insufficient_evidence`. Les autres contrats sont visibles et testables dans
OpenAPI :

| Endpoint | Rôle |
|---|---|
| `POST /v1/documents` | Nettoyer, découper et indexer un document |
| `POST /v1/search` | Retrouver les passages classés et cités |
| `POST /v1/changes/compare` | Comparer deux ensembles de sections |
| `POST /v1/claims/review` | Vérifier les claims d'un changement |
| `POST /v1/impacts/analyze` | Classer les impacts internes potentiels |

## Architecture

```mermaid
flowchart LR
    Sources[EBA / ECB / EUR-Lex] --> Guard[Sanitisation]
    Guard --> Ingestion[Ingestion structurée]
    Ingestion --> Retrieval[Recherche lexicale BM25 + Jaccard]
    Retrieval --> Analysis[Change + Impact analysis]
    Analysis --> Reviewer[Reviewer fail-closed]
    Reviewer --> API[FastAPI]
    API --> Analyst[Analyste conformité]
    API --> Metrics[Prometheus metrics]
    Ingestion -. schéma initialisé, données non écrites .-> PG[(PostgreSQL)]
```

Les choix, flux de données, frontières de confiance et limites sont détaillés
dans [docs/architecture.md](docs/architecture.md). Le guide Docker et les
consignes de passage en production sont dans
[docs/deployment.md](docs/deployment.md).

## État et limites du MVP

L'index lexical exposé par l'API est en mémoire : son contenu est perdu au
redémarrage. Le schéma PostgreSQL et des repositories existent, mais l'ingestion
et la recherche HTTP ne les utilisent pas. Aucun stockage vectoriel ni graphe
n'est provisionné. Un adaptateur d'embeddings Gemini existe pour des
expérimentations hors ligne, est chargé paresseusement et n'est pas appelé par
la recherche HTTP.

Les scores affichés proviennent uniquement du rapport versionné présent dans
`artifacts/` (v2 prioritaire, v1 en repli). Ils doivent être complétés avec un
corpus public annoté avant toute conclusion sur la qualité en production.
